"""Caso de uso: enriquecer una reunión de comisión con análisis LLM (feat-61.4.B.3).

Input:
- ID de la reunión (la entidad viene del repo).
- Texto del PDF de citación (puede ser None si no bajó).
- Perfil opositor del despacho (para personalizar la "oportunidad política").
- Comisión a la que pertenece (nombre + integrantes para contexto).

Output: `ResultadoEnriquecimiento` con todos los campos LLM listos para
persistir. El caller (router) los pasa al repo en una sola actualización.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from praxis.application.ports import (
    ComisionHcdnRepository,
    LlmProvider,
    PerfilOpositorRepository,
)
from praxis.domain import ComisionHcdn, ReunionComision
from praxis.infrastructure.scrapers.hcdn.citacion_pdf import (
    descargar_y_extraer,
    extraer_expedientes_citados,
)

log = logging.getLogger(__name__)

MAX_TOKENS_LLM = 1500


@dataclass(frozen=True, slots=True)
class ResultadoEnriquecimiento:
    """Lo que devuelve el LLM, listo para persistir."""

    tema_corto: str
    tipo_reunion: str
    convocada_por: str
    expedientes_citados: list[str]
    oportunidad_politica: str
    accion_sugerida: str


class ReunionNoEncontrada(Exception):
    pass


class EnriquecerReunionComision:
    """1 reunión → 1 llamada LLM. Idempotente: el caller decide
    si saltar cuando `enriquecida_en is not None`."""

    def __init__(
        self,
        *,
        llm: LlmProvider,
        perfiles: PerfilOpositorRepository,
        comisiones: ComisionHcdnRepository,
    ) -> None:
        self._llm = llm
        self._perfiles = perfiles
        self._comisiones = comisiones

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        reunion: ReunionComision,
        comision: ComisionHcdn,
    ) -> ResultadoEnriquecimiento:
        texto_pdf = ""
        expedientes_pdf: list[str] = []
        if reunion.citacion_pdf_url:
            extracto = await descargar_y_extraer(reunion.citacion_pdf_url)
            if extracto:
                texto_pdf = extracto
                expedientes_pdf = extraer_expedientes_citados(extracto)

        perfil = await self._perfiles.buscar_por_despacho(despacho_id)
        perfil_texto = _perfil_a_texto(perfil)

        system, user = _armar_prompt(
            comision=comision,
            reunion=reunion,
            texto_pdf=texto_pdf,
            expedientes_pdf=expedientes_pdf,
            perfil_opositor_texto=perfil_texto,
        )
        texto, _modelo = await self._llm.razonar_libre(
            system=system, user=user, max_tokens=MAX_TOKENS_LLM,
        )
        parsed = _parsear_respuesta(texto)
        # Si el LLM no detecta expedientes, usamos los del regex del PDF.
        if not parsed["expedientes_citados"] and expedientes_pdf:
            parsed["expedientes_citados"] = expedientes_pdf
        return ResultadoEnriquecimiento(
            tema_corto=parsed["tema_corto"][:500],
            tipo_reunion=parsed["tipo_reunion"][:80],
            convocada_por=parsed["convocada_por"][:200],
            expedientes_citados=parsed["expedientes_citados"][:30],
            oportunidad_politica=parsed["oportunidad_politica"][:1500],
            accion_sugerida=parsed["accion_sugerida"][:200],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _perfil_a_texto(perfil: object | None) -> str:
    if perfil is None:
        return "Sin perfil opositor cargado — usar análisis neutral."
    # PerfilOpositorDespacho tiene atributos textuales; tomamos los útiles.
    partes: list[str] = []
    for attr in (
        "ideologia",
        "areas_prioritarias",
        "estilo_comunicacional",
        "lineas_rojas",
    ):
        v = getattr(perfil, attr, None)
        if v:
            if isinstance(v, list):
                partes.append(f"{attr}: {', '.join(map(str, v))}")
            else:
                partes.append(f"{attr}: {v}")
    return "\n".join(partes) or "Perfil sin datos significativos."


def _armar_prompt(
    *,
    comision: ComisionHcdn,
    reunion: ReunionComision,
    texto_pdf: str,
    expedientes_pdf: list[str],
    perfil_opositor_texto: str,
) -> tuple[str, str]:
    system = (
        "Sos un asesor parlamentario senior, experto en análisis político "
        "argentino. Tu tarea: enriquecer la convocatoria de una reunión de "
        "comisión con análisis útil para que el despacho del legislador "
        "decida cómo actuar. Devolvé JSON estricto sin texto fuera del "
        "objeto, sin markdown."
    )

    secciones_user: list[str] = []
    secciones_user.append(f"COMISIÓN: {comision.nombre}")
    secciones_user.append(f"FECHA: {reunion.fecha.isoformat()}")
    if reunion.hora:
        secciones_user.append(f"HORA: {reunion.hora.strftime('%H:%M')}")
    if reunion.sala:
        secciones_user.append(f"LUGAR: {reunion.sala}")
    if reunion.descripcion:
        secciones_user.append(f"DESCRIPCIÓN HTML:\n{reunion.descripcion}")
    if reunion.comisiones_invitadas:
        secciones_user.append(
            "COMISIONES INVITADAS: " + "; ".join(reunion.comisiones_invitadas),
        )
    if expedientes_pdf:
        secciones_user.append(
            "EXPEDIENTES DETECTADOS EN PDF: " + ", ".join(expedientes_pdf),
        )
    if texto_pdf:
        secciones_user.append(
            "TEXTO DEL PDF DE CITACIÓN (puede contener orden del día):\n"
            + texto_pdf,
        )
    secciones_user.append(
        "PERFIL OPOSITOR DEL DESPACHO QUE DEBE DECIDIR:\n"
        + perfil_opositor_texto,
    )
    secciones_user.append(
        "\nDEVOLVÉ JSON con esta forma exacta:\n"
        "{\n"
        '  "tema_corto": "1 oración explicando de qué se trata la reunión en lenguaje claro, sin jerga",\n'
        '  "tipo_reunion": "Informativa / Dictamen / Plenario / Conjunta / Constitutiva / Otra",\n'
        '  "convocada_por": "Quién la convocó (presidencia? bloque? emplazamiento del pleno?)",\n'
        '  "expedientes_citados": ["lista de expedientes en notación HCDN ej 1234-D-2025"],\n'
        '  "oportunidad_politica": "2-3 oraciones sobre cómo el despacho puede aprovechar políticamente esta reunión",\n'
        '  "accion_sugerida": "1 oración con acción concreta: cofirmar / pedir informes / declaración / dictamen alternativo / silencio estratégico / etc"\n'
        "}"
    )
    return system, "\n\n".join(secciones_user)


def _parsear_respuesta(texto: str) -> dict[str, object]:
    """Tolerante a fences ```json / texto extra: extrae el JSON ".

    Si nada parsea, devuelve campos vacíos en vez de romper.
    """
    fallback: dict[str, object] = {
        "tema_corto": "",
        "tipo_reunion": "",
        "convocada_por": "",
        "expedientes_citados": [],
        "oportunidad_politica": "",
        "accion_sugerida": "",
    }
    # Sacar fences ```json ... ```
    sin_fences = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.MULTILINE,
    ).strip()
    # Buscar el primer { ... } JSON.
    m = re.search(r"\{.*\}", sin_fences, flags=re.DOTALL)
    if not m:
        log.warning("enriquecer_reunion.no_json_en_respuesta")
        return fallback
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        log.warning("enriquecer_reunion.json_invalido: %s", exc)
        return fallback
    out: dict[str, object] = {}
    for k, default in fallback.items():
        v = data.get(k, default)
        # Coerciones defensivas.
        if isinstance(default, list):
            if isinstance(v, list):
                out[k] = [str(x) for x in v]
            elif isinstance(v, str) and v:
                out[k] = [s.strip() for s in v.split(",") if s.strip()]
            else:
                out[k] = []
        else:
            out[k] = str(v) if v is not None else ""
    return out
