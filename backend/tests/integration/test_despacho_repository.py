"""Tests de integración del `SqlAlchemyDespachoRepository`.

Usa SQLite in-memory async para no requerir Postgres corriendo. La lógica
de mapeo/persistencia es la misma; lo único que difiere entre SQLite y
Postgres son detalles de tipos (Uuid → text en SQLite, UUID nativo en
Postgres) que SQLAlchemy abstrae.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import Despacho
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import SqlAlchemyDespachoRepository

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Engine + session de SQLite in-memory; crea schema antes de cada test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> SqlAlchemyDespachoRepository:
    return SqlAlchemyDespachoRepository(session)


# --- Camino feliz -----------------------------------------------------------


async def test_crear_y_buscar_por_id(
    repo: SqlAlchemyDespachoRepository,
) -> None:
    despacho = Despacho(id=uuid4(), nombre="Despacho A")
    creado = await repo.crear(despacho)
    assert creado.id == despacho.id
    assert creado.creado_en is not None
    assert creado.actualizado_en is not None

    encontrado = await repo.buscar_por_id(creado.id)
    assert encontrado is not None
    assert encontrado.nombre == "Despacho A"


async def test_crear_sin_id_explicito_genera_uuid7(
    repo: SqlAlchemyDespachoRepository,
) -> None:
    """Si la entidad tiene un id (siempre obligatorio en el constructor),
    se usa ese. Para que el ORM genere uuid7, hay que pasar id=None — no
    soportado por el dominio. Por lo que en práctica el id viene del dominio."""
    d_id = uuid4()
    despacho = Despacho(id=d_id, nombre="X")
    creado = await repo.crear(despacho)
    assert creado.id == d_id  # respetado.


async def test_buscar_inexistente_devuelve_none(
    repo: SqlAlchemyDespachoRepository,
) -> None:
    resultado = await repo.buscar_por_id(uuid4())
    assert resultado is None


async def test_listar_vacio(repo: SqlAlchemyDespachoRepository) -> None:
    assert await repo.listar() == []


async def test_listar_con_varios(repo: SqlAlchemyDespachoRepository) -> None:
    await repo.crear(Despacho(id=uuid4(), nombre="A"))
    await repo.crear(Despacho(id=uuid4(), nombre="B"))
    await repo.crear(Despacho(id=uuid4(), nombre="C"))
    resultado = await repo.listar()
    assert len(resultado) == 3
    nombres = {d.nombre for d in resultado}
    assert nombres == {"A", "B", "C"}


async def test_configuracion_se_persiste_como_json(
    repo: SqlAlchemyDespachoRepository,
) -> None:
    config = {"tema_principal": "salud", "alertas_email": True, "max_seguimientos": 50}
    despacho = Despacho(id=uuid4(), nombre="X", configuracion=config)
    creado = await repo.crear(despacho)
    encontrado = await repo.buscar_por_id(creado.id)
    assert encontrado is not None
    assert encontrado.configuracion == config


async def test_legislador_titular_slug_opcional(
    repo: SqlAlchemyDespachoRepository,
) -> None:
    sin_slug = await repo.crear(Despacho(id=uuid4(), nombre="A"))
    con_slug = await repo.crear(
        Despacho(id=uuid4(), nombre="B", legislador_titular_slug="haguirre")
    )
    sin_slug_encontrado = await repo.buscar_por_id(sin_slug.id)
    con_slug_encontrado = await repo.buscar_por_id(con_slug.id)
    assert sin_slug_encontrado is not None and sin_slug_encontrado.legislador_titular_slug is None
    assert (
        con_slug_encontrado is not None
        and con_slug_encontrado.legislador_titular_slug == "haguirre"
    )
