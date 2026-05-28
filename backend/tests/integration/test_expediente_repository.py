"""Tests de integración de `SqlAlchemyExpedienteRepository`.

SQLite in-memory async para evitar dependencia de Postgres en CI.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    Firmante,
    Giro,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
    TramiteEvento,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import SqlAlchemyExpedienteRepository

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
async def repo(session: AsyncSession) -> SqlAlchemyExpedienteRepository:
    return SqlAlchemyExpedienteRepository(session)


def _expediente_completo() -> Expediente:
    """Helper: arma un Expediente con firmantes, giros y trámite."""
    return Expediente(
        numero=NumeroExpediente.parse_hcdn("1497-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="PROTECCION DE DATOS PERSONALES - LEY 25326",
        sumario="MODIFICACION DE LOS ARTICULOS 2 Y 4",
        fecha_ingreso=date(2024, 5, 1),
        estado=EstadoExpediente.EN_COMISION,
        firmantes=[
            Firmante(
                nombre="PROPATO, AGUSTINA LUCRECIA",
                distrito="BUENOS AIRES",
                bloque="UNIÓN POR LA PATRIA",
                orden=1,
            )
        ],
        giros=[Giro(comision="ASUNTOS CONSTITUCIONALES")],
        tramite=[
            TramiteEvento(
                fecha=date(2024, 5, 15),
                camara=Camara.HCDN,
                evento="GIRO A COMISION",
                detalle="ASUNTOS CONSTITUCIONALES",
                fuente="scraper:hcdn",
            ),
        ],
        texto_url="https://www4.hcdn.gob.ar/.../1497-D-2024.pdf",
        fuente_url="https://www.diputados.gob.ar/proyectos/resultado.html",
        fecha_caducidad=date(2026, 4, 30),
        fecha_caducidad_original=date(2026, 4, 30),
        prorrogado=False,
    )


# --- crear -------------------------------------------------------------------


async def test_crear_persiste_expediente_y_relaciones(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    expediente = _expediente_completo()
    creado = await repo.crear(expediente)

    # Identidad preservada.
    assert creado.numero == expediente.numero
    assert creado.titulo == expediente.titulo
    # Relaciones persistidas y re-leídas.
    assert len(creado.firmantes) == 1
    assert creado.firmantes[0].nombre.startswith("PROPATO")
    assert len(creado.giros) == 1
    assert len(creado.tramite) == 1
    assert creado.tramite[0].fuente == "scraper:hcdn"


async def test_crear_genera_uuid_v7_para_id_interno(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """El dominio no expone el UUID, pero al persistir 2 expedientes
    distintos deberían tener IDs internos distintos (no fallar por
    PK colision)."""
    e1 = _expediente_completo()
    e2 = Expediente(
        numero=NumeroExpediente.parse_hcdn("4330-D-2021"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Otro proyecto",
    )
    await repo.crear(e1)
    await repo.crear(e2)
    # Si llegamos acá sin excepción, los IDs son distintos.


async def test_no_se_puede_crear_dos_veces_el_mismo_numero(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """UNIQUE en (numero, origen, anio, camara) impide duplicado."""
    from sqlalchemy.exc import IntegrityError

    await repo.crear(_expediente_completo())
    with pytest.raises(IntegrityError):
        await repo.crear(_expediente_completo())


# --- buscar_por_numero -------------------------------------------------------


async def test_buscar_por_numero_devuelve_completo(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    await repo.crear(_expediente_completo())
    encontrado = await repo.buscar_por_numero(NumeroExpediente.parse_hcdn("1497-D-2024"))
    assert encontrado is not None
    assert encontrado.titulo.startswith("PROTECCION DE DATOS")
    assert len(encontrado.firmantes) == 1
    assert len(encontrado.giros) == 1
    assert len(encontrado.tramite) == 1


async def test_buscar_por_numero_inexistente_devuelve_none(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    resultado = await repo.buscar_por_numero(NumeroExpediente.parse_hcdn("9999-D-2024"))
    assert resultado is None


# --- buscar_por_id -----------------------------------------------------------


async def test_buscar_por_id_inexistente_devuelve_none(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    assert await repo.buscar_por_id(uuid4()) is None


# --- listar ------------------------------------------------------------------


async def test_listar_vacio(repo: SqlAlchemyExpedienteRepository) -> None:
    assert await repo.listar() == []


async def test_listar_con_varios_paginado(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    """Crear 3 expedientes; listar limit=2 devuelve 2; offset=2 limit=2 devuelve 1."""
    for n in [1, 2, 3]:
        await repo.crear(
            Expediente(
                numero=NumeroExpediente.parse_hcdn(f"{n}-D-2024"),
                tipo=TipoExpediente.PROYECTO_LEY,
                titulo=f"Expediente {n}",
            )
        )
    primera = await repo.listar(limit=2, offset=0)
    segunda = await repo.listar(limit=2, offset=2)
    assert len(primera) == 2
    assert len(segunda) == 1


# --- Round-trip de campos de caducidad -------------------------------------


async def test_caducidad_round_trip(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    expediente = Expediente(
        numero=NumeroExpediente.parse_hcdn("100-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="X",
        fecha_caducidad=date(2026, 5, 1),
        fecha_caducidad_original=date(2024, 5, 1),
        prorrogado=True,
    )
    await repo.crear(expediente)
    leido = await repo.buscar_por_numero(expediente.numero)
    assert leido is not None
    assert leido.fecha_caducidad == date(2026, 5, 1)
    assert leido.fecha_caducidad_original == date(2024, 5, 1)
    assert leido.prorrogado is True


# --- Round-trip de estado ---------------------------------------------------


async def test_estado_round_trip(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    expediente = Expediente(
        numero=NumeroExpediente.parse_hcdn("200-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Y",
        estado=EstadoExpediente.MEDIA_SANCION_HCDN,
    )
    await repo.crear(expediente)
    leido = await repo.buscar_por_numero(expediente.numero)
    assert leido is not None
    assert leido.estado == EstadoExpediente.MEDIA_SANCION_HCDN


# --- Firmantes ordenados por `orden` -----------------------------------------


async def test_firmantes_se_devuelven_en_orden(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    expediente = Expediente(
        numero=NumeroExpediente.parse_hcdn("300-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Z",
        firmantes=[
            Firmante(nombre="C", orden=3),
            Firmante(nombre="A", orden=1),
            Firmante(nombre="B", orden=2),
        ],
    )
    await repo.crear(expediente)
    leido = await repo.buscar_por_numero(expediente.numero)
    assert leido is not None
    assert [f.nombre for f in leido.firmantes] == ["A", "B", "C"]


# --- Origen no estándar ------------------------------------------------------


async def test_origen_ejecutivo_se_persiste_correctamente(
    repo: SqlAlchemyExpedienteRepository,
) -> None:
    expediente = Expediente(
        numero=NumeroExpediente.parse_hcdn("1-PE-2024"),
        tipo=TipoExpediente.MENSAJE_PE,
        titulo="W",
    )
    await repo.crear(expediente)
    leido = await repo.buscar_por_numero(expediente.numero)
    assert leido is not None
    assert leido.numero.origen == OrigenExpediente.EJECUTIVO
    assert leido.tipo == TipoExpediente.MENSAJE_PE
