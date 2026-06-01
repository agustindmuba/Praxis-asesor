"""Tests del SqlAlchemyVotacionRepository contra SQLite in-memory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from praxis.domain import (
    Camara,
    TipoVotacion,
    Votacion,
    VotoLegislador,
    VotoTipo,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyVotacionRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session_:
        yield session_
    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> SqlAlchemyVotacionRepository:
    return SqlAlchemyVotacionRepository(session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _votacion(
    *,
    acta_id: int = 5937,
    fecha: date = date(2026, 5, 20),
    titulo_od: str = "O.D. 84",
    asunto: str = "O.D. 84 - RÉGIMEN DE ZONA FRÍA. CAPÍTULO VI.",
    aprobada: bool = True,
    afirmativos: int = 137,
    negativos: int = 102,
) -> Votacion:
    return Votacion(
        id=None,
        camara=Camara.HCDN,
        fecha=fecha,
        sesion="Período 144 - Reunión 3 - Acta 20",
        asunto=asunto,
        tipo=TipoVotacion.PARTICULAR,
        resultado_afirmativos=afirmativos,
        resultado_negativos=negativos,
        resultado_abstenciones=1,
        resultado_sin_votar=1,
        resultado_ausentes=16,
        aprobada=aprobada,
        presidida_por="MENEM, MARTIN",
        titulo_od=titulo_od,
        acta_id_hcdn=acta_id,
        acta_pdf_url=f"/pdf/acta/{acta_id}",
        fuente_url=f"https://votaciones.hcdn.gob.ar/votacion/{acta_id}",
    )


def _voto(
    nombre: str,
    voto: VotoTipo,
    bloque: str = "Union Por La Patria",
    distrito: str = "Buenos Aires",
) -> VotoLegislador:
    return VotoLegislador(
        legislador_nombre=nombre,
        voto=voto,
        bloque=bloque,
        distrito=distrito,
    )


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_crear_persiste_votacion_y_votos(
    repo: SqlAlchemyVotacionRepository,
    session: AsyncSession,
) -> None:
    domain = _votacion(acta_id=5937)
    votos = [
        _voto("YEDLIN, PABLO RAUL", VotoTipo.NEGATIVO),
        _voto("MENEM, MARTIN", VotoTipo.SIN_VOTAR),
        _voto("MILEI, KARINA", VotoTipo.AFIRMATIVO, bloque="LLA"),
    ]
    creado = await repo.crear(domain, votos)
    await session.commit()

    assert creado.id is not None
    assert creado.acta_id_hcdn == 5937
    assert creado.titulo_od == "O.D. 84"

    # Buscar por acta_id_hcdn devuelve la misma.
    encontrada = await repo.buscar_por_acta_id_hcdn(5937)
    assert encontrada is not None
    assert encontrada.id == creado.id

    # Los votos están cargados separadamente.
    votos_db = await repo.listar_votos_de(creado.id)
    assert len(votos_db) == 3
    nombres = {v.legislador_nombre for v in votos_db}
    assert nombres == {"YEDLIN, PABLO RAUL", "MENEM, MARTIN", "MILEI, KARINA"}


async def test_acta_id_hcdn_es_unique(
    repo: SqlAlchemyVotacionRepository,
    session: AsyncSession,
) -> None:
    """Insertar dos veces con el mismo acta_id_hcdn rompe la UNIQUE."""
    from sqlalchemy.exc import IntegrityError

    await repo.crear(_votacion(acta_id=5937), [])
    await session.commit()
    # El segundo crear() hace flush y ahí tira IntegrityError
    # (no esperamos al commit).
    with pytest.raises(IntegrityError):
        await repo.crear(_votacion(acta_id=5937), [])


async def test_buscar_por_acta_inexistente_devuelve_none(
    repo: SqlAlchemyVotacionRepository,
) -> None:
    assert await repo.buscar_por_acta_id_hcdn(99999) is None


async def test_listar_recientes_filtra_por_camara_y_rango(
    repo: SqlAlchemyVotacionRepository,
    session: AsyncSession,
) -> None:
    await repo.crear(_votacion(acta_id=1, fecha=date(2024, 3, 1)), [])
    await repo.crear(_votacion(acta_id=2, fecha=date(2025, 6, 1)), [])
    await repo.crear(_votacion(acta_id=3, fecha=date(2026, 5, 20)), [])
    await session.commit()

    todas = await repo.listar_recientes(camara=Camara.HCDN, limit=10)
    assert len(todas) == 3
    # Orden: más recientes primero.
    assert [v.acta_id_hcdn for v in todas] == [3, 2, 1]

    rango_2025 = await repo.listar_recientes(
        camara=Camara.HCDN,
        desde=date(2025, 1, 1),
        hasta=date(2025, 12, 31),
    )
    assert [v.acta_id_hcdn for v in rango_2025] == [2]


async def test_cascade_borra_votos_al_borrar_votacion(
    repo: SqlAlchemyVotacionRepository,
    session: AsyncSession,
) -> None:
    creado = await repo.crear(
        _votacion(acta_id=5937),
        [_voto("X, Y", VotoTipo.AFIRMATIVO)],
    )
    await session.commit()
    assert creado.id is not None
    creado_id = creado.id
    assert len(await repo.listar_votos_de(creado_id)) == 1

    # Borrar manualmente y verificar cascade
    from praxis.infrastructure.persistence.models import VotacionOrm

    orm = await session.get(VotacionOrm, creado_id)
    assert orm is not None
    await session.delete(orm)
    await session.commit()

    assert await repo.buscar_por_id(creado_id) is None
    # Y los votos también deberían haberse borrado por cascade.
    assert await repo.listar_votos_de(creado_id) == []
