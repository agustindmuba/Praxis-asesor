"""Tests unit del caso de uso SincronizarUsuarioDesdeClerk.

Fake del UsuarioRepository en memoria + payloads sintéticos por tipo de evento.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from praxis.application.ports import UsuarioRepository
from praxis.application.use_cases import SincronizarUsuarioDesdeClerk
from praxis.application.use_cases.sincronizar_usuario_clerk import (
    _extract_clerk_id,
    _extract_email,
    _extract_nombre,
)
from praxis.domain import Usuario

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake repo
# ---------------------------------------------------------------------------


class FakeUsuariosRepo(UsuarioRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Usuario] = {}
        self._by_clerk_id: dict[str, Usuario] = {}

    async def crear(self, usuario: Usuario) -> Usuario:
        # Reproducimos la normalización del adapter real.
        nuevo = Usuario(
            id=usuario.id,
            email=usuario.email.strip().lower(),
            nombre=usuario.nombre,
            auth_provider_id=usuario.auth_provider_id,
            activo=usuario.activo,
        )
        self._by_id[nuevo.id] = nuevo
        if nuevo.auth_provider_id:
            self._by_clerk_id[nuevo.auth_provider_id] = nuevo
        return nuevo

    async def actualizar(self, usuario: Usuario) -> Usuario:
        if usuario.id not in self._by_id:
            raise ValueError(f"usuario {usuario.id} no existe")
        nuevo = Usuario(
            id=usuario.id,
            email=usuario.email.strip().lower(),
            nombre=usuario.nombre,
            auth_provider_id=usuario.auth_provider_id,
            activo=usuario.activo,
        )
        self._by_id[nuevo.id] = nuevo
        if nuevo.auth_provider_id:
            self._by_clerk_id[nuevo.auth_provider_id] = nuevo
        return nuevo

    async def buscar_por_id(self, usuario_id: UUID) -> Usuario | None:
        return self._by_id.get(usuario_id)

    async def buscar_por_email(self, email: str) -> Usuario | None:
        for u in self._by_id.values():
            if u.email == email.strip().lower():
                return u
        return None

    async def buscar_por_auth_provider_id(self, auth_provider_id: str) -> Usuario | None:
        return self._by_clerk_id.get(auth_provider_id)

    async def listar(self) -> list[Usuario]:
        return list(self._by_id.values())


# ---------------------------------------------------------------------------
# Helpers de payload Clerk
# ---------------------------------------------------------------------------


def _user_payload(
    *,
    clerk_id: str = "user_abc",
    email: str = "ana@x.com",
    first: str | None = "Ana",
    last: str | None = "Perez",
    primary_id: str = "ea_1",
) -> dict[str, Any]:
    return {
        "id": clerk_id,
        "email_addresses": [
            {"id": "ea_1", "email_address": email},
            {"id": "ea_2", "email_address": "alt@x.com"},
        ],
        "primary_email_address_id": primary_id,
        "first_name": first,
        "last_name": last,
    }


# ---------------------------------------------------------------------------
# Extractores puros
# ---------------------------------------------------------------------------


def test_extract_clerk_id() -> None:
    assert _extract_clerk_id({"id": "user_xyz"}) == "user_xyz"


def test_extract_clerk_id_rechaza_sin_id() -> None:
    with pytest.raises(ValueError, match="id"):
        _extract_clerk_id({})


def test_extract_email_usa_primary() -> None:
    p = _user_payload(email="ana@x.com")
    assert _extract_email(p) == "ana@x.com"


def test_extract_email_fallback_al_primero_si_no_hay_primary() -> None:
    p = _user_payload(primary_id="no-existe")
    # No matchea ningún id; toma el primero.
    assert _extract_email(p) == "ana@x.com"


def test_extract_email_rechaza_sin_email_addresses() -> None:
    with pytest.raises(ValueError, match="email_addresses"):
        _extract_email({"id": "x"})


def test_extract_email_rechaza_inválido() -> None:
    with pytest.raises(ValueError, match="email"):
        _extract_email(
            {
                "id": "x",
                "email_addresses": [{"id": "e1", "email_address": "no-arroba"}],
                "primary_email_address_id": "e1",
            }
        )


def test_extract_nombre_concatena_first_last() -> None:
    assert _extract_nombre(_user_payload(first="Ana", last="Perez")) == "Ana Perez"


def test_extract_nombre_solo_first() -> None:
    assert _extract_nombre(_user_payload(first="Ana", last=None)) == "Ana"


def test_extract_nombre_fallback_username() -> None:
    p = _user_payload(first=None, last=None)
    p["username"] = "ana_p"
    assert _extract_nombre(p) == "ana_p"


def test_extract_nombre_fallback_email_local() -> None:
    p = _user_payload(first=None, last=None, email="ana_test@x.com")
    assert _extract_nombre(p) == "ana_test"


# ---------------------------------------------------------------------------
# Caso de uso — user.created
# ---------------------------------------------------------------------------


async def test_user_created_provisiona_nuevo_usuario() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)

    resultado = await sync.execute(
        evento_tipo="user.created",
        data=_user_payload(clerk_id="user_001", email="ana@x.com"),
    )
    assert resultado == "processed"
    u = await repo.buscar_por_auth_provider_id("user_001")
    assert u is not None
    assert u.email == "ana@x.com"
    assert u.nombre == "Ana Perez"
    assert u.activo is True


async def test_user_created_es_idempotente_si_ya_existe() -> None:
    """Si Clerk reenvía user.created para un user ya en DB, lo tratamos
    como update (no error)."""
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    await repo.crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana Vieja",
            auth_provider_id="user_001",
        )
    )

    resultado = await sync.execute(
        evento_tipo="user.created",
        data=_user_payload(clerk_id="user_001", first="Ana", last="Nueva"),
    )
    assert resultado == "processed"
    u = await repo.buscar_por_auth_provider_id("user_001")
    assert u is not None
    assert u.nombre == "Ana Nueva"


# ---------------------------------------------------------------------------
# Caso de uso — user.updated
# ---------------------------------------------------------------------------


async def test_user_updated_sincroniza_email_y_nombre() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    await repo.crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana Vieja",
            auth_provider_id="user_001",
        )
    )

    await sync.execute(
        evento_tipo="user.updated",
        data=_user_payload(clerk_id="user_001", email="ana@new.com", first="Ana", last="Nueva"),
    )
    u = await repo.buscar_por_auth_provider_id("user_001")
    assert u is not None
    assert u.email == "ana@new.com"
    assert u.nombre == "Ana Nueva"


async def test_user_updated_preserva_activo() -> None:
    """Si el usuario estaba inactivo, no lo reactivamos automáticamente."""
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    await repo.crear(
        Usuario(
            id=uuid4(),
            email="x@x.com",
            nombre="X",
            auth_provider_id="user_002",
            activo=False,
        )
    )
    await sync.execute(
        evento_tipo="user.updated",
        data=_user_payload(clerk_id="user_002"),
    )
    u = await repo.buscar_por_auth_provider_id("user_002")
    assert u is not None
    assert u.activo is False


# ---------------------------------------------------------------------------
# Caso de uso — user.deleted
# ---------------------------------------------------------------------------


async def test_user_deleted_desactiva() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    await repo.crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana",
            auth_provider_id="user_001",
        )
    )

    resultado = await sync.execute(
        evento_tipo="user.deleted",
        data={"id": "user_001"},
    )
    assert resultado == "processed"
    u = await repo.buscar_por_auth_provider_id("user_001")
    assert u is not None
    assert u.activo is False


async def test_user_deleted_para_usuario_desconocido_no_lanza() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    resultado = await sync.execute(
        evento_tipo="user.deleted",
        data={"id": "user_FANTASMA"},
    )
    assert resultado == "processed"


# ---------------------------------------------------------------------------
# Caso de uso — session.created y eventos desconocidos
# ---------------------------------------------------------------------------


async def test_session_created_es_processed_pero_no_op() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    resultado = await sync.execute(
        evento_tipo="session.created",
        data={"id": "sess_abc", "user_id": "user_001"},
    )
    assert resultado == "processed"
    assert len(await repo.listar()) == 0  # no creó nada


async def test_evento_desconocido_devuelve_ignored() -> None:
    repo = FakeUsuariosRepo()
    sync = SincronizarUsuarioDesdeClerk(usuarios=repo)
    resultado = await sync.execute(
        evento_tipo="organization.created",
        data={"id": "org_x"},
    )
    assert resultado == "ignored"
