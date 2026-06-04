"""Smoke end-to-end del pipeline de Noticias + Menciones (feat-40.7).

Corre el pipeline completo:

1. **Setup:** SQLite local `tmp_smoke_noticias.db`, crea tablas, seedea
   despacho Juliano + perfil de interés + 4 fuentes RSS reales.
2. **Pipeline:** por cada fuente, llama a `ProcesarArticulosDeFuente`
   con ventana `desde=ahora - 7 días`. El caso de uso:
   - baja el feed RSS real (red),
   - dedup por hash de URL,
   - baja texto de cada artículo nuevo (red, sin persistir cuerpo),
   - LLM `bajada_propia` + `clasificar_articulo`,
   - detector de menciones (regex + LLM disambiguator),
   - scoring de relevancia y persistencia de `ArticuloRelevante`.
3. **Reporte:** tabla por fuente con descubiertos / nuevos / menciones /
   relevancias + totales agregados.

Cap de seguridad: `--max-articulos-por-fuente N` envuelve el adapter
para no procesar más de N candidatos. Default 5 para limitar gasto LLM.

Modo por defecto: `--fake-llm` (sin gasto). Para gasto real pasar
`--llm-real` explícito. Default conservador a propósito.

Uso:
    PYTHONUTF8=1 uv run python -m scripts.smoke_noticias                # dry-run sin gasto
    PYTHONUTF8=1 uv run python -m scripts.smoke_noticias --llm-real     # gasta API
    PYTHONUTF8=1 uv run python -m scripts.smoke_noticias --llm-real --max-articulos-por-fuente 3

Salida: tabla por fuente + totales en STDOUT. Exit 0 si todo ok.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.application.ports import FuenteNoticias, LlmProvider
from praxis.application.use_cases import (
    DespachoSuscrito,
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
    ProcesarArticulosDeFuente,
)
from praxis.config import get_settings
from praxis.domain import (
    AlcanceMedio,
    Articulo,
    Camara,
    Despacho,
    FuenteNoticia,
    Legislador,
    ModoAccesoFuente,
    PerfilInteresDespacho,
    TipoFuenteNoticia,
)
from praxis.infrastructure.llm import FakeLlmProvider
from praxis.infrastructure.llm.anthropic_provider import AnthropicLlmProvider
from praxis.infrastructure.noticias.multi_adapter import (
    FuenteNoticiasMultiAdapter,
)
from praxis.infrastructure.padron import CsvPadronRepository
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloHashRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMencionRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)
from praxis.infrastructure.queue.tasks_noticias import legislador_uuid

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("smoke_noticias")
log.setLevel(logging.INFO)

DB_FILE = Path(__file__).resolve().parent.parent / "tmp_smoke_noticias.db"


# Fuentes RSS reales para el smoke. URLs estables conocidas. Si alguna
# falla, el pipeline tolera por fuente y sigue con las otras.
FUENTES_SEED: list[FuenteNoticia] = [
    FuenteNoticia(
        id=None,
        nombre="Infobae Política",
        dominio="infobae.com",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url=(
            "https://www.infobae.com/arc/outboundfeeds/rss/"
            "category/politica/?outputType=xml"
        ),
    ),
    FuenteNoticia(
        id=None,
        nombre="La Nación Política",
        dominio="lanacion.com.ar",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url=(
            "https://www.lanacion.com.ar/arc/outboundfeeds/rss/"
            "category/politica/?outputType=xml"
        ),
    ),
    FuenteNoticia(
        id=None,
        nombre="Clarín Política",
        dominio="clarin.com",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://www.clarin.com/rss/politica/",
    ),
    FuenteNoticia(
        id=None,
        nombre="Perfil",
        dominio="perfil.com",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://www.perfil.com/feed",
    ),
    FuenteNoticia(
        id=None,
        nombre="Parlamentario",
        dominio="parlamentario.com",
        tipo=TipoFuenteNoticia.POLITICO,
        alcance=AlcanceMedio.NICHO,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://www.parlamentario.com/feed/",
    ),
    FuenteNoticia(
        id=None,
        nombre="TN",
        dominio="tn.com.ar",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://tn.com.ar/feed/",
    ),
    FuenteNoticia(
        id=None,
        nombre="elDiarioAR",
        dominio="eldiarioar.com",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://eldiarioar.com/rss/",
    ),
    FuenteNoticia(
        id=None,
        nombre="La Voz del Interior (Política)",
        dominio="lavoz.com.ar",
        tipo=TipoFuenteNoticia.DISTRITAL,
        alcance=AlcanceMedio.PROVINCIAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://www.lavoz.com.ar/rss/politica.xml",
        distrito="Córdoba",
    ),
]


class FuenteNoticiasCapeado(FuenteNoticias):
    """Wrapper que limita la cantidad de candidatos por fuente.

    Útil para smoke: queremos validar el flujo end-to-end sin gastar
    LLM en 100+ artículos. Cortamos al N-ésimo candidato y delegamos
    el resto al adapter real.
    """

    def __init__(self, inner: FuenteNoticias, max_articulos: int) -> None:
        self._inner = inner
        self._max = max_articulos

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        items = await self._inner.listar_articulos_nuevos(fuente, desde=desde)
        if len(items) > self._max:
            log.info(
                "  [%s] %d candidatos descubiertos, capeando a %d.",
                fuente.dominio, len(items), self._max,
            )
        return items[: self._max]

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        return await self._inner.obtener_texto_articulo(articulo)


def _construir_llm(usar_fake: bool) -> LlmProvider:
    if usar_fake:
        log.info("Usando FakeLlmProvider (sin gasto).")
        return FakeLlmProvider()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY no seteada → cayendo a FakeLlmProvider.")
        return FakeLlmProvider()
    log.info("Usando AnthropicLlmProvider con %s", settings.anthropic_model)
    return AnthropicLlmProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )


def _enable_fk(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


async def _seed_despacho_y_fuentes(
    sessionmaker, padron: CsvPadronRepository,
) -> tuple[Despacho, PerfilInteresDespacho, list[FuenteNoticia], list[LegisladorAMonitorear]]:
    """Idempotente: si ya hay despacho/fuentes/perfil, los reusa."""
    async with sessionmaker() as session:
        despachos_repo = SqlAlchemyDespachoRepository(session)
        perfiles_repo = SqlAlchemyPerfilInteresDespachoRepository(session)
        fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)

        # Despacho.
        despachos = await despachos_repo.listar()
        if despachos:
            despacho = despachos[0]
            log.info("Reusando despacho %s (%s)", despacho.nombre, despacho.id)
        else:
            despacho = await despachos_repo.crear(
                Despacho(id=uuid4(), nombre="Despacho smoke (Juliano DPS)"),
            )
            log.info("Creado despacho %s (%s)", despacho.nombre, despacho.id)

        # Perfil de interés (idempotente vía upsert).
        perfil = PerfilInteresDespacho(
            despacho_id=despacho.id,
            areas_tematicas=["educacion", "justicia", "salud"],
            distritos_observados=["Buenos Aires"],
            aliases_legislador=["Pablo Juliano", "Juliano", "PJuliano"],
            sembrado_at=datetime.now(UTC),
        )
        await perfiles_repo.upsert(perfil)
        log.info(
            "Perfil sembrado: areas=%s distritos=%s aliases=%s",
            perfil.areas_tematicas,
            perfil.distritos_observados,
            perfil.aliases_legislador,
        )

        # Fuentes (idempotente por dominio).
        existentes = await fuentes_repo.listar_activas()
        existentes_dominios = {f.dominio for f in existentes}
        for seed in FUENTES_SEED:
            if seed.dominio in existentes_dominios:
                continue
            await fuentes_repo.crear(seed)
            log.info("Creada fuente %s", seed.dominio)
        fuentes = await fuentes_repo.listar_activas()

        await session.commit()

    # Resuelvo el legislador Juliano contra el padrón.
    legislador: Legislador | None = None
    for camara in (Camara.HCDN, Camara.HSN):
        try:
            legislador = padron.buscar_por_slug("pjuliano", camara)
            break
        except KeyError:
            continue
    if legislador is None:
        raise RuntimeError(
            "No encontré a Juliano en el padrón. ¿Está data/padron/?",
        )
    log.info(
        "Legislador resuelto: %s %s (%s)",
        legislador.nombre, legislador.apellido, legislador.camara.value,
    )
    monitor = LegisladorAMonitorear(
        legislador=legislador,
        legislador_id=legislador_uuid(
            slug=legislador.slug, camara=legislador.camara,
        ),
        despacho_id=despacho.id,
        aliases_extra=list(perfil.aliases_legislador),
    )
    return despacho, perfil, fuentes, [monitor]


async def main(args: argparse.Namespace) -> int:
    # Default: SQLite local idempotente. Con --usar-db-real usa la
    # DATABASE_URL del .env (Postgres en compose). Útil para poblar
    # la DB de develop con datos navegables en la UI.
    if args.usar_db_real:
        settings = get_settings()
        db_url = str(settings.database_url)
        log.info("DB real (Postgres): %s",
                 db_url.split("@")[-1] if "@" in db_url else db_url)
        engine = create_async_engine(db_url, echo=False)
    else:
        db_url = f"sqlite+aiosqlite:///{DB_FILE.as_posix()}"
        log.info("DB de smoke (SQLite): %s", DB_FILE)
        engine = create_async_engine(db_url, echo=False)
        event.listen(engine.sync_engine, "connect", _enable_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    padron = CsvPadronRepository()
    despacho, _perfil, fuentes, legisladores = await _seed_despacho_y_fuentes(
        sessionmaker, padron,
    )

    llm = _construir_llm(not args.llm_real)
    adapter_real = FuenteNoticiasMultiAdapter()
    adapter = FuenteNoticiasCapeado(adapter_real, args.max_articulos_por_fuente)
    detector = DetectarMencionesEnArticulo(llm=llm)

    ahora = datetime.now(UTC)
    desde = ahora - timedelta(days=args.ventana_dias)

    log.info("=" * 70)
    log.info(
        "Pipeline: %d fuentes, ventana %s → %s (%d días), cap %d arts/fuente",
        len(fuentes), desde.date(), ahora.date(),
        args.ventana_dias, args.max_articulos_por_fuente,
    )
    log.info("=" * 70)

    resultados: list[tuple[str, dict[str, int], list[str]]] = []
    try:
        for fuente in fuentes:
            assert fuente.id is not None
            log.info("→ %s (%s)", fuente.nombre, fuente.dominio)
            async with sessionmaker() as session:
                uc = ProcesarArticulosDeFuente(
                    fuente_adapter=adapter,
                    articulos=SqlAlchemyArticuloRepository(session),
                    hashes=SqlAlchemyArticuloHashRepository(session),
                    clasificaciones=SqlAlchemyClasificacionArticuloRepository(session),
                    menciones=SqlAlchemyMencionRepository(session),
                    relevantes=SqlAlchemyArticuloRelevanteRepository(session),
                    fuentes=SqlAlchemyFuenteNoticiaRepository(session),
                    llm=llm,
                    detector_menciones=detector,
                )
                try:
                    res = await uc.ejecutar(
                        fuente,
                        desde=desde,
                        despachos=[DespachoSuscrito(
                            despacho_id=despacho.id,
                            perfil_interes=_perfil,
                            legisladores=legisladores,
                        )],
                        ahora=ahora,
                    )
                    await session.commit()
                    stats = {
                        "descubiertos": res.articulos_descubiertos,
                        "nuevos": res.articulos_nuevos,
                        "omitidos_dedup": res.articulos_omitidos_por_dedup,
                        "bajadas": res.bajadas_generadas,
                        "clasif": res.clasificaciones_persistidas,
                        "menciones": res.menciones_creadas,
                        "relevantes": res.relevancias_persistidas,
                        "fallidos": res.fallidos,
                    }
                    resultados.append((fuente.dominio, stats, list(res.errores)))
                    log.info(
                        "  %d desc / %d nuevos / %d clasif / %d menciones / "
                        "%d relevantes / %d fallidos",
                        stats["descubiertos"], stats["nuevos"],
                        stats["clasif"], stats["menciones"],
                        stats["relevantes"], stats["fallidos"],
                    )
                except Exception as exc:
                    await session.rollback()
                    log.exception("  Falló %s: %s", fuente.dominio, exc)
                    resultados.append((
                        fuente.dominio,
                        {k: 0 for k in (
                            "descubiertos", "nuevos", "omitidos_dedup",
                            "bajadas", "clasif", "menciones",
                            "relevantes", "fallidos",
                        )},
                        [f"FATAL: {exc}"],
                    ))
    finally:
        await adapter_real.aclose()
        await engine.dispose()

    # Reporte final.
    print()
    print("=" * 78)
    print(f"{'FUENTE':<28} {'desc':>5} {'nuev':>5} {'clasif':>6} {'menc':>5} {'rel':>4} {'fail':>5}")
    print("-" * 78)
    totales = {k: 0 for k in ("descubiertos", "nuevos", "clasif", "menciones", "relevantes", "fallidos")}
    for dominio, stats, _ in resultados:
        print(
            f"{dominio:<28} {stats['descubiertos']:>5} {stats['nuevos']:>5} "
            f"{stats['clasif']:>6} {stats['menciones']:>5} "
            f"{stats['relevantes']:>4} {stats['fallidos']:>5}",
        )
        for k in totales:
            totales[k] += stats[k]
    print("-" * 78)
    print(
        f"{'TOTAL':<28} {totales['descubiertos']:>5} {totales['nuevos']:>5} "
        f"{totales['clasif']:>6} {totales['menciones']:>5} "
        f"{totales['relevantes']:>4} {totales['fallidos']:>5}",
    )
    print("=" * 78)

    # Errores por fuente.
    errores_hay = any(errores for _, _, errores in resultados)
    if errores_hay:
        print()
        print("ERRORES por fuente (primeros 5 por fuente):")
        for dominio, _, errores in resultados:
            if errores:
                print(f"  [{dominio}]")
                for e in errores:
                    print(f"    - {e}")

    # Detalle de relevantes encontrados (validación semántica).
    await _imprimir_relevantes(sessionmaker, despacho.id)
    await _imprimir_menciones(sessionmaker, despacho.id)

    return 0


async def _imprimir_relevantes(sessionmaker, despacho_id) -> None:  # type: ignore[no-untyped-def]
    """Imprime el detalle de ArticuloRelevante encontrados, ordenados
    por score desc. Para validar manualmente que el LLM clasificó
    razonablemente y que el scoring matcheó."""
    from praxis.infrastructure.persistence.models import (
        ArticuloOrm,
        ArticuloRelevanteOrm,
        FuenteNoticiaOrm,
    )
    from sqlalchemy import select

    async with sessionmaker() as session:
        stmt = (
            select(
                ArticuloRelevanteOrm,
                ArticuloOrm,
                FuenteNoticiaOrm,
            )
            .join(ArticuloOrm, ArticuloRelevanteOrm.articulo_id == ArticuloOrm.id)
            .join(FuenteNoticiaOrm, ArticuloOrm.fuente_id == FuenteNoticiaOrm.id)
            .where(ArticuloRelevanteOrm.despacho_id == despacho_id)
            .order_by(ArticuloRelevanteOrm.score.desc())
        )
        result = await session.execute(stmt)
        filas = list(result.all())

    if not filas:
        print()
        print("Sin ArticuloRelevante. El perfil quizá es muy específico para")
        print("la muestra random — probá subiendo --max-articulos-por-fuente.")
        return

    print()
    print("=" * 78)
    print(f"ARTÍCULOS RELEVANTES ({len(filas)}):")
    print("-" * 78)
    for rel, art, fuente in filas:
        titulo = art.titulo[:75]
        razon = rel.razon[:60]
        print(f"  [{rel.score:>3}] {fuente.dominio:<22} {titulo}")
        print(f"        razón: {razon}")
        print(f"        url:   {art.url[:75]}")
    print("=" * 78)


async def _imprimir_menciones(sessionmaker, despacho_id) -> None:  # type: ignore[no-untyped-def]
    """Imprime las menciones detectadas (regex + LLM disambig confirmado)."""
    from praxis.infrastructure.persistence.models import (
        ArticuloOrm,
        FuenteNoticiaOrm,
        MencionOrm,
    )
    from sqlalchemy import select

    async with sessionmaker() as session:
        stmt = (
            select(MencionOrm, ArticuloOrm, FuenteNoticiaOrm)
            .join(ArticuloOrm, MencionOrm.articulo_id == ArticuloOrm.id)
            .join(FuenteNoticiaOrm, ArticuloOrm.fuente_id == FuenteNoticiaOrm.id)
            .where(MencionOrm.despacho_id == despacho_id)
            .order_by(MencionOrm.detectado_en.desc())
        )
        result = await session.execute(stmt)
        filas = list(result.all())

    if not filas:
        print()
        print("Sin MENCIONES explícitas del legislador en esta muestra. "
              "Esperable")
        print("en N=25-50 artículos random; para validar el detector con datos")
        print("reales, hay que esperar a que algún medio mencione a Juliano.")
        return

    print()
    print("=" * 78)
    print(f"MENCIONES DETECTADAS ({len(filas)}):")
    print("-" * 78)
    for men, art, fuente in filas:
        print(f"  [{men.tono.value:<8} conf={men.confianza_tono:.2f}] "
              f"{fuente.dominio} — {art.titulo[:55]}")
        print(f"        snippet: \"{men.snippet_contexto[:120]}\"")
    print("=" * 78)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--llm-real",
        action="store_true",
        help="Usar AnthropicLlmProvider real (GASTA). Default: FakeLlm.",
    )
    p.add_argument(
        "--max-articulos-por-fuente",
        type=int,
        default=10,
        help="Cap de candidatos a procesar por fuente (default 10).",
    )
    p.add_argument(
        "--ventana-dias",
        type=int,
        default=7,
        help="Ventana temporal hacia atrás en días (default 7).",
    )
    p.add_argument(
        "--usar-db-real",
        action="store_true",
        help=(
            "Usar la DATABASE_URL del .env (Postgres) en vez de SQLite "
            "local. Útil para poblar la DB de develop con datos navegables."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
