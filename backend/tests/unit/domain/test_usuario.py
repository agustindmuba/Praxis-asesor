"""Tests unitarios de Usuario, Rol y MembresiaDespacho."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from praxis.domain import MembresiaDespacho, Rol, Usuario

pytestmark = pytest.mark.unit


# --- Rol ---------------------------------------------------------------------


def test_rol_tres_valores_del_mvp() -> None:
    assert Rol.JEFE_ASESORES.value == "jefe_asesores"
    assert Rol.ASESOR.value == "asesor"
    assert Rol.LECTOR.value == "lector"


# --- Usuario -----------------------------------------------------------------


def test_usuario_minimo() -> None:
    u = Usuario(id=uuid4(), email="a@b.com", nombre="Ana")
    assert u.email == "a@b.com"
    assert u.activo is True
    assert u.auth_provider_id is None


def test_usuario_email_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="email"):
        Usuario(id=uuid4(), email=" ", nombre="X")


def test_usuario_email_sin_arroba_lanza() -> None:
    with pytest.raises(ValueError, match="email"):
        Usuario(id=uuid4(), email="noesemail", nombre="X")


def test_usuario_nombre_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="nombre"):
        Usuario(id=uuid4(), email="a@b.com", nombre="  ")


def test_usuario_es_mutable() -> None:
    u = Usuario(id=uuid4(), email="a@b.com", nombre="X")
    u.activo = False
    assert u.activo is False


# --- MembresiaDespacho -------------------------------------------------------


def test_membresia_minima() -> None:
    m = MembresiaDespacho(
        usuario_id=uuid4(),
        despacho_id=uuid4(),
        rol=Rol.JEFE_ASESORES,
    )
    assert m.activo is True


def test_membresia_con_creado_en() -> None:
    now = datetime.now(UTC)
    m = MembresiaDespacho(
        usuario_id=uuid4(),
        despacho_id=uuid4(),
        rol=Rol.ASESOR,
        creado_en=now,
    )
    assert m.creado_en == now
