"""Tests del DevAuthProvider — el atajo SOLO para dev local sin Clerk."""

from __future__ import annotations

import pytest

from praxis.domain import AuthError, AuthErrorCode
from praxis.infrastructure.auth import DEV_TOKEN_PREFIX, DevAuthProvider

pytestmark = pytest.mark.unit


async def test_dev_provider_acepta_token_con_prefijo() -> None:
    provider = DevAuthProvider()
    claims = await provider.verificar_token(f"{DEV_TOKEN_PREFIX}user_agustin")
    assert claims.sub == "user_agustin"
    assert claims.email is None
    assert claims.nombre is None


async def test_dev_provider_rechaza_token_sin_prefijo() -> None:
    provider = DevAuthProvider()
    with pytest.raises(AuthError) as exc:
        await provider.verificar_token("eyJhbGc-jwt-real-no-anda-aca")
    assert exc.value.code == AuthErrorCode.INVALID_TOKEN


async def test_dev_provider_rechaza_token_sin_sub() -> None:
    provider = DevAuthProvider()
    with pytest.raises(AuthError) as exc:
        await provider.verificar_token(DEV_TOKEN_PREFIX)
    assert exc.value.code == AuthErrorCode.INVALID_TOKEN
