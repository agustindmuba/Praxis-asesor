"""Caso de uso: detectar menciones de legisladores en un artículo (feat-40.3).

Pipeline (spec 16 D6 + ADR 0009):

1. Por cada legislador a monitorear (= padrón filtrado por suscripción
   del despacho):
   1.1. Pase 1 — regex: `detectar_candidatos()` sobre el texto del
        artículo. Devuelve `list[CandidatoMencion]` con
        `confianza_regex` y `snippet_contexto` ≤200 chars.
   1.2. Pase 2 — LLM: por cada candidato, `LlmProvider.disambiguar_mencion()`
        decide si es ESE legislador (no homónimo) y clasifica el tono.
   1.3. Si `es_el_legislador=False` → descartar candidato.
   1.4. Si `es_el_legislador=True` → construir `Mencion` con snippet
        cap ≤MAX_SNIPPET_CONTEXTO_CHARS + `tono` + `confianza_tono`.
2. Dedup por `(articulo_id, legislador_id, despacho_id)`: si el regex
   matcheó varias veces al mismo legislador, nos quedamos con la
   mención de mayor confianza combinada (`confianza_regex *
   confianza_tono`). El resto se descarta.

El caso de uso NO persiste — devuelve `list[Mencion]` listas para que
el caller (Celery task `detectar_menciones_en_articulo`) las guarde
vía `MencionRepository.crear_lote`.

Restricción legal: el texto del artículo se recibe por parámetro
(in-memory, ADR 0006) y NUNCA se persiste. Sólo viven el snippet
≤200 chars de cada `Mencion` y la bajada propia ≤240 chars.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from praxis.application.ports import LlmProvider
from praxis.application.services import detectar_candidatos
from praxis.domain import (
    MAX_SNIPPET_CONTEXTO_CHARS,
    AlcanceMedio,
    Articulo,
    Legislador,
    Mencion,
    TonoMencion,
)


@dataclass(frozen=True, slots=True)
class LegisladorAMonitorear:
    """Wrapper de un legislador suscripto por un despacho.

    El caller (Celery task) resuelve `legislador_id` y `despacho_id`
    contra la DB (no son atributos naturales del padrón).

    `aliases_extra` son apodos / Twitter handles que el despacho
    cargó en su perfil. Los pasamos al detector regex como matches
    adicionales con `confianza_regex=0.9`.
    """

    legislador: Legislador
    legislador_id: UUID
    despacho_id: UUID
    aliases_extra: list[str] = field(default_factory=list)


class DetectarMencionesEnArticulo:
    """Caso de uso: regex + LLM disambiguator sobre un artículo.

    Inyectado con un `LlmProvider`. NO toca la DB. Lo orquesta una
    Celery task que, por cada artículo nuevo:
    - Resuelve los legisladores suscriptos por los despachos activos.
    - Baja el texto del artículo en memoria con `FuenteNoticias.
      obtener_texto_articulo()`.
    - Llama `ejecutar(...)` para obtener las menciones.
    - Las persiste vía `MencionRepository.crear_lote`.
    """

    def __init__(self, *, llm: LlmProvider) -> None:
        self._llm = llm

    async def ejecutar(
        self,
        *,
        articulo: Articulo,
        texto_articulo: str,
        legisladores: list[LegisladorAMonitorear],
        alcance_medio: AlcanceMedio,
        ahora: datetime | None = None,
    ) -> list[Mencion]:
        """Devuelve la lista de menciones confirmadas (sin persistir).

        Args:
            articulo: artículo con `id` ya persistido (snapshot).
            texto_articulo: cuerpo bajado en memoria. NO se persiste.
            legisladores: legisladores a monitorear con su UUID +
                despacho + aliases extra del perfil del despacho.
            alcance_medio: del `FuenteNoticia` (catálogo fijo, D7).
            ahora: timestamp UTC para `detectado_en`. Default
                `datetime.now(UTC)` — parametrizable para tests.
        """
        if articulo.id is None:
            raise ValueError(
                "DetectarMencionesEnArticulo exige articulo.id persistido",
            )
        if not texto_articulo.strip():
            return []

        ts = ahora or datetime.now(UTC)
        articulo_id: UUID = articulo.id
        menciones: list[Mencion] = []

        for slot in legisladores:
            mejores = await self._procesar_legislador(
                articulo_id=articulo_id,
                texto_articulo=texto_articulo,
                titulo_articulo=articulo.titulo,
                slot=slot,
                alcance_medio=alcance_medio,
                ahora=ts,
            )
            menciones.extend(mejores)

        return menciones

    async def _procesar_legislador(
        self,
        *,
        articulo_id: UUID,
        texto_articulo: str,
        titulo_articulo: str,
        slot: LegisladorAMonitorear,
        alcance_medio: AlcanceMedio,
        ahora: datetime,
    ) -> list[Mencion]:
        """Procesa un legislador: regex → LLM → dedup → 0/1 Mencion.

        Devuelve a lo sumo UNA `Mencion` por `(articulo, legislador,
        despacho)`. La spec 16 trata "el artículo X menciona al
        legislador Y" como un único evento de alerta, aunque el regex
        haya matcheado varias posiciones.
        """
        nombre_completo = (
            f"{slot.legislador.nombre} {slot.legislador.apellido}".strip()
        )
        candidatos = detectar_candidatos(
            texto_articulo,
            nombre_completo=nombre_completo,
            apellido=slot.legislador.apellido,
            aliases_extra=slot.aliases_extra,
        )
        if not candidatos:
            return []

        # Confirmar + clasificar tono por candidato. Quedamos con el
        # mejor (mayor confianza combinada). Si NINGUNO es confirmado
        # por el LLM, no construimos Mencion.
        mejor_score = -1.0
        mejor_snippet = ""
        mejor_confianza_tono = 0.0
        mejor_tono = TonoMencion.NEUTRO
        for cand in candidatos:
            snippet_capado = _capar_snippet(cand.snippet)
            disamb = await self._llm.disambiguar_mencion(
                legislador=slot.legislador,
                alias_matcheado=cand.alias_matcheado,
                snippet=snippet_capado,
                titulo_articulo=titulo_articulo,
            )
            if not disamb.es_el_legislador:
                continue
            score = cand.confianza_regex * disamb.confianza_tono
            if score > mejor_score:
                mejor_score = score
                mejor_snippet = snippet_capado
                mejor_confianza_tono = disamb.confianza_tono
                mejor_tono = disamb.tono

        if mejor_score < 0:
            return []

        return [
            Mencion(
                id=None,
                articulo_id=articulo_id,
                legislador_id=slot.legislador_id,
                despacho_id=slot.despacho_id,
                snippet_contexto=mejor_snippet,
                tono=mejor_tono,
                confianza_tono=mejor_confianza_tono,
                alcance_medio=alcance_medio,
                detectado_en=ahora,
                notificada=False,
            ),
        ]


def _capar_snippet(snippet: str) -> str:
    """Capa al `MAX_SNIPPET_CONTEXTO_CHARS` del dominio.

    El detector regex devuelve ~200 chars con elipsis; algunos casos
    de borde pueden quedar un pelo más largos por la elipsis. Cortamos
    en seco preservando la elipsis si la había.
    """
    snippet = snippet.strip()
    if len(snippet) <= MAX_SNIPPET_CONTEXTO_CHARS:
        return snippet
    # Cortamos y reagregamos elipsis al final si la sacamos.
    cortado = snippet[: MAX_SNIPPET_CONTEXTO_CHARS - 1].rstrip()
    return f"{cortado}…"
