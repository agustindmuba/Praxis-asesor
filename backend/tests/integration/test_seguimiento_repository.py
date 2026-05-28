"""Tests de integración del SqlAlchemySeguimientoExpedienteRepository.

Foco crítico: **aislamiento entre despachos** (multi-tenancy).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import (
    Despacho,
    Expediente,
    NumeroExpediente,
    Prioridad,
    SeguimientoExpediente,
    TipoExpediente,
    Usuario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyExpedienteRepository,
    SqlAlchemySeguimientoExpedienteRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def _seed_dos_despachos_un_expediente(
    session: AsyncSession,
) -> tuple[Despacho, Despacho, Expediente]:
    """Devuelve (despacho_A, despacho_B, expediente)."""
    d_a = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho A")
    )
    d_b = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho B")
    )
    expediente = await SqlAlchemyExpedienteRepository(session).crear(
        Expediente(
            numero=NumeroExpediente.parse_hcdn("100-D-2024"),
            tipo=TipoExpediente.PROYECTO_LEY,
            titulo="X",
        )
    )
    return d_a, d_b, expediente


# --- Crear y buscar -----------------------------------------------------------


async def test_crear_y_buscar_seguimiento(session: AsyncSession) -> None:
    d_a, _, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    creado = await repo.crear(
        SeguimientoExpediente(
            id=uuid4(),
            despacho_id=d_a.id,
            expediente_id=exp.id,
            prioridad=Prioridad.ALTA,
        )
    )
    encontrado = await repo.buscar(despacho_id=d_a.id, expediente_id=exp.id)
    assert encontrado is not None
    assert encontrado.id == creado.id
    assert encontrado.prioridad == Prioridad.ALTA


# --- Aislamiento entre despachos (test crítico) ------------------------------


async def test_dos_despachos_pueden_seguir_el_mismo_expediente(
    session: AsyncSession,
) -> None:
    """Despacho A y Despacho B siguen el mismo expediente — son rows separados."""
    d_a, d_b, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    await repo.crear(SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id))
    await repo.crear(SeguimientoExpediente(id=uuid4(), despacho_id=d_b.id, expediente_id=exp.id))
    # Cada despacho ve solo su propio seguimiento.
    s_a = await repo.listar_por_despacho(d_a.id)
    s_b = await repo.listar_por_despacho(d_b.id)
    assert len(s_a) == 1
    assert len(s_b) == 1
    assert s_a[0].despacho_id == d_a.id
    assert s_b[0].despacho_id == d_b.id


async def test_un_despacho_no_puede_seguir_dos_veces_el_mismo_expediente(
    session: AsyncSession,
) -> None:
    """UNIQUE (despacho_id, expediente_id) impide duplicado."""
    d_a, _, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    await repo.crear(SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id))
    with pytest.raises(IntegrityError):
        await repo.crear(
            SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
        )


async def test_buscar_por_id_no_filtra_si_despacho_es_otro(
    session: AsyncSession,
) -> None:
    """Test crítico: si paso seguimiento_id de despacho A pero despacho_id=B,
    no debe devolver nada (no leak cross-tenant)."""
    d_a, d_b, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    creado_a = await repo.crear(
        SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
    )

    # Despacho A lo ve.
    encontrado_a = await repo.buscar_por_id(despacho_id=d_a.id, seguimiento_id=creado_a.id)
    assert encontrado_a is not None

    # Despacho B NO lo ve aunque pase el id correcto.
    encontrado_b = await repo.buscar_por_id(despacho_id=d_b.id, seguimiento_id=creado_a.id)
    assert encontrado_b is None


# --- Archivado ---------------------------------------------------------------


async def test_archivar_y_listar_sin_archivados_default(
    session: AsyncSession,
) -> None:
    d_a, _, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    s = await repo.crear(
        SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
    )

    # Antes de archivar, listar() lo devuelve.
    assert len(await repo.listar_por_despacho(d_a.id)) == 1

    # Archivar.
    ok = await repo.archivar(despacho_id=d_a.id, seguimiento_id=s.id)
    assert ok is True

    # Después de archivar, listar() default lo oculta.
    assert await repo.listar_por_despacho(d_a.id) == []
    # Con `incluir_archivados=True` reaparece.
    assert len(await repo.listar_por_despacho(d_a.id, incluir_archivados=True)) == 1


async def test_archivar_id_de_otro_despacho_no_afecta_nada(
    session: AsyncSession,
) -> None:
    """Archivar pasando despacho_id incorrecto debe devolver False sin tocar la row."""
    d_a, d_b, exp = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    s = await repo.crear(
        SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
    )
    ok = await repo.archivar(despacho_id=d_b.id, seguimiento_id=s.id)
    assert ok is False
    # La row original sigue sin archivar.
    leido = await repo.buscar_por_id(despacho_id=d_a.id, seguimiento_id=s.id)
    assert leido is not None
    assert leido.archivado is False


# --- Asignación de responsable -----------------------------------------------


async def test_asignar_responsable(session: AsyncSession) -> None:
    d_a, _, exp = await _seed_dos_despachos_un_expediente(session)
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)

    usuario = await usuario_repo.crear(Usuario(id=uuid4(), email="asesor@x.com", nombre="Asesor"))
    s = await repo.crear(
        SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
    )

    ok = await repo.asignar_responsable(
        despacho_id=d_a.id, seguimiento_id=s.id, responsable_id=usuario.id
    )
    assert ok is True

    leido = await repo.buscar_por_id(despacho_id=d_a.id, seguimiento_id=s.id)
    assert leido is not None
    assert leido.responsable_id == usuario.id


async def test_desasignar_responsable_con_none(session: AsyncSession) -> None:
    d_a, _, exp = await _seed_dos_despachos_un_expediente(session)
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)

    usuario = await usuario_repo.crear(Usuario(id=uuid4(), email="a@x.com", nombre="A"))
    s = await repo.crear(
        SeguimientoExpediente(
            id=uuid4(),
            despacho_id=d_a.id,
            expediente_id=exp.id,
            responsable_id=usuario.id,
        )
    )

    await repo.asignar_responsable(despacho_id=d_a.id, seguimiento_id=s.id, responsable_id=None)

    leido = await repo.buscar_por_id(despacho_id=d_a.id, seguimiento_id=s.id)
    assert leido is not None
    assert leido.responsable_id is None


async def test_asignar_id_de_otro_despacho_no_afecta(session: AsyncSession) -> None:
    """Tenant isolation en update: pasar despacho_id de otro tenant no debe modificar."""
    d_a, d_b, exp = await _seed_dos_despachos_un_expediente(session)
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)

    usuario = await usuario_repo.crear(Usuario(id=uuid4(), email="a@x.com", nombre="A"))
    s = await repo.crear(
        SeguimientoExpediente(id=uuid4(), despacho_id=d_a.id, expediente_id=exp.id)
    )

    ok = await repo.asignar_responsable(
        despacho_id=d_b.id, seguimiento_id=s.id, responsable_id=usuario.id
    )
    assert ok is False

    leido = await repo.buscar_por_id(despacho_id=d_a.id, seguimiento_id=s.id)
    assert leido is not None
    assert leido.responsable_id is None  # no se modificó.


# --- Listado ----------------------------------------------------------------


async def test_listar_por_despacho_vacio(session: AsyncSession) -> None:
    d_a, _, _ = await _seed_dos_despachos_un_expediente(session)
    repo = SqlAlchemySeguimientoExpedienteRepository(session)
    assert await repo.listar_por_despacho(d_a.id) == []
