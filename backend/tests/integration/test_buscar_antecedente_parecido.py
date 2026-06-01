"""Integration tests del use case BuscarAntecedenteParecido."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from praxis.application.use_cases import BuscarAntecedenteParecido
from praxis.domain import (
    AreaTematica,
    Camara,
    EstadoExpediente,
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


async def _crear(
    session: AsyncSession,
    *,
    numero: int,
    titulo: str,
    estado: EstadoExpediente = EstadoExpediente.SANCIONADO,
    area: AreaTematica = AreaTematica.EDUCACION,
    tipo: TipoExpediente = TipoExpediente.PROYECTO_LEY,
    fecha_ingreso: date = date(2024, 1, 1),
) -> UUID:
    repo = SqlAlchemyExpedienteRepository(session)
    repo_area = SqlAlchemyExpedienteAreaTematicaRepository(session)
    exp = Expediente(
        numero=NumeroExpediente(
            numero=numero,
            origen=OrigenExpediente.DIPUTADO,
            anio=fecha_ingreso.year,
            camara=Camara.HCDN,
        ),
        tipo=tipo,
        titulo=titulo,
        estado=estado,
        fecha_ingreso=fecha_ingreso,
    )
    creado = await repo.crear(exp)
    assert creado.id is not None
    await repo_area.crear(
        ExpedienteAreaTematica(
            id=uuid4(),
            expediente_id=creado.id,
            area=area,
            modelo="fake-keywords",
        )
    )
    return creado.id


async def test_devuelve_el_mas_similar_por_jaccard(
    session: AsyncSession,
) -> None:
    propio_id = await _crear(
        session,
        numero=100,
        titulo="EDUCACION SERVICIO ESTRATEGICO ESENCIAL",
        estado=EstadoExpediente.MEDIA_SANCION_HCDN,
    )
    # Antecedente 1: comparte 2 palabras clave → debería ganar.
    await _crear(
        session,
        numero=1,
        titulo="REGIMEN EDUCATIVO Y SERVICIO ESTRATEGICO NACIONAL",
        estado=EstadoExpediente.SANCIONADO,
    )
    # Antecedente 2: comparte menos palabras.
    await _crear(
        session,
        numero=2,
        titulo="PLAN DE ALFABETIZACION DIGITAL",
        estado=EstadoExpediente.SANCIONADO,
    )
    await session.commit()

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = BuscarAntecedenteParecido(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    resultado = await uc.execute(propio_id)

    assert resultado is not None
    assert resultado.numero.numero == 1
    assert resultado.estado_terminal == EstadoExpediente.SANCIONADO
    assert resultado.similitud > 0.20


async def test_excluye_expedientes_no_terminales(session: AsyncSession) -> None:
    propio_id = await _crear(
        session,
        numero=100,
        titulo="EDUCACION SERVICIO ESTRATEGICO ESENCIAL",
    )
    # Mismo título base pero EN_COMISION → NO es terminal, no debe entrar.
    await _crear(
        session,
        numero=1,
        titulo="EDUCACION SERVICIO ESTRATEGICO COMISION",
        estado=EstadoExpediente.EN_COMISION,
    )
    await session.commit()

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = BuscarAntecedenteParecido(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    resultado = await uc.execute(propio_id)
    assert resultado is None


async def test_excluye_expedientes_de_otra_area(session: AsyncSession) -> None:
    propio_id = await _crear(
        session,
        numero=100,
        titulo="EDUCACION SERVICIO ESTRATEGICO",
        area=AreaTematica.EDUCACION,
    )
    # Mismo título, otra área → no debe entrar.
    await _crear(
        session,
        numero=1,
        titulo="EDUCACION SERVICIO ESTRATEGICO",
        area=AreaTematica.SALUD,  # área distinta
        estado=EstadoExpediente.SANCIONADO,
    )
    await session.commit()

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = BuscarAntecedenteParecido(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    resultado = await uc.execute(propio_id)
    assert resultado is None


async def test_sin_clasificacion_devuelve_none(session: AsyncSession) -> None:
    repo = SqlAlchemyExpedienteRepository(session)
    exp = await repo.crear(
        Expediente(
            numero=NumeroExpediente(
                numero=1,
                origen=OrigenExpediente.DIPUTADO,
                anio=2025,
                camara=Camara.HCDN,
            ),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="Sin clasificar",
        )
    )
    await session.commit()
    assert exp.id is not None

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = BuscarAntecedenteParecido(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    assert await uc.execute(exp.id) is None
