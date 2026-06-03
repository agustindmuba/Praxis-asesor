"""AnthropicLlmProvider — implementación real del LlmProvider con Claude.

Spec 13 + 14. Tres métodos:
- generar_resumen_ejecutivo: 3 bullets markdown sobre un Expediente.
- clasificar_area_tematica: una AreaTematica del set fijo de 12.
- generar_argumentos: 2-3 bullets a favor (o contraargumentos esperables).

Prompt caching: la parte estable del system prompt (rol + instrucciones)
se marca con `cache_control: ephemeral`. Las requests subsiguientes
dentro de los 5 minutos siguientes leen del cache a 1/10 del costo del
input regular. El input específico del expediente NO se cachea (cambia
en cada call).

Modelo default: `claude-sonnet-4-5-20250929`. Configurable vía
`Settings.anthropic_model`. Para abaratar a expensas de calidad,
configurar Haiku.

Errores: la API puede tirar varios errores (rate limit, overloaded,
auth). En v1 los dejamos burbujear como Exception genéricas para que
el caller (el use case) los maneje. Una iteración futura podría mapear
a `FuenteNoDisponible` o similar.
"""

from __future__ import annotations

import json
import re
from typing import Any

from anthropic import AsyncAnthropic

from praxis.application.ports import LlmProvider
from praxis.domain import (
    AreaTematica,
    ClasificacionNormaBOResult,
    Expediente,
    NormaBO,
)

# Las 12 áreas, cada una en una sola línea para que el modelo no se
# confunda con guiones inconsistentes.
_AREAS_VALIDAS = [a.value for a in AreaTematica]


# System prompt cacheado: rol + estilo + reglas comunes. Lo dejamos
# en una sola string que se manda como bloque con cache_control.
_SYSTEM_PROMPT_BASE = """\
Sos un analista parlamentario senior que asesora a un despacho del Congreso Argentino.
Tu rol es producir contenido conciso, fácticamente sólido y políticamente útil para
un jefe de asesores que tiene 30 minutos para preparar su sesión.

Estilo:
- Castellano rioplatense neutro, profesional pero no acartonado.
- Frases cortas. Sin floreo. Sin "es importante destacar que...".
- Datos concretos cuando los tengas; si no, evitás inventarlos.
- Cero alucinaciones: si no sabés algo, lo decís.

Formato:
- Cuando te pidan bullets, devolvés exactamente la cantidad pedida,
  uno por línea, sin numeración y sin asteriscos al inicio.
- Cuando te pidan una clasificación, devolvés UNA sola palabra del set
  permitido, sin explicación adicional.
- Cuando te pidan markdown estructurado, respetás los headings que se
  especifiquen y nada más.
"""


class AnthropicLlmProvider(LlmProvider):
    """LlmProvider real contra la API de Anthropic.

    Se inyecta solo si `Settings.anthropic_api_key` está seteada (ver
    `praxis.api.deps.LlmProviderDep`). Sino se usa `FakeLlmProvider`.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def nombre_modelo(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Resumen ejecutivo (3 bullets markdown)
    # ------------------------------------------------------------------

    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str:
        autor = expediente.autor_principal
        autor_txt = (
            f"{autor.nombre} ({autor.bloque or 'sin bloque'}"
            f"{', ' + autor.distrito if autor.distrito else ''})"
            if autor
            else "sin firmantes registrados"
        )
        eventos = len(expediente.tramite)
        prompt = f"""\
Generá un resumen ejecutivo del siguiente expediente parlamentario para
un asesor que necesita decidir en 2 minutos si vale la pena leerlo entero.

Formato (markdown, exactamente 3 bullets, sin titular ni epílogo):
**Qué propone:** una frase clara explicando el contenido principal.
**Quién lo impulsa:** primer firmante con bloque/distrito, mención si tiene cofirmantes.
**Probabilidad de avance:** evaluación honesta del estado actual.

DATOS DEL EXPEDIENTE:
- Número: {expediente.numero}
- Tipo: {expediente.tipo.value}
- Título: {expediente.titulo}
- Sumario: {expediente.sumario or '(sin sumario en la fuente)'}
- Estado actual: {expediente.estado.value}
- Autor principal: {autor_txt}
- Cantidad de firmantes: {len(expediente.firmantes)}
- Eventos de trámite registrados: {eventos}
- Fecha de caducidad estimada: {expediente.fecha_caducidad or '(sin estimar)'}
"""
        return await self._call_text(prompt)

    # ------------------------------------------------------------------
    # Clasificación temática (1 palabra)
    # ------------------------------------------------------------------

    async def clasificar_area_tematica(
        self, expediente: Expediente,
    ) -> AreaTematica:
        prompt = f"""\
Clasificá el siguiente expediente en UNA de estas áreas:
{", ".join(_AREAS_VALIDAS)}

Devolvé exactamente una palabra del set anterior. Si no encaja claramente
en ninguna, devolvé "otros".

DATOS DEL EXPEDIENTE:
- Título: {expediente.titulo}
- Sumario: {expediente.sumario or '(sin sumario)'}
- Tipo: {expediente.tipo.value}
"""
        respuesta = await self._call_text(prompt, max_tokens=20)
        # Normalizar la respuesta.
        token = re.sub(r"[^a-záéíóúñ_]", "", respuesta.lower().strip())
        for area in AreaTematica:
            if area.value == token:
                return area
        # Fallback: el modelo devolvió algo fuera del set.
        return AreaTematica.OTROS

    # ------------------------------------------------------------------
    # Argumentos / contraargumentos (bullets)
    # ------------------------------------------------------------------

    async def generar_argumentos(
        self,
        expediente: Expediente,
        *,
        contraargumentos: bool = False,
    ) -> list[str]:
        autor = expediente.autor_principal
        autor_txt = (
            f"{autor.nombre} ({autor.bloque or 'sin bloque'})"
            if autor
            else "autor desconocido"
        )

        if contraargumentos:
            instruccion = (
                "Generá 2 contraargumentos políticamente esperables que el "
                "bloque rival va a usar para oponerse al proyecto. Pensá "
                "como quien va a votar en CONTRA y necesita argumentos sólidos."
            )
            cantidad = 2
        else:
            instruccion = (
                "Generá 3 argumentos a favor del proyecto que el despacho del "
                "autor (o un cofirmante) pueda usar en su exposición de bloque. "
                "Pensá como asesor del autor: argumentos persuasivos y "
                "consistentes con la línea política."
            )
            cantidad = 3

        prompt = f"""\
{instruccion}

REGLAS:
- Exactamente {cantidad} bullets, uno por línea.
- Sin numeración, sin asteriscos iniciales, sin titular.
- Cada bullet debe ser una frase autónoma de 1-2 oraciones.
- Apoyate en lo que sabés del contexto político argentino actual,
  pero sin inventar datos numéricos.

CONTEXTO DEL PROYECTO:
- Número: {expediente.numero}
- Título: {expediente.titulo}
- Sumario: {expediente.sumario or '(sin sumario)'}
- Estado actual: {expediente.estado.value}
- Autor: {autor_txt}
- Tipo: {expediente.tipo.value}
"""
        texto = await self._call_text(prompt, max_tokens=600)
        bullets = _parsear_bullets(texto, max_bullets=cantidad)
        return bullets

    # ------------------------------------------------------------------
    # Clasificación de norma BO (JSON estructurado)
    # ------------------------------------------------------------------

    async def clasificar_norma_bo(
        self,
        norma: NormaBO,
        *,
        texto: str | None = None,
    ) -> ClasificacionNormaBOResult:
        # Capamos el texto para no inflar tokens. 3000 chars cubren la
        # mayoría de los decretos típicos del BO sin exceder el cap.
        cuerpo = (texto or "")[:3000]
        prompt = f"""\
Clasificá la siguiente norma del Boletín Oficial argentino.

Tu salida debe ser EXCLUSIVAMENTE un JSON válido con este esquema:
{{
  "area_tematica": "una de: {', '.join(_AREAS_VALIDAS)}",
  "palabras_clave": ["3 a 7 tokens en castellano, en minúscula, sin puntuación"],
  "afecta_expedientes_hcdn": true|false,
  "referencias_legales": ["Ley NNN", "Decreto NNN/AAAA", ...]
}}

REGLAS:
- "area_tematica" debe ser EXACTAMENTE una de las 12 áreas listadas.
  Si la norma no encaja claro, devolvé "otros".
- "afecta_expedientes_hcdn" = true si la norma menciona explícitamente
  una ley vigente, un expediente parlamentario o un proyecto en HCDN/HSN
  que un despacho podría estar siguiendo. Por defecto false.
- "referencias_legales" enumera leyes/decretos/resoluciones que la norma
  cita explícitamente (no inventes; si no hay, devolvé []).
- NO incluyas texto adicional fuera del JSON. Sin ```json``` fences,
  sin explicación previa ni posterior.

DATOS DE LA NORMA:
- Tipo: {norma.tipo_norma}
- Número: {norma.numero_norma}
- Organismo emisor: {norma.organismo_emisor}
- Sumario: {norma.sumario}
- Texto del cuerpo (recortado a 3000 chars):
{cuerpo or '(sin texto disponible)'}
"""
        respuesta = await self._call_text(prompt, max_tokens=400)
        return _parsear_clasificacion_norma_bo(respuesta)

    # ------------------------------------------------------------------
    # Helper común: llamada a la API con prompt caching
    # ------------------------------------------------------------------

    async def _call_text(self, user_prompt: str, *, max_tokens: int = 500) -> str:
        """Llamada estándar con system cacheado. Devuelve solo el texto."""
        message: Any = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT_BASE,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        # message.content es lista de bloques; agarramos el texto del primero.
        if not message.content:
            return ""
        bloque = message.content[0]
        return getattr(bloque, "text", "")


# ---------------------------------------------------------------------------
# Helpers locales
# ---------------------------------------------------------------------------


def _parsear_clasificacion_norma_bo(
    respuesta: str,
) -> ClasificacionNormaBOResult:
    """Parsea la respuesta JSON del modelo, con fallback defensivo.

    Si el modelo devuelve texto envuelto en fences ```json``` los saca.
    Si falla el parseo o el JSON está incompleto, devuelve un default
    conservador (area=OTROS, listas vacías, sin afectación) en lugar de
    levantar — el clasificador no es bloqueante para el resto del flujo.
    """
    texto = respuesta.strip()
    # Sacar fences ```json ... ``` si el modelo los pone igual.
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    try:
        data = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return ClasificacionNormaBOResult(
            area_tematica=AreaTematica.OTROS,
            palabras_clave=[],
            afecta_expedientes_hcdn=False,
            referencias_legales=[],
        )

    # Area: normalizar y validar contra el enum.
    area_raw = str(data.get("area_tematica", "otros")).strip().lower()
    try:
        area = AreaTematica(area_raw)
    except ValueError:
        area = AreaTematica.OTROS

    palabras = data.get("palabras_clave", [])
    if not isinstance(palabras, list):
        palabras = []
    palabras = [str(p).strip() for p in palabras if str(p).strip()]

    referencias = data.get("referencias_legales", [])
    if not isinstance(referencias, list):
        referencias = []
    referencias = [str(r).strip() for r in referencias if str(r).strip()]

    afecta = bool(data.get("afecta_expedientes_hcdn", False))

    return ClasificacionNormaBOResult(
        area_tematica=area,
        palabras_clave=palabras,
        afecta_expedientes_hcdn=afecta,
        referencias_legales=referencias,
    )


def _parsear_bullets(texto: str, *, max_bullets: int) -> list[str]:
    """Convierte el output del LLM en una lista de bullets limpios.

    Acepta líneas con / sin viñeta (`-`, `*`, `•`, números). Saca
    prefijos, espacios y líneas vacías.
    """
    out: list[str] = []
    for raw in texto.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Sacar viñetas / numeración del inicio.
        line = re.sub(r"^[-*•·]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        # Asteriscos de markdown bold si quedaron sueltos.
        line = re.sub(r"^\*+\s*", "", line)
        if line:
            out.append(line)
        if len(out) >= max_bullets:
            break
    return out
