"""Tests unit de los value objects de auth."""

from __future__ import annotations

from uuid import uuid4

import pytest

from praxis.domain import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    Despacho,
    RequestContext,
    Rol,
    Usuario,
)

pytestmark = pytest.mark.unit


def test_auth_claims_acepta_sub_minimo() -> None:
    claims = AuthClaims(sub="user_123")
    assert claims.sub == "user_123"
    assert claims.email is None
    assert claims.nombre is None


def test_auth_claims_rechaza_sub_vacio() -> None:
    with pytest.raises(ValueError, match="sub"):
        AuthClaims(sub="")
    with pytest.raises(ValueError, match="sub"):
        AuthClaims(sub="   ")


def test_request_context_se_construye_con_las_3_entidades() -> None:
    usuario = Usuario(id=uuid4(), email="a@b.com", nombre="Ana")
    despacho = Despacho(id=uuid4(), nombre="Despacho X")
    ctx = RequestContext(usuario=usuario, despacho=despacho, rol=Rol.JEFE_ASESORES)
    assert ctx.usuario is usuario
    assert ctx.despacho is despacho
    assert ctx.rol == Rol.JEFE_ASESORES


def test_auth_error_lleva_code_y_detalle() -> None:
    err = AuthError(AuthErrorCode.TOKEN_EXPIRED, "exp=...")
    assert err.code == AuthErrorCode.TOKEN_EXPIRED
    assert err.detalle == "exp=..."
    assert "token_expired" in str(err)
    assert "exp=..." in str(err)


def test_auth_error_sin_detalle() -> None:
    err = AuthError(AuthErrorCode.NOT_A_MEMBER)
    assert err.code == AuthErrorCode.NOT_A_MEMBER
    assert err.detalle is None
    assert str(err) == "not_a_member"


def test_auth_error_code_tiene_todos_los_codigos() -> None:
    """Sanidad: que no me olvide ninguno al renombrar."""
    esperados = {
        "INVALID_TOKEN",
        "TOKEN_EXPIRED",
        "WRONG_ISSUER",
        "USER_NOT_PROVISIONED",
        "DESPACHO_NOT_FOUND",
        "NOT_A_MEMBER",
    }
    actuales = {c.name for c in AuthErrorCode}
    assert actuales == esperados
