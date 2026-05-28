"""Tests de integración de UsuarioRepository y MembresiaDespachoRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.domain import Despacho, MembresiaDespacho, Rol, Usuario
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    # SQLite no enforza FKs por default; habilitar.
    from sqlalchemy import event

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


# --- UsuarioRepository -------------------------------------------------------


async def test_crear_y_buscar_usuario_por_email(session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(session)
    creado = await repo.crear(Usuario(id=uuid4(), email="ANA@example.com", nombre="Ana"))
    # email se normaliza a lowercase al guardar.
    assert creado.email == "ana@example.com"

    encontrado = await repo.buscar_por_email("ana@example.com")
    assert encontrado is not None
    assert encontrado.id == creado.id


async def test_buscar_usuario_inexistente(session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(session)
    assert await repo.buscar_por_email("no@hay.com") is None
    assert await repo.buscar_por_id(uuid4()) is None
    assert await repo.buscar_por_auth_provider_id("no_existe") is None


async def test_email_es_unico(session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(session)
    await repo.crear(Usuario(id=uuid4(), email="a@b.com", nombre="A"))
    with pytest.raises(IntegrityError):
        await repo.crear(Usuario(id=uuid4(), email="a@b.com", nombre="A2"))


async def test_listar_usuarios(session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(session)
    await repo.crear(Usuario(id=uuid4(), email="b@x.com", nombre="B"))
    await repo.crear(Usuario(id=uuid4(), email="a@x.com", nombre="A"))
    resultado = await repo.listar()
    # Orden por email asc.
    assert [u.email for u in resultado] == ["a@x.com", "b@x.com"]


async def test_buscar_por_auth_provider_id(session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(session)
    await repo.crear(
        Usuario(
            id=uuid4(),
            email="x@y.com",
            nombre="X",
            auth_provider_id="clerk_user_abc",
        )
    )
    encontrado = await repo.buscar_por_auth_provider_id("clerk_user_abc")
    assert encontrado is not None
    assert encontrado.nombre == "X"


# --- MembresiaDespachoRepository ---------------------------------------------


async def _seed_usuario_y_despacho(
    session: AsyncSession,
) -> tuple[Usuario, Despacho]:
    """Crea un usuario y un despacho para los tests de membresía."""
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    despacho_repo = SqlAlchemyDespachoRepository(session)
    usuario = await usuario_repo.crear(Usuario(id=uuid4(), email="m@m.com", nombre="Miembro"))
    despacho = await despacho_repo.crear(Despacho(id=uuid4(), nombre="Despacho A"))
    return usuario, despacho


async def test_agregar_y_buscar_membresia(session: AsyncSession) -> None:
    usuario, despacho = await _seed_usuario_y_despacho(session)
    repo = SqlAlchemyMembresiaDespachoRepository(session)
    m = await repo.agregar(
        MembresiaDespacho(
            usuario_id=usuario.id,
            despacho_id=despacho.id,
            rol=Rol.JEFE_ASESORES,
        )
    )
    assert m.rol == Rol.JEFE_ASESORES

    encontrada = await repo.buscar(usuario_id=usuario.id, despacho_id=despacho.id)
    assert encontrada is not None
    assert encontrada.rol == Rol.JEFE_ASESORES


async def test_listar_por_despacho_solo_devuelve_miembros_de_ese_despacho(
    session: AsyncSession,
) -> None:
    """Filter explícito de despacho_id: aislamiento entre despachos."""
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    despacho_repo = SqlAlchemyDespachoRepository(session)
    membresia_repo = SqlAlchemyMembresiaDespachoRepository(session)

    u1 = await usuario_repo.crear(Usuario(id=uuid4(), email="u1@x.com", nombre="U1"))
    u2 = await usuario_repo.crear(Usuario(id=uuid4(), email="u2@x.com", nombre="U2"))
    d_a = await despacho_repo.crear(Despacho(id=uuid4(), nombre="A"))
    d_b = await despacho_repo.crear(Despacho(id=uuid4(), nombre="B"))

    await membresia_repo.agregar(
        MembresiaDespacho(usuario_id=u1.id, despacho_id=d_a.id, rol=Rol.JEFE_ASESORES)
    )
    await membresia_repo.agregar(
        MembresiaDespacho(usuario_id=u2.id, despacho_id=d_a.id, rol=Rol.ASESOR)
    )
    await membresia_repo.agregar(
        MembresiaDespacho(usuario_id=u1.id, despacho_id=d_b.id, rol=Rol.LECTOR)
    )

    miembros_a = await membresia_repo.listar_por_despacho(d_a.id)
    miembros_b = await membresia_repo.listar_por_despacho(d_b.id)
    assert {m.usuario_id for m in miembros_a} == {u1.id, u2.id}
    assert {m.usuario_id for m in miembros_b} == {u1.id}


async def test_listar_por_usuario_cruza_tenants(session: AsyncSession) -> None:
    """Un usuario miembro de dos despachos los ve a ambos."""
    usuario_repo = SqlAlchemyUsuarioRepository(session)
    despacho_repo = SqlAlchemyDespachoRepository(session)
    membresia_repo = SqlAlchemyMembresiaDespachoRepository(session)

    usuario = await usuario_repo.crear(Usuario(id=uuid4(), email="x@x.com", nombre="X"))
    d_a = await despacho_repo.crear(Despacho(id=uuid4(), nombre="A"))
    d_b = await despacho_repo.crear(Despacho(id=uuid4(), nombre="B"))

    await membresia_repo.agregar(
        MembresiaDespacho(usuario_id=usuario.id, despacho_id=d_a.id, rol=Rol.JEFE_ASESORES)
    )
    await membresia_repo.agregar(
        MembresiaDespacho(usuario_id=usuario.id, despacho_id=d_b.id, rol=Rol.ASESOR)
    )

    membresias = await membresia_repo.listar_por_usuario(usuario.id)
    despachos = {m.despacho_id for m in membresias}
    assert despachos == {d_a.id, d_b.id}


async def test_pk_compuesto_impide_duplicado(session: AsyncSession) -> None:
    """Un usuario no puede tener dos membresías en el mismo despacho."""
    usuario, despacho = await _seed_usuario_y_despacho(session)
    repo = SqlAlchemyMembresiaDespachoRepository(session)
    await repo.agregar(
        MembresiaDespacho(usuario_id=usuario.id, despacho_id=despacho.id, rol=Rol.ASESOR)
    )
    with pytest.raises(IntegrityError):
        await repo.agregar(
            MembresiaDespacho(usuario_id=usuario.id, despacho_id=despacho.id, rol=Rol.LECTOR)
        )
