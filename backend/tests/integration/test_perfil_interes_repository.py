"""Tests de integración del `SqlAlchemyPerfilInteresDespachoRepository`.

SQLite in-memory async. Cubren:
- Inserción sobre despacho que no tiene perfil.
- Lectura.
- Upsert sobre fila existente preserva PK y actualiza valores.
- Listas se persisten y rehidratan correctamente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import Despacho, PerfilInteresDespacho
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def despacho(session: AsyncSession) -> Despacho:
    repo = SqlAlchemyDespachoRepository(session)
    creado = await repo.crear(Despacho(id=uuid4(), nombre="Despacho Juliano"))
    return creado


@pytest_asyncio.fixture
async def repo(
    session: AsyncSession,
) -> SqlAlchemyPerfilInteresDespachoRepository:
    return SqlAlchemyPerfilInteresDespachoRepository(session)


async def test_buscar_devuelve_none_si_no_se_sembr_o(
    repo: SqlAlchemyPerfilInteresDespachoRepository,
) -> None:
    assert await repo.buscar_por_despacho(uuid4()) is None


async def test_upsert_inserta_y_devuelve_con_actualizado_en(
    repo: SqlAlchemyPerfilInteresDespachoRepository,
    despacho: Despacho,
) -> None:
    perfil = PerfilInteresDespacho(
        despacho_id=despacho.id,
        areas_tematicas=["educacion", "salud"],
        distritos_observados=["Buenos Aires"],
        aliases_legislador=["Pablo Juliano", "Juliano"],
        sembrado_at=datetime.now(UTC),
    )
    creado = await repo.upsert(perfil)
    assert creado.despacho_id == despacho.id
    assert creado.areas_tematicas == ["educacion", "salud"]
    assert creado.distritos_observados == ["Buenos Aires"]
    assert creado.aliases_legislador == ["Pablo Juliano", "Juliano"]
    assert creado.sembrado_at is not None
    assert creado.actualizado_en is not None


async def test_buscar_devuelve_lo_persistido(
    repo: SqlAlchemyPerfilInteresDespachoRepository,
    despacho: Despacho,
) -> None:
    perfil = PerfilInteresDespacho(
        despacho_id=despacho.id,
        areas_tematicas=["justicia"],
        comisiones_legislador=["Legislación General"],
    )
    await repo.upsert(perfil)
    leido = await repo.buscar_por_despacho(despacho.id)
    assert leido is not None
    assert leido.areas_tematicas == ["justicia"]
    assert leido.comisiones_legislador == ["Legislación General"]


async def test_upsert_actualiza_sin_duplicar(
    repo: SqlAlchemyPerfilInteresDespachoRepository,
    despacho: Despacho,
) -> None:
    """Re-upsert sobre el mismo despacho_id reemplaza la fila."""
    sembrado_at = datetime.now(UTC)
    await repo.upsert(
        PerfilInteresDespacho(
            despacho_id=despacho.id,
            areas_tematicas=["educacion"],
            sembrado_at=sembrado_at,
        )
    )
    editado_at = sembrado_at + timedelta(hours=1)
    await repo.upsert(
        PerfilInteresDespacho(
            despacho_id=despacho.id,
            areas_tematicas=["educacion", "salud", "trabajo"],
            sembrado_at=sembrado_at,
            editado_at=editado_at,
        )
    )
    leido = await repo.buscar_por_despacho(despacho.id)
    assert leido is not None
    assert leido.areas_tematicas == ["educacion", "salud", "trabajo"]
    assert leido.editado_at is not None
