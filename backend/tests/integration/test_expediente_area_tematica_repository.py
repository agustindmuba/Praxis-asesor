"""Tests del SqlAlchemyExpedienteAreaTematicaRepository contra SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from praxis.domain import (
    AreaTematica,
    Camara,
    Expediente,
    ExpedienteAreaTematica,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteAreaTematicaRepository,
    SqlAlchemyExpedienteRepository,
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


async def _crear_expediente(session: AsyncSession) -> Expediente:
    """Crea un expediente dummy para asociar la clasificación."""
    repo = SqlAlchemyExpedienteRepository(session)
    exp = Expediente(
        numero=NumeroExpediente(
            numero=1, origen=OrigenExpediente.DIPUTADO, anio=2025, camara=Camara.HCDN
        ),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Test",
        fecha_ingreso=date(2025, 1, 1),
    )
    creado = await repo.crear(exp)
    await session.commit()
    return creado


async def test_crear_y_buscar_por_expediente(session: AsyncSession) -> None:
    expediente = await _crear_expediente(session)
    assert expediente.id is not None
    repo = SqlAlchemyExpedienteAreaTematicaRepository(session)

    cache = ExpedienteAreaTematica(
        id=uuid4(),
        expediente_id=expediente.id,
        area=AreaTematica.EDUCACION,
        modelo="fake-keywords",
    )
    creado = await repo.crear(cache)
    await session.commit()

    assert creado.id == cache.id
    assert creado.area == AreaTematica.EDUCACION
    assert creado.generado_en is not None  # populated by server_default

    encontrado = await repo.buscar_por_expediente(expediente.id)
    assert encontrado is not None
    assert encontrado.area == AreaTematica.EDUCACION


async def test_expediente_id_es_unique(session: AsyncSession) -> None:
    expediente = await _crear_expediente(session)
    assert expediente.id is not None
    repo = SqlAlchemyExpedienteAreaTematicaRepository(session)

    await repo.crear(
        ExpedienteAreaTematica(
            id=uuid4(),
            expediente_id=expediente.id,
            area=AreaTematica.EDUCACION,
            modelo="fake-keywords",
        )
    )
    await session.commit()
    with pytest.raises(IntegrityError):
        await repo.crear(
            ExpedienteAreaTematica(
                id=uuid4(),
                expediente_id=expediente.id,
                area=AreaTematica.SALUD,
                modelo="fake-keywords",
            )
        )


async def test_eliminar_devuelve_bool(session: AsyncSession) -> None:
    expediente = await _crear_expediente(session)
    assert expediente.id is not None
    repo = SqlAlchemyExpedienteAreaTematicaRepository(session)

    # Nada que borrar
    assert await repo.eliminar(expediente.id) is False

    await repo.crear(
        ExpedienteAreaTematica(
            id=uuid4(),
            expediente_id=expediente.id,
            area=AreaTematica.EDUCACION,
            modelo="fake-keywords",
        )
    )
    await session.commit()

    assert await repo.eliminar(expediente.id) is True
    assert await repo.buscar_por_expediente(expediente.id) is None


async def test_listar_por_area(session: AsyncSession) -> None:
    # Crear 3 expedientes con distintas áreas
    repo_exp = SqlAlchemyExpedienteRepository(session)
    repo = SqlAlchemyExpedienteAreaTematicaRepository(session)

    ids: list[UUID] = []
    for n, area in enumerate(
        [AreaTematica.EDUCACION, AreaTematica.SALUD, AreaTematica.EDUCACION],
        start=1,
    ):
        exp = await repo_exp.crear(
            Expediente(
                numero=NumeroExpediente(
                    numero=n,
                    origen=OrigenExpediente.DIPUTADO,
                    anio=2025,
                    camara=Camara.HCDN,
                ),
                tipo=TipoExpediente.PROYECTO_LEY,
                titulo=f"Test {n}",
            )
        )
        assert exp.id is not None
        ids.append(exp.id)
        await repo.crear(
            ExpedienteAreaTematica(
                id=uuid4(),
                expediente_id=exp.id,
                area=area,
                modelo="fake-keywords",
            )
        )
    await session.commit()

    educacion = await repo.listar_por_area(AreaTematica.EDUCACION)
    assert len(educacion) == 2
    salud = await repo.listar_por_area(AreaTematica.SALUD)
    assert len(salud) == 1
    ambiente = await repo.listar_por_area(AreaTematica.AMBIENTE)
    assert ambiente == []
