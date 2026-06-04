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
    MAX_BAJADA_PROPIA_CHARS,
    AreaTematica,
    Articulo,
    ClasificacionArticuloResult,
    ClasificacionNormaBOResult,
    DisambiguacionMencion,
    Expediente,
    Legislador,
    NormaBO,
    TonoMencion,
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
    # Razonamiento libre (escape hatch para feat-42)
    # ------------------------------------------------------------------

    async def razonar_libre(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2000,
    ) -> tuple[str, str]:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text, self._model

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
    # Disambiguación de mención (JSON estructurado)
    # ------------------------------------------------------------------

    async def disambiguar_mencion(
        self,
        *,
        legislador: Legislador,
        alias_matcheado: str,
        snippet: str,
        titulo_articulo: str,
    ) -> DisambiguacionMencion:
        # Snippet ya viene capado a ≤200 chars (más elipsis) por el
        # detector regex; lo cortamos por seguridad si excede.
        snippet_seguro = snippet[:300]
        bloque = legislador.bloque.nombre
        prompt = f"""\
Tenemos que decidir DOS cosas sobre la siguiente mención en una nota
periodística:

1. ¿El texto se refiere a ESTE legislador, o a un homónimo (otra
   persona, una empresa con el mismo apellido, etc.)?
2. ¿Cuál es el tono hacia el legislador? Una de: positivo, neutro,
   negativo.

Tu salida debe ser EXCLUSIVAMENTE un JSON válido con este esquema:
{{
  "es_el_legislador": true|false,
  "tono": "positivo"|"neutro"|"negativo",
  "confianza_tono": 0.0-1.0,
  "razon": "máx 200 chars, en castellano, sin floreo"
}}

REGLAS:
- "es_el_legislador" = false si el snippet sugiere claramente otro
  referente (ej. una S.A., un actor/futbolista homónimo, un homónimo
  político en otra cámara o distrito). En caso de duda, devolvé true:
  el flujo posterior puede revisarlo. Pero si hay señales contrarias
  fuertes, devolvé false.
- "tono" hacia el legislador:
  - "positivo": lo destacan, acompañan, presentan logro.
  - "negativo": lo critican, denuncian, cuestionan, acusan.
  - "neutro": mención informativa sin valoración clara.
- "confianza_tono" refleja qué tan claro está el tono (0.5 = duda
  alta, 0.9 = muy claro).
- "razon" justifica las dos decisiones en una frase ≤200 chars.
- Sin ```json``` fences, sin texto fuera del JSON.

CONTEXTO DEL LEGISLADOR (al que estamos rastreando):
- Nombre completo: {legislador.nombre} {legislador.apellido}
- Cámara: {legislador.camara.value}
- Bloque: {bloque}
- Distrito: {legislador.distrito}

ALIAS QUE MATCHEÓ EL REGEX: "{alias_matcheado}"

TÍTULO DEL ARTÍCULO: {titulo_articulo}

SNIPPET DEL ARTÍCULO (≤200 chars de contexto alrededor del match):
{snippet_seguro}
"""
        respuesta = await self._call_text(prompt, max_tokens=300)
        return _parsear_disambiguacion_mencion(respuesta)

    # ------------------------------------------------------------------
    # Bajada propia de artículo (texto plano)
    # ------------------------------------------------------------------

    async def generar_bajada_propia(
        self,
        articulo: Articulo,
        *,
        texto_articulo: str,
    ) -> str:
        # Capamos el cuerpo para no inflar tokens. 4000 chars cubren
        # un artículo típico de medios argentinos.
        cuerpo = texto_articulo.strip()[:4000] or "(sin texto disponible)"
        prompt = f"""\
Escribí UNA sola oración informativa que resuma qué pasa en este
artículo. Va a aparecer como bajada propia en una app de monitoreo
para asesores parlamentarios — el lector ya vio el título y quiere
saber el QUÉ concreto en 5 segundos.

REGLAS:
- Máximo {MAX_BAJADA_PROPIA_CHARS} caracteres (es duro: contalos).
- Castellano rioplatense neutro, estilo Reuters/AFP. Cero opinión,
  cero adjetivos cargados, cero comillas dramáticas.
- NO parafrasees el título — agregá información del cuerpo.
- Sin "el artículo dice", "según el medio", "reportan que". Decí el
  hecho directo.
- Sin punto final si te ayuda a ahorrar chars.
- Devolvé SOLO la oración. Sin titular, sin comillas envolventes,
  sin etiqueta "Bajada:".

TÍTULO DEL ARTÍCULO: {articulo.titulo}

CUERPO (≤4000 chars):
{cuerpo}
"""
        respuesta = await self._call_text(prompt, max_tokens=200)
        return _limpiar_y_cap_bajada(respuesta, MAX_BAJADA_PROPIA_CHARS)

    # ------------------------------------------------------------------
    # Clasificación de artículo (JSON)
    # ------------------------------------------------------------------

    async def clasificar_articulo(
        self,
        articulo: Articulo,
        *,
        texto_articulo: str,
    ) -> ClasificacionArticuloResult:
        cuerpo = texto_articulo.strip()[:4000] or "(sin texto disponible)"
        prompt = f"""\
Clasificá el siguiente artículo en UNA de estas áreas temáticas:
{", ".join(_AREAS_VALIDAS)}

Tu salida debe ser EXCLUSIVAMENTE un JSON válido con este esquema:
{{
  "area_tematica": "una de las áreas listadas",
  "palabras_clave": ["3 a 5 tokens en minúsculas, sin tilde, sin puntuación"]
}}

REGLAS:
- "area_tematica" debe ser EXACTAMENTE una de las áreas listadas.
  Si no encaja claramente en ninguna, devolvé "otros".
- "palabras_clave" son los conceptos clave del artículo — no copies
  palabras del título textualmente, abstraé el tema.
- NO incluyas texto adicional fuera del JSON. Sin ```json``` fences.

TÍTULO: {articulo.titulo}

CUERPO (≤4000 chars):
{cuerpo}
"""
        respuesta = await self._call_text(prompt, max_tokens=200)
        return _parsear_clasificacion_articulo(respuesta)

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


def _limpiar_y_cap_bajada(respuesta: str, max_chars: int) -> str:
    """Saca cualquier wrapping del modelo y capa a `max_chars`.

    El modelo a veces devuelve la bajada envuelta en comillas o
    precedida de "Bajada: ". Limpiamos y agregamos elipsis si
    cortamos a la fuerza.
    """
    texto = respuesta.strip()
    # Saca prefijos típicos.
    texto = re.sub(r"^(bajada|resumen)\s*:\s*", "", texto, flags=re.IGNORECASE)
    # Saca comillas envolventes (rectas y tipográficas).
    if len(texto) >= 2 and texto[0] in '"“«' and texto[-1] in '"”»':
        texto = texto[1:-1].strip()
    # Saca espacios duplicados y salto de línea.
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) <= max_chars:
        return texto
    # Cortamos cuidando no terminar a la mitad de una palabra si se puede.
    cortado = texto[: max_chars - 1].rstrip()
    espacio = cortado.rfind(" ")
    if espacio > max_chars - 30:
        cortado = cortado[:espacio].rstrip(" ,;:.")
    return f"{cortado}…"


def _parsear_clasificacion_articulo(
    respuesta: str,
) -> ClasificacionArticuloResult:
    """Parsea JSON con fallback conservador.

    Si el modelo se va al pasto → área OTROS + lista vacía. El caller
    persiste igual y lo marca para revisión.
    """
    texto = respuesta.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    fallback = ClasificacionArticuloResult(
        area_tematica=AreaTematica.OTROS,
        palabras_clave=[],
    )

    try:
        data = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback

    area_raw = str(data.get("area_tematica", "otros")).strip().lower()
    try:
        area = AreaTematica(area_raw)
    except ValueError:
        area = AreaTematica.OTROS

    palabras = data.get("palabras_clave", [])
    if not isinstance(palabras, list):
        palabras = []
    palabras = [str(p).strip() for p in palabras if str(p).strip()][:5]

    return ClasificacionArticuloResult(
        area_tematica=area,
        palabras_clave=palabras,
    )


def _parsear_disambiguacion_mencion(respuesta: str) -> DisambiguacionMencion:
    """Parsea la respuesta JSON con fallback conservador.

    Si el modelo se va al pasto (no JSON, claves faltantes, valores
    fuera de rango), devolvemos un default seguro: `es_el_legislador=
    True` (porque preferimos no descartar menciones legítimas por un
    parsing fallido) + tono neutro + confianza 0.5. El caller
    persiste igual y lo marca para revisión humana.
    """
    texto = respuesta.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    fallback = DisambiguacionMencion(
        es_el_legislador=True,
        tono=TonoMencion.NEUTRO,
        confianza_tono=0.5,
        razon="LLM no devolvió JSON parseable; default conservador.",
    )

    try:
        data = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback

    es_el = bool(data.get("es_el_legislador", True))

    tono_raw = str(data.get("tono", "neutro")).strip().lower()
    try:
        tono = TonoMencion(tono_raw)
    except ValueError:
        tono = TonoMencion.NEUTRO

    try:
        confianza = float(data.get("confianza_tono", 0.5))
    except (TypeError, ValueError):
        confianza = 0.5
    confianza = max(0.0, min(1.0, confianza))

    razon = str(data.get("razon", "")).strip()[:200] or "(sin razón)"

    return DisambiguacionMencion(
        es_el_legislador=es_el,
        tono=tono,
        confianza_tono=confianza,
        razon=razon,
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
