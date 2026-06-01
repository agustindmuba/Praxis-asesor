"""Integration tests del use case SugerirCofirmantes.

SQLite in-memory con seed manual: 1 proyecto del despacho + 5 candidatos
firmantes con distintos perfiles de firmas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from praxis.application.use_cases import SugerirCofirmantes
from praxis.domain import (
    AreaTematica,
    Camara,
    EstadoExpediente,
    Expediente,
    ExpedienteAreaTematica,
    Firmante,
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


async def _crear_expediente_con_firmantes(
    session: AsyncSession,
    *,
    numero: int,
    titulo: str,
    firmantes: list[tuple[str, str, str]],  # (nombre, bloque, distrito)
    area: AreaTematica = AreaTematica.EDUCACION,
    tipo: TipoExpediente = TipoExpediente.PROYECTO_LEY,
    fecha_ingreso: date | None = None,
) -> UUID:
    repo_exp = SqlAlchemyExpedienteRepository(session)
    repo_area = SqlAlchemyExpedienteAreaTematicaRepository(session)
    exp = Expediente(
        numero=NumeroExpediente(
            numero=numero,
            origen=OrigenExpediente.DIPUTADO,
            anio=2025,
            camara=Camara.HCDN,
        ),
        tipo=tipo,
        titulo=titulo,
        fecha_ingreso=fecha_ingreso or date.today() - timedelta(days=180),
        firmantes=[
            Firmante(nombre=n, bloque=b, distrito=d, orden=i + 1)
            for i, (n, b, d) in enumerate(firmantes)
        ],
    )
    creado = await repo_exp.crear(exp)
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


async def test_devuelve_cofirmantes_ordenados_por_proyectos_firmados(
    session: AsyncSession,
) -> None:
    # Proyecto del despacho (Juliano firma).
    propio_id = await _crear_expediente_con_firmantes(
        session,
        numero=1,
        titulo="Educación servicio estratégico",
        firmantes=[("JULIANO, PABLO", "Provincias Unidas", "Buenos Aires")],
    )

    # 3 expedientes parecidos firmados por distintos legisladores.
    # Diputado X firma 3 proyectos de educación (debería rankear primero).
    for i in range(3):
        await _crear_expediente_con_firmantes(
            session,
            numero=10 + i,
            titulo=f"Plan educativo {i}",
            firmantes=[
                ("DIPUTADO X", "UCR", "Cordoba"),
                ("DIPUTADO Y", "PRO", "Mendoza"),
            ],
        )
    # Diputado Z firma 2 proyectos
    for i in range(2):
        await _crear_expediente_con_firmantes(
            session,
            numero=20 + i,
            titulo=f"Reforma educativa {i}",
            firmantes=[("DIPUTADO Z", "FdT", "Santa Fe")],
        )
    # Diputado W firma solo 1 (por debajo del umbral _MIN_PROYECTOS=2 → fuera)
    await _crear_expediente_con_firmantes(
        session,
        numero=30,
        titulo="Proyecto educativo único",
        firmantes=[("DIPUTADO W", "MC", "Chaco")],
    )
    await session.commit()

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = SugerirCofirmantes(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    sugerencias = await uc.execute(propio_id)

    nombres = [s.nombre for s in sugerencias]
    assert "DIPUTADO X" in nombres
    assert "DIPUTADO Y" in nombres
    assert "DIPUTADO Z" in nombres
    # W tiene solo 1 proyecto → excluido por _MIN_PROYECTOS.
    assert "DIPUTADO W" not in nombres
    # X tiene 3 proyectos → debe estar antes que Z (2 proyectos).
    assert nombres.index("DIPUTADO X") < nombres.index("DIPUTADO Z")


async def test_excluir_bloques_y_firmantes(session: AsyncSession) -> None:
    propio_id = await _crear_expediente_con_firmantes(
        session,
        numero=1,
        titulo="Educación servicio estratégico",
        firmantes=[("JULIANO, PABLO", "Provincias Unidas", "Buenos Aires")],
    )
    # 2 cofirmantes potenciales — uno del bloque propio, uno externo.
    for i in range(2):
        await _crear_expediente_con_firmantes(
            session,
            numero=10 + i,
            titulo=f"Educación {i}",
            firmantes=[
                ("DIPUTADO A", "Provincias Unidas", "X"),
                ("DIPUTADO B", "UCR", "Y"),
            ],
        )
    await session.commit()

    expedientes = SqlAlchemyExpedienteRepository(session)
    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
    uc = SugerirCofirmantes(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    sugerencias = await uc.execute(
        propio_id,
        excluir_bloques=["Provincias Unidas"],
        excluir_firmantes=["JULIANO, PABLO"],
    )
    nombres = [s.nombre for s in sugerencias]
    assert "DIPUTADO B" in nombres        # UCR sí entra
    assert "DIPUTADO A" not in nombres    # PU excluido por bloque


async def test_sin_clasificacion_devuelve_vacio(session: AsyncSession) -> None:
    """Si el expediente no tiene área cacheada, sin sugerencias."""
    repo_exp = SqlAlchemyExpedienteRepository(session)
    exp = await repo_exp.crear(
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
    uc = SugerirCofirmantes(
        session=session,
        expedientes=expedientes,
        clasificaciones=clasificaciones,
    )
    sugerencias = await uc.execute(exp.id)
    assert sugerencias == []
    # asegurar que EstadoExpediente no se rompió en el setup
    assert EstadoExpediente.DESCONOCIDO
