"""Caso de uso: procesar artículos nuevos de una FuenteNoticia.

Pipeline end-to-end (feat-40.5 / spec 16):

1. `FuenteNoticias.listar_articulos_nuevos(fuente, desde=...)` →
   `list[Articulo]` candidatos.
2. Por cada artículo candidato:
   2.1. Dedup forever via `ArticuloHashRepository.existe(hash_dedup)`:
        si ya estaba, se omite (ni siquiera se baja el texto).
   2.2. `ArticuloRepository.upsert_lote([art])` persiste el snapshot.
        UNIQUE en hash_dedup hace este paso idempotente cross-corrida.
   2.3. `FuenteNoticias.obtener_texto_articulo(persistido)` baja el
        cuerpo a MEMORIA. ADR 0006 — el cuerpo NO se persiste.
   2.4. Si el cuerpo está vacío / excepción → se registra el hash
        igual (para no reintentarlo) y se sigue con el siguiente.
   2.5. `LlmProvider.generar_bajada_propia(...)` →
        `ArticuloRepository.actualizar_bajada_propia(...)`.
   2.6. `LlmProvider.clasificar_articulo(...)` →
        `ClasificacionArticuloRepository.crear(ClasificacionArticulo)`.
        Hidrata `modelo`/`prompt_version` con `llm.nombre_modelo` y
        `NOTICIA_PROMPT_VERSION`.
   2.7. Por cada despacho suscripto:
        - `DetectarMencionesEnArticulo.ejecutar(...)` (caso de uso de
          feat-40.3) — regex + LLM disambiguator.
        - `MencionRepository.crear_lote(...)`. Idempotente.
        - `_calcular_score_relevancia(...)` con perfil + clasif +
          fuente + bool de menciones.
        - Si `score >= SCORE_MINIMO_ARTICULO_RELEVANTE` →
          `ArticuloRelevanteRepository.upsert(...)`.
   2.8. `ArticuloHashRepository.registrar(hash)` — dedup forever
        (sobrevive a la purga del artículo a los 12 meses, D10).
3. `FuenteNoticiaRepository.marcar_revisada(fuente.id, momento=ahora)`.
4. Devuelve estadísticas para logging del Celery task.

El caso de uso NO commitea — la Celery task le pasa la session y
hace el commit al final (atomicidad por fuente). Si falla un
artículo puntual, el caso de uso captura la excepción, la suma a
`errores` y sigue con los demás.

Ver `docs/specs/16-briefing-noticias-y-menciones.md` §"Pipeline".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from praxis.application.ports import (
    ArticuloHashRepository,
    ArticuloRelevanteRepository,
    ArticuloRepository,
    ClasificacionArticuloRepository,
    FuenteNoticiaRepository,
    FuenteNoticias,
    LlmProvider,
    MencionRepository,
)
from praxis.application.use_cases.detectar_menciones_en_articulo import (
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
)
from praxis.domain import (
    NOTICIA_PROMPT_VERSION,
    Articulo,
    ArticuloRelevante,
    ClasificacionArticulo,
    FuenteNoticia,
    PerfilInteresDespacho,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inputs / outputs del caso de uso
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DespachoSuscrito:
    """Datos del despacho que el Celery task resuelve antes de invocar.

    `perfil_interes` es opcional — si el despacho no tiene perfil
    sembrado, el score queda en 0 y NO se persiste ArticuloRelevante.
    """

    despacho_id: UUID
    perfil_interes: PerfilInteresDespacho | None
    legisladores: list[LegisladorAMonitorear]


@dataclass(frozen=True, slots=True)
class ResultadoProcesamiento:
    """Estadísticas para logging del Celery task."""

    articulos_descubiertos: int
    articulos_nuevos: int
    articulos_omitidos_por_dedup: int
    bajadas_generadas: int
    clasificaciones_persistidas: int
    menciones_creadas: int
    relevancias_persistidas: int
    fallidos: int
    errores: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pesos del scoring de relevancia (cap suave a 100)
# ---------------------------------------------------------------------------


SCORE_AREA_TEMATICA_MATCH = 35
SCORE_HAY_MENCION_LEGISLADOR = 35
SCORE_DISTRITO_DEL_LEGISLADOR = 20
SCORE_PALABRA_CLAVE_MATCH = 10
SCORE_MINIMO_ARTICULO_RELEVANTE = 30
SCORE_MAX = 100
MAX_RAZON_RELEVANCIA_CHARS = 200

# Cuántas excepciones distintas registramos en `errores` antes de cortar.
_MAX_ERRORES_EN_LOG = 5


# ---------------------------------------------------------------------------
# Caso de uso
# ---------------------------------------------------------------------------


class ProcesarArticulosDeFuente:
    """Pipeline end-to-end por fuente: descubrir → dedup → bajar
    texto → bajada propia → clasificar → menciones + scoring por
    despacho → marcar fuente revisada.
    """

    def __init__(
        self,
        *,
        fuente_adapter: FuenteNoticias,
        articulos: ArticuloRepository,
        hashes: ArticuloHashRepository,
        clasificaciones: ClasificacionArticuloRepository,
        menciones: MencionRepository,
        relevantes: ArticuloRelevanteRepository,
        fuentes: FuenteNoticiaRepository,
        llm: LlmProvider,
        detector_menciones: DetectarMencionesEnArticulo,
    ) -> None:
        self._adapter = fuente_adapter
        self._articulos = articulos
        self._hashes = hashes
        self._clasificaciones = clasificaciones
        self._menciones = menciones
        self._relevantes = relevantes
        self._fuentes = fuentes
        self._llm = llm
        self._detector = detector_menciones

    async def ejecutar(
        self,
        fuente: FuenteNoticia,
        *,
        desde: datetime,
        despachos: list[DespachoSuscrito],
        ahora: datetime | None = None,
    ) -> ResultadoProcesamiento:
        if fuente.id is None:
            raise ValueError("Fuente debe tener id persistido")
        ts = ahora or datetime.now(UTC)

        candidatos = await self._adapter.listar_articulos_nuevos(
            fuente, desde=desde,
        )
        stats = _StatsAcumulador(descubiertos=len(candidatos))

        for art_crudo in candidatos:
            try:
                await self._procesar_uno(
                    art_crudo=art_crudo,
                    fuente=fuente,
                    despachos=despachos,
                    stats=stats,
                    ahora=ts,
                )
            except Exception as exc:  # tolerancia por artículo
                stats.fallido(f"{art_crudo.url}: {exc}")
                log.warning(
                    "Falló procesamiento de %s en fuente %s: %s",
                    art_crudo.url, fuente.dominio, exc,
                )

        await self._fuentes.marcar_revisada(fuente.id, momento=ts)
        return stats.snapshot()

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    async def _procesar_uno(
        self,
        *,
        art_crudo: Articulo,
        fuente: FuenteNoticia,
        despachos: list[DespachoSuscrito],
        stats: _StatsAcumulador,
        ahora: datetime,
    ) -> None:
        # 2.1 Dedup forever.
        if await self._hashes.existe(art_crudo.hash_dedup):
            stats.omitido_por_dedup()
            return

        # 2.2 Persistir snapshot (upsert idempotente por hash UNIQUE).
        persistidos = await self._articulos.upsert_lote([art_crudo])
        if not persistidos:
            return
        articulo = persistidos[0]
        if articulo.id is None:  # defensivo
            return
        articulo_id: UUID = articulo.id  # narrowing para mypy
        stats.nuevo()

        # 2.3 Bajar texto en memoria.
        try:
            texto = await self._adapter.obtener_texto_articulo(articulo)
        except Exception as exc:
            log.info(
                "Sin texto para %s (%s); registro hash y sigo.",
                articulo.url, exc,
            )
            await self._hashes.registrar(articulo.hash_dedup)
            return

        if not texto.strip():
            await self._hashes.registrar(articulo.hash_dedup)
            return

        # 2.5 Bajada propia.
        bajada = await self._llm.generar_bajada_propia(
            articulo, texto_articulo=texto,
        )
        if bajada.strip():
            articulo = await self._articulos.actualizar_bajada_propia(
                articulo_id, bajada=bajada,
            )
            stats.bajada_generada()

        # 2.6 Clasificación (cache por articulo_id).
        clasif = await self._clasificaciones.buscar_por_articulo(articulo_id)
        if clasif is None:
            resultado = await self._llm.clasificar_articulo(
                articulo, texto_articulo=texto,
            )
            clasif = await self._clasificaciones.crear(
                ClasificacionArticulo(
                    id=None,
                    articulo_id=articulo_id,
                    area_tematica=resultado.area_tematica,
                    palabras_clave=resultado.palabras_clave,
                    modelo=self._llm.nombre_modelo,
                    prompt_version=NOTICIA_PROMPT_VERSION,
                    generado_en=ahora,
                ),
            )
            stats.clasificacion_persistida()

        # 2.7 Por cada despacho — menciones + score.
        for despacho in despachos:
            # Defendemos la invariante: el `despacho_id` que viaja en
            # cada `LegisladorAMonitorear` debe coincidir con el del
            # wrapper. Si el caller armó mal el wrapper, lo corregimos
            # acá para que la Mención persistida apunte al despacho
            # correcto.
            legisladores_norm = [
                LegisladorAMonitorear(
                    legislador=lam.legislador,
                    legislador_id=lam.legislador_id,
                    despacho_id=despacho.despacho_id,
                    aliases_extra=lam.aliases_extra,
                )
                for lam in despacho.legisladores
            ]
            menciones = await self._detector.ejecutar(
                articulo=articulo,
                texto_articulo=texto,
                legisladores=legisladores_norm,
                alcance_medio=fuente.alcance,
                ahora=ahora,
            )
            persistidas = await self._menciones.crear_lote(menciones)
            stats.menciones_creadas(len(persistidas))

            score, razon = calcular_score_relevancia(
                fuente=fuente,
                clasificacion=clasif,
                perfil=despacho.perfil_interes,
                hay_mencion_de_legislador=len(persistidas) > 0,
            )
            if score >= SCORE_MINIMO_ARTICULO_RELEVANTE:
                await self._relevantes.upsert(
                    ArticuloRelevante(
                        articulo_id=articulo_id,
                        despacho_id=despacho.despacho_id,
                        score=score,
                        razon=razon[:MAX_RAZON_RELEVANCIA_CHARS],
                        expedientes_tocados=[],
                        generado_en=ahora,
                    ),
                )
                stats.relevancia_persistida()

        # 2.8 Hash forever.
        await self._hashes.registrar(articulo.hash_dedup)


# ---------------------------------------------------------------------------
# Función pura: scoring de relevancia
# ---------------------------------------------------------------------------


def calcular_score_relevancia(
    *,
    fuente: FuenteNoticia,
    clasificacion: ClasificacionArticulo | None,
    perfil: PerfilInteresDespacho | None,
    hay_mencion_de_legislador: bool,
) -> tuple[int, str]:
    """Heurística determinística de relevancia (0-100).

    Suma de pesos:
    - Área temática del artículo en `perfil.areas_tematicas` → +35.
    - Hay alguna mención confirmada del legislador → +35.
    - Fuente distrital con distrito en `perfil.distritos_observados`
      → +20.
    - Palabra clave del artículo en `perfil.comisiones_legislador`
      (proxy v1) → +10.

    Sin perfil → 0. El umbral de persistencia es
    `SCORE_MINIMO_ARTICULO_RELEVANTE` (=30); el caller decide si
    descartar.

    Devuelve `(score 0-100, razon ≤200 chars)`. La razón se compone
    de las señales que sumaron.
    """
    if perfil is None:
        return 0, "Sin perfil de interés del despacho."

    score = 0
    razones: list[str] = []

    if (
        clasificacion is not None
        and clasificacion.area_tematica.value in perfil.areas_tematicas
    ):
        score += SCORE_AREA_TEMATICA_MATCH
        razones.append(f"área {clasificacion.area_tematica.value}")

    if hay_mencion_de_legislador:
        score += SCORE_HAY_MENCION_LEGISLADOR
        razones.append("menciona al legislador")

    if (
        fuente.distrito is not None
        and fuente.distrito in perfil.distritos_observados
    ):
        score += SCORE_DISTRITO_DEL_LEGISLADOR
        razones.append(f"distrito {fuente.distrito}")

    if clasificacion is not None and clasificacion.palabras_clave:
        palabras = {p.lower() for p in clasificacion.palabras_clave}
        proxies = {p.lower() for p in perfil.comisiones_legislador}
        if palabras & proxies:
            score += SCORE_PALABRA_CLAVE_MATCH
            comunes = sorted(palabras & proxies)[:2]
            razones.append("palabras clave: " + ", ".join(comunes))

    score = min(score, SCORE_MAX)
    razon = "; ".join(razones) if razones else "Sin señales fuertes."
    return score, razon[:MAX_RAZON_RELEVANCIA_CHARS]


# ---------------------------------------------------------------------------
# Acumulador interno de estadísticas
# ---------------------------------------------------------------------------


class _StatsAcumulador:
    """Mutable interno; al final devuelve un `ResultadoProcesamiento`
    inmutable."""

    def __init__(self, *, descubiertos: int) -> None:
        self._descubiertos = descubiertos
        self._nuevos = 0
        self._omitidos = 0
        self._bajadas = 0
        self._clasif = 0
        self._menciones = 0
        self._relevancias = 0
        self._fallidos = 0
        self._errores: list[str] = []

    def nuevo(self) -> None:
        self._nuevos += 1

    def omitido_por_dedup(self) -> None:
        self._omitidos += 1

    def bajada_generada(self) -> None:
        self._bajadas += 1

    def clasificacion_persistida(self) -> None:
        self._clasif += 1

    def menciones_creadas(self, n: int) -> None:
        self._menciones += n

    def relevancia_persistida(self) -> None:
        self._relevancias += 1

    def fallido(self, error: str) -> None:
        self._fallidos += 1
        if len(self._errores) < _MAX_ERRORES_EN_LOG:
            self._errores.append(error[:200])

    def snapshot(self) -> ResultadoProcesamiento:
        return ResultadoProcesamiento(
            articulos_descubiertos=self._descubiertos,
            articulos_nuevos=self._nuevos,
            articulos_omitidos_por_dedup=self._omitidos,
            bajadas_generadas=self._bajadas,
            clasificaciones_persistidas=self._clasif,
            menciones_creadas=self._menciones,
            relevancias_persistidas=self._relevancias,
            fallidos=self._fallidos,
            errores=list(self._errores),
        )
