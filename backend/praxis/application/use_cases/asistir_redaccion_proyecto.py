"""Casos de uso de asistencia al redactor de proyectos (feat-42.3).

3 asistentes LLM, todos opcionalmente informados por el perfil
opositor del despacho:

1. `GenerarArticulado(tema, tipo, perfil) → list[str]`
   El asesor describe el objeto del proyecto ("Crear un registro de
   medicamentos críticos"), el LLM devuelve articulado borrador
   (3-7 artículos según tipo).

2. `GenerarFundamentos(tema, articulado, perfil) → str`
   El LLM compone fundamentos en Markdown (exposición + cita de
   normativa relacionada cuando puede, sin RAG todavía).

3. `RefinarArticulo(texto_actual, instruccion) → str`
   "Hacelo más técnico", "más corto", "alineá con bandera X", etc.

Todos usan `LlmProvider.razonar_libre` (escape hatch ya disponible).
Cache no se aplica acá — el asesor itera mucho.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from praxis.application.ports import LlmProvider, PerfilOpositorRepository
from praxis.domain import (
    PerfilOpositorDespacho,
    TIPO_LABELS,
    TipoProyecto,
)
from uuid import UUID

log = logging.getLogger(__name__)


SYSTEM_PROMPT_ARTICULADO = """Sos un secretario parlamentario senior
con 20 años de experiencia redactando proyectos en la Cámara de
Diputados Nacional argentina.

Te paso:
- El TIPO de proyecto (Ley / Resolución / Comunicación / Declaración).
- El TEMA / objeto del proyecto (1-2 frases del asesor).
- El PERFIL OPOSITOR del despacho que lo va a presentar (opcional —
  cuando esté, los artículos deben alinearse con la bandera).

Devolvé EXACTAMENTE este JSON, sin texto antes ni después:

{
  "articulado": [
    "Artículo 1° — ...",
    "Artículo 2° — ...",
    "Artículo N° — De forma."
  ]
}

Reglas técnicas:
- LEY: 3-7 artículos. Primer artículo es OBJETO de la ley. Último es
  "Comuníquese al PEN" o "De forma" según corresponda.
- RESOLUCION: 1-3 artículos. La cámara expresa voluntad o crea
  comisiones internas.
- COMUNICACION: 1-2 artículos. Solicita información al PEN sobre
  preguntas concretas.
- DECLARACION: 1 artículo (a veces 2). La cámara declara X.
- Numeración: "Artículo 1° —", "Artículo 2° —", ...
- NO uses títulos de capítulos en v1 (mantenelo plano).
- NO inventes leyes existentes que no conozcas con certeza.
- Si el perfil indica bandera de salud y el tema es salud, alineá
  el lenguaje (ej. "garantízase el acceso", "decláranse de interés").
"""


SYSTEM_PROMPT_FUNDAMENTOS = """Sos un asesor parlamentario senior que
redacta los FUNDAMENTOS de un proyecto. Te paso:
- TIPO de proyecto + TEMA.
- ARTICULADO ya redactado.
- PERFIL OPOSITOR del despacho (opcional).

Devolvé los fundamentos en Markdown plano (sin JSON, solo texto), 4-8
párrafos, estilo declarativo, citas de normativa argentina cuando
correspondan SIN inventarlas. Si dudás de una cita, omitila.

Estructura recomendada:
1. Apertura: Sr/a Presidente, ...
2. Contexto del problema (1-2 párrafos).
3. Marco normativo vigente (Constitución, ley si la conocés).
4. Justificación de la propuesta (cómo el articulado responde).
5. Cierre: solicito a mis pares...

Tono: respetuoso con la institución, propositivo, técnico.
Largo objetivo: 800-1500 palabras.
"""


SYSTEM_PROMPT_REFINAR = """Sos un editor parlamentario. Te paso un
TEXTO (un artículo o fragmento de fundamentos) y una INSTRUCCIÓN
del asesor sobre cómo modificarlo. Devolvé SOLO el texto refinado,
sin comentarios ni explicaciones. Mantené el estilo legal-parlamentario.
"""


@dataclass(frozen=True, slots=True)
class ArticuladoGenerado:
    articulado: list[str]
    modelo: str


class GenerarArticuladoConLLM:
    """Use case 1: genera articulado borrador."""

    def __init__(
        self,
        *,
        perfiles: PerfilOpositorRepository,
        llm: LlmProvider,
    ) -> None:
        self._perfiles = perfiles
        self._llm = llm

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        tipo: TipoProyecto,
        tema: str,
    ) -> ArticuladoGenerado:
        perfil = await self._perfiles.buscar_por_despacho(despacho_id)
        contenido = self._armar_contenido(tipo=tipo, tema=tema, perfil=perfil)
        raw, modelo = await self._llm.razonar_libre(
            system=SYSTEM_PROMPT_ARTICULADO,
            user=contenido,
            max_tokens=2000,
        )
        parsed = self._parsear_json(raw)
        return ArticuladoGenerado(
            articulado=parsed.get("articulado", []),
            modelo=modelo,
        )

    def _armar_contenido(
        self,
        *,
        tipo: TipoProyecto,
        tema: str,
        perfil: PerfilOpositorDespacho | None,
    ) -> str:
        partes = [
            f"TIPO: {TIPO_LABELS[tipo]}",
            f"TEMA / objeto del proyecto:\n{tema.strip()}",
        ]
        if perfil is not None:
            partes.append(
                f"\nPERFIL OPOSITOR DEL DESPACHO:\n"
                f"- Bandera: {perfil.bandera_principal}\n"
                f"- Banderas secundarias: {'; '.join(perfil.banderas_secundarias[:3])}\n"
                f"- Tono comunicacional: {perfil.tono_comunicacional.value}",
            )
        partes.append("\nGenerá el JSON del articulado.")
        return "\n".join(partes)

    def _parsear_json(self, raw: str) -> dict:
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s[:-3].strip()
            if s.startswith("json"):
                s = s[4:].strip()
        return json.loads(s)


@dataclass(frozen=True, slots=True)
class FundamentosGenerados:
    fundamentos: str
    modelo: str


class GenerarFundamentosConLLM:
    """Use case 2: compone fundamentos en Markdown."""

    def __init__(
        self,
        *,
        perfiles: PerfilOpositorRepository,
        llm: LlmProvider,
    ) -> None:
        self._perfiles = perfiles
        self._llm = llm

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        tipo: TipoProyecto,
        tema: str,
        articulado: list[str],
    ) -> FundamentosGenerados:
        perfil = await self._perfiles.buscar_por_despacho(despacho_id)
        contenido = self._armar_contenido(
            tipo=tipo, tema=tema, articulado=articulado, perfil=perfil,
        )
        raw, modelo = await self._llm.razonar_libre(
            system=SYSTEM_PROMPT_FUNDAMENTOS,
            user=contenido,
            max_tokens=3000,
        )
        return FundamentosGenerados(fundamentos=raw.strip(), modelo=modelo)

    def _armar_contenido(
        self,
        *,
        tipo: TipoProyecto,
        tema: str,
        articulado: list[str],
        perfil: PerfilOpositorDespacho | None,
    ) -> str:
        articulado_txt = "\n".join(articulado)
        partes = [
            f"TIPO: {TIPO_LABELS[tipo]}",
            f"TEMA: {tema.strip()}",
            f"\nARTICULADO ya redactado:\n{articulado_txt}",
        ]
        if perfil is not None:
            partes.append(
                f"\nPERFIL OPOSITOR:\n"
                f"- Bandera principal: {perfil.bandera_principal}\n"
                f"- Línea de bloque: {perfil.linea_de_bloque}",
            )
        partes.append("\nGenerá los fundamentos en Markdown.")
        return "\n".join(partes)


class RefinarArticuloConLLM:
    """Use case 3: refina un texto puntual según instrucción del asesor."""

    def __init__(self, *, llm: LlmProvider) -> None:
        self._llm = llm

    async def ejecutar(
        self, *, texto_actual: str, instruccion: str,
    ) -> tuple[str, str]:
        """Devuelve (texto_refinado, modelo)."""
        contenido = (
            f"TEXTO ACTUAL:\n{texto_actual}\n\n"
            f"INSTRUCCIÓN DEL ASESOR:\n{instruccion}\n\n"
            "Devolvé el texto refinado."
        )
        raw, modelo = await self._llm.razonar_libre(
            system=SYSTEM_PROMPT_REFINAR,
            user=contenido,
            max_tokens=1500,
        )
        return raw.strip(), modelo
