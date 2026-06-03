"""Tests integración de los 6 repos de noticias sobre SQLite in-memory.

Cubren:
- FuenteNoticia: crear, lookups, listar_activas, listar_para_despacho
  (globales + DISTRITALES por puente), marcar_revisada.
- Articulo: upsert idempotente por hash, lookups, listar por fuente,
  actualizar_bajada_propia.
- ArticuloHash: registrar idempotente, existe.
- ClasificacionArticulo: crear/buscar/eliminar.
- ArticuloRelevante: upsert (PK compuesta), top_n, borrar por ventana.
- Mencion: crear_lote idempotente por tupla natural, listar histórico
  con filtros, listar no notificadas, marcar_notificadas (bulk),
  listar_recientes (anti-flood).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    AlcanceMedio,
    AreaTematica,
    Articulo,
    ArticuloRelevante,
    ClasificacionArticulo,
    Despacho,
    FuenteNoticia,
    Mencion,
    ModoAccesoFuente,
    TipoFuenteNoticia,
    TonoMencion,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.models import FuenteNoticiaDespachoOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloHashRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMencionRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures + factories
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def despacho(session: AsyncSession) -> Despacho:
    repo = SqlAlchemyDespachoRepository(session)
    return await repo.crear(Despacho(id=uuid4(), nombre="Despacho test"))


def _fuente_nacional(
    *, dominio: str = "lanacion.com.ar", nombre: str = "La Nación",
) -> FuenteNoticia:
    return FuenteNoticia(
        id=None,
        nombre=nombre,
        dominio=dominio,
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url=f"https://{dominio}/rss",
    )


def _fuente_distrital(
    *,
    dominio: str = "infobae-tucuman.com.ar",
    distrito: str = "TUCUMAN",
) -> FuenteNoticia:
    return FuenteNoticia(
        id=None,
        nombre=f"Medio de {distrito}",
        dominio=dominio,
        tipo=TipoFuenteNoticia.DISTRITAL,
        alcance=AlcanceMedio.PROVINCIAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url=f"https://{dominio}/rss",
        distrito=distrito,
    )


def _articulo(fuente_id, *, url: str | None = None) -> Articulo:
    final_url = url or f"https://medio.com.ar/nota-{uuid4().hex[:6]}"
    return Articulo(
        id=None,
        fuente_id=fuente_id,
        url=final_url,
        titulo="Título de prueba",
        publicado_en=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        capturado_en=datetime(2026, 6, 1, 9, 5, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# FuenteNoticia
# ---------------------------------------------------------------------------


async def test_fuente_crear_y_buscar(session: AsyncSession) -> None:
    repo = SqlAlchemyFuenteNoticiaRepository(session)
    f = await repo.crear(_fuente_nacional())
    assert f.id is not None

    por_id = await repo.buscar_por_id(f.id)
    por_dom = await repo.buscar_por_dominio("lanacion.com.ar")
    assert por_id is not None and por_id.nombre == "La Nación"
    assert por_dom is not None and por_dom.id == f.id


async def test_listar_activas_excluye_desactivadas(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyFuenteNoticiaRepository(session)
    activa = await repo.crear(_fuente_nacional(dominio="clarin.com"))
    inactiva = _fuente_nacional(dominio="ambito.com", nombre="Ámbito")
    inactiva_persistida = await repo.crear(
        FuenteNoticia(
            id=None,
            nombre=inactiva.nombre,
            dominio=inactiva.dominio,
            tipo=inactiva.tipo,
            alcance=inactiva.alcance,
            modo_acceso=inactiva.modo_acceso,
            feed_url=inactiva.feed_url,
            activa=False,
        ),
    )
    listadas = await repo.listar_activas()
    ids = {f.id for f in listadas}
    assert activa.id in ids
    assert inactiva_persistida.id not in ids


async def test_listar_para_despacho_incluye_global_y_distrital(
    session: AsyncSession, despacho: Despacho,
) -> None:
    repo = SqlAlchemyFuenteNoticiaRepository(session)
    nac = await repo.crear(_fuente_nacional())
    dist_suya = await repo.crear(_fuente_distrital(dominio="x-tucuman.com"))
    dist_ajena = await repo.crear(
        _fuente_distrital(dominio="x-cordoba.com", distrito="CORDOBA"),
    )
    # Asociamos sólo `dist_suya` al despacho.
    session.add(
        FuenteNoticiaDespachoOrm(
            fuente_id=dist_suya.id, despacho_id=despacho.id,
        ),
    )
    await session.flush()

    visibles = await repo.listar_para_despacho(despacho.id)  # type: ignore[arg-type]
    ids = {f.id for f in visibles}
    assert nac.id in ids
    assert dist_suya.id in ids
    assert dist_ajena.id not in ids


async def test_marcar_revisada(session: AsyncSession) -> None:
    repo = SqlAlchemyFuenteNoticiaRepository(session)
    f = await repo.crear(_fuente_nacional())
    momento = datetime(2026, 6, 2, 10, 30, tzinfo=UTC)
    await repo.marcar_revisada(f.id, momento=momento)  # type: ignore[arg-type]
    refresco = await repo.buscar_por_id(f.id)  # type: ignore[arg-type]
    assert refresco is not None
    # SQLite no preserva tzinfo. Postgres en prod sí. Comparamos naive.
    leido = refresco.ultima_revision
    assert leido is not None
    leido_utc = leido if leido.tzinfo else leido.replace(tzinfo=UTC)
    assert leido_utc == momento


# ---------------------------------------------------------------------------
# Articulo
# ---------------------------------------------------------------------------


async def test_upsert_lote_idempotente_por_hash(
    session: AsyncSession,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a1 = _articulo(f.id, url="https://medio.com.ar/nota-A")
    persistidos1 = await art_repo.upsert_lote([a1])
    persistidos2 = await art_repo.upsert_lote(
        [_articulo(f.id, url="https://medio.com.ar/nota-A")],
    )
    assert persistidos1[0].id == persistidos2[0].id


async def test_actualizar_bajada_propia_persiste(
    session: AsyncSession,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    assert a.bajada_propia is None

    actualizado = await art_repo.actualizar_bajada_propia(
        a.id, bajada="Bajada neutral de prueba.",
    )
    assert actualizado.bajada_propia == "Bajada neutral de prueba."


async def test_actualizar_bajada_excede_max_levanta(
    session: AsyncSession,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    with pytest.raises(ValueError, match="bajada excede"):
        await art_repo.actualizar_bajada_propia(a.id, bajada="x" * 500)


async def test_articulo_inexistente_levanta_en_update(
    session: AsyncSession,
) -> None:
    art_repo = SqlAlchemyArticuloRepository(session)
    with pytest.raises(ValueError, match="no existe"):
        await art_repo.actualizar_bajada_propia(
            uuid4(), bajada="cualquiera",
        )


# ---------------------------------------------------------------------------
# ArticuloHash
# ---------------------------------------------------------------------------


async def test_articulo_hash_registrar_idempotente(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyArticuloHashRepository(session)
    h = "a" * 64
    assert await repo.registrar(h) is True
    assert await repo.registrar(h) is False
    assert await repo.existe(h) is True
    assert await repo.existe("b" * 64) is False


# ---------------------------------------------------------------------------
# ClasificacionArticulo
# ---------------------------------------------------------------------------


async def test_clasificacion_crear_buscar_eliminar(
    session: AsyncSession,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    cls_repo = SqlAlchemyClasificacionArticuloRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    c = await cls_repo.crear(
        ClasificacionArticulo(
            id=None,
            articulo_id=a.id,
            area_tematica=AreaTematica.SALUD,
            palabras_clave=["hospital", "vacuna"],
            modelo="fake-keywords",
        ),
    )
    assert c.id is not None
    encontrada = await cls_repo.buscar_por_articulo(a.id)
    assert encontrada is not None
    assert encontrada.area_tematica == AreaTematica.SALUD

    borrada = await cls_repo.eliminar(a.id)
    assert borrada is True
    assert await cls_repo.buscar_por_articulo(a.id) is None


# ---------------------------------------------------------------------------
# ArticuloRelevante
# ---------------------------------------------------------------------------


async def test_articulo_relevante_upsert_actualiza_existente(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    rel_repo = SqlAlchemyArticuloRelevanteRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    r = ArticuloRelevante(
        articulo_id=a.id,
        despacho_id=despacho.id,
        score=40,
        razon="match área",
    )
    primero = await rel_repo.upsert(r)
    segundo = await rel_repo.upsert(
        ArticuloRelevante(
            articulo_id=a.id,
            despacho_id=despacho.id,
            score=70,
            razon="match área + distrito",
        ),
    )
    assert primero.score == 40
    assert segundo.score == 70
    # Verifica que actualizó la misma fila (no duplica).
    listado = await rel_repo.listar_por_despacho_24h(
        despacho_id=despacho.id, hasta=datetime.now(UTC),
    )
    assert len(listado) == 1
    assert listado[0].score == 70


async def test_articulo_relevante_top_n_orden_por_score(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    rel_repo = SqlAlchemyArticuloRelevanteRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    arts = await art_repo.upsert_lote(
        [_articulo(f.id) for _ in range(5)],
    )
    for i, art in enumerate(arts):
        await rel_repo.upsert(
            ArticuloRelevante(
                articulo_id=art.id,
                despacho_id=despacho.id,
                score=10 * (i + 1),
                razon="r",
            ),
        )
    top3 = await rel_repo.listar_por_despacho_24h(
        despacho_id=despacho.id, hasta=datetime.now(UTC), top_n=3,
    )
    assert [r.score for r in top3] == [50, 40, 30]


async def test_articulo_relevante_borrar_por_ventana(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    rel_repo = SqlAlchemyArticuloRelevanteRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    await rel_repo.upsert(
        ArticuloRelevante(
            articulo_id=a.id,
            despacho_id=despacho.id,
            score=50,
            razon="r",
        ),
    )
    ahora = datetime.now(UTC)
    borradas = await rel_repo.borrar_por_despacho_y_ventana(
        despacho_id=despacho.id,
        desde=ahora - timedelta(days=1),
        hasta=ahora + timedelta(minutes=1),
    )
    assert borradas == 1


# ---------------------------------------------------------------------------
# Mencion
# ---------------------------------------------------------------------------


def _mencion(articulo_id, despacho_id, legislador_id=None) -> Mencion:
    return Mencion(
        id=None,
        articulo_id=articulo_id,
        legislador_id=legislador_id or uuid4(),
        despacho_id=despacho_id,
        snippet_contexto="…Pablo Juliano dijo algo importante…",
        tono=TonoMencion.NEUTRO,
        confianza_tono=0.7,
        alcance_medio=AlcanceMedio.NACIONAL,
    )


async def test_mencion_crear_lote_idempotente_por_tupla_natural(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    men_repo = SqlAlchemyMencionRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    leg_id = uuid4()
    m = _mencion(a.id, despacho.id, leg_id)
    primero = await men_repo.crear_lote([m])
    segundo = await men_repo.crear_lote(
        [_mencion(a.id, despacho.id, leg_id)],
    )
    assert primero[0].id == segundo[0].id


async def test_mencion_listar_historico_filtros(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    men_repo = SqlAlchemyMencionRepository(session)
    f1 = await fuente_repo.crear(_fuente_nacional(dominio="a.com"))
    f2 = await fuente_repo.crear(_fuente_nacional(dominio="b.com"))
    a1, = await art_repo.upsert_lote([_articulo(f1.id, url="https://a.com/1")])
    a2, = await art_repo.upsert_lote([_articulo(f2.id, url="https://b.com/2")])
    await men_repo.crear_lote([
        Mencion(
            id=None,
            articulo_id=a1.id,
            legislador_id=uuid4(),
            despacho_id=despacho.id,
            snippet_contexto="pos…",
            tono=TonoMencion.POSITIVO,
            confianza_tono=0.9,
            alcance_medio=AlcanceMedio.NACIONAL,
        ),
        Mencion(
            id=None,
            articulo_id=a2.id,
            legislador_id=uuid4(),
            despacho_id=despacho.id,
            snippet_contexto="neg…",
            tono=TonoMencion.NEGATIVO,
            confianza_tono=0.8,
            alcance_medio=AlcanceMedio.NACIONAL,
        ),
    ])
    ahora = datetime.now(UTC)

    todas = await men_repo.listar_historico(
        despacho_id=despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(minutes=1),
    )
    assert len(todas) == 2

    solo_pos = await men_repo.listar_historico(
        despacho_id=despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(minutes=1),
        tono="positivo",
    )
    assert len(solo_pos) == 1
    assert solo_pos[0].tono == TonoMencion.POSITIVO

    solo_f2 = await men_repo.listar_historico(
        despacho_id=despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(minutes=1),
        fuente_id=f2.id,
    )
    assert len(solo_f2) == 1
    assert solo_f2[0].tono == TonoMencion.NEGATIVO


async def test_marcar_notificadas_bulk(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    men_repo = SqlAlchemyMencionRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    creadas = await men_repo.crear_lote([
        _mencion(a.id, despacho.id) for _ in range(3)
    ])
    ids = [m.id for m in creadas]
    afectadas = await men_repo.marcar_notificadas(ids)  # type: ignore[arg-type]
    assert afectadas == 3
    sin_notif = await men_repo.listar_por_despacho_no_notificadas(
        despacho.id,
    )
    assert sin_notif == []


async def test_listar_recientes_para_anti_flood(
    session: AsyncSession, despacho: Despacho,
) -> None:
    fuente_repo = SqlAlchemyFuenteNoticiaRepository(session)
    art_repo = SqlAlchemyArticuloRepository(session)
    men_repo = SqlAlchemyMencionRepository(session)
    f = await fuente_repo.crear(_fuente_nacional())
    a, = await art_repo.upsert_lote([_articulo(f.id)])
    await men_repo.crear_lote([_mencion(a.id, despacho.id)])
    ahora = datetime.now(UTC)
    recientes = await men_repo.listar_recientes_por_despacho(
        despacho.id,
        desde=ahora - timedelta(hours=1),
        hasta=ahora + timedelta(minutes=1),
    )
    assert len(recientes) == 1
