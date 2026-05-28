"""Tests unit del ClerkAuthProvider.

Generamos pares RSA in-memory con `cryptography`, firmamos JWTs, y publicamos
el JWKS como dict en un `httpx.MockTransport`. Sin tocar red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    generate_private_key,
)
from jwt.algorithms import RSAAlgorithm

from praxis.domain import AuthError, AuthErrorCode
from praxis.infrastructure.auth import ClerkAuthProvider

ISSUER = "https://test.clerk.dev"
JWKS_URL = "https://test.clerk.dev/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_key_1() -> RSAPrivateKey:
    return generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def rsa_key_2() -> RSAPrivateKey:
    return generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_rsa(key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    """Convierte la public key a JWK dict (n, e, kid, kty, alg)."""
    public_jwk_json = RSAAlgorithm.to_jwk(key.public_key())
    import json

    jwk = json.loads(public_jwk_json)
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def _sign(
    key: RSAPrivateKey,
    *,
    kid: str,
    sub: str = "user_test_1",
    issuer: str = ISSUER,
    extra_claims: dict[str, Any] | None = None,
    exp_delta: timedelta = timedelta(minutes=10),
    audience: str | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": sub,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + exp_delta).timestamp()),
    }
    if audience is not None:
        claims["aud"] = audience
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def _make_provider(
    *,
    jwks_payload: dict[str, Any],
    audience: str | None = None,
    clock: Any = None,
) -> ClerkAuthProvider:
    """Construye el provider con un MockTransport que sirve el JWKS dado."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, json=jwks_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClerkAuthProvider(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        audience=audience,
        http_client=client,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# Tests happy path
# ---------------------------------------------------------------------------


async def test_verifica_token_valido_y_devuelve_claims(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(
        rsa_key_1,
        kid="kid-1",
        sub="user_abc",
        extra_claims={"email": "a@b.com", "first_name": "Ana", "last_name": "Perez"},
    )

    claims = await provider.verificar_token(token)
    assert claims.sub == "user_abc"
    assert claims.email == "a@b.com"
    assert claims.nombre == "Ana Perez"


async def test_nombre_desde_claim_name_directo(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_1, kid="kid-1", extra_claims={"name": "Juan Lopez"})
    claims = await provider.verificar_token(token)
    assert claims.nombre == "Juan Lopez"


async def test_sin_nombre_devuelve_none(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_1, kid="kid-1")
    claims = await provider.verificar_token(token)
    assert claims.nombre is None
    assert claims.email is None


async def test_verifica_aud_si_configurado(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks, audience="my-api")
    token = _sign(rsa_key_1, kid="kid-1", audience="my-api")
    claims = await provider.verificar_token(token)
    assert claims.sub == "user_test_1"


# ---------------------------------------------------------------------------
# Tests de fallas
# ---------------------------------------------------------------------------


async def test_rechaza_token_expirado(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_1, kid="kid-1", exp_delta=timedelta(seconds=-60))

    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token(token)
    assert exc_info.value.code == AuthErrorCode.TOKEN_EXPIRED


async def test_rechaza_issuer_incorrecto(rsa_key_1: RSAPrivateKey) -> None:
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_1, kid="kid-1", issuer="https://otro-issuer.com")

    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token(token)
    assert exc_info.value.code == AuthErrorCode.WRONG_ISSUER


async def test_rechaza_firma_con_otra_clave(
    rsa_key_1: RSAPrivateKey, rsa_key_2: RSAPrivateKey
) -> None:
    """El JWKS publica `kid-1` con la public key 1, pero el token está firmado
    con la private key 2. La firma no debe validar."""
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_2, kid="kid-1")

    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token(token)
    assert exc_info.value.code == AuthErrorCode.INVALID_TOKEN


async def test_rechaza_kid_desconocido(rsa_key_1: RSAPrivateKey) -> None:
    """El token apunta a `kid-xxx` pero el JWKS solo tiene `kid-1`.

    Refresca el JWKS y, al seguir sin estar, AuthError(INVALID_TOKEN).
    """
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    token = _sign(rsa_key_1, kid="kid-xxx")

    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token(token)
    assert exc_info.value.code == AuthErrorCode.INVALID_TOKEN
    assert "kid" in str(exc_info.value).lower()


async def test_rechaza_token_sin_kid(rsa_key_1: RSAPrivateKey) -> None:
    """Token sin claim 'kid' en el header (header inválido)."""
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    provider = _make_provider(jwks_payload=jwks)
    # Firmamos sin pasar headers extra.
    token = jwt.encode(
        {
            "sub": "x",
            "iss": ISSUER,
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        rsa_key_1,
        algorithm="RS256",
    )
    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token(token)
    assert exc_info.value.code == AuthErrorCode.INVALID_TOKEN


async def test_rechaza_token_basura() -> None:
    jwks: dict[str, Any] = {"keys": []}
    provider = _make_provider(jwks_payload=jwks)
    with pytest.raises(AuthError) as exc_info:
        await provider.verificar_token("esto-no-es-un-jwt")
    assert exc_info.value.code == AuthErrorCode.INVALID_TOKEN


# ---------------------------------------------------------------------------
# Cache de JWKS
# ---------------------------------------------------------------------------


async def test_cache_evita_refetch_dentro_del_ttl(rsa_key_1: RSAPrivateKey) -> None:
    """Dos verificaciones consecutivas dentro del TTL solo descargan el JWKS una vez."""
    jwks = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=jwks)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ClerkAuthProvider(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        http_client=client,
    )
    token = _sign(rsa_key_1, kid="kid-1")
    await provider.verificar_token(token)
    await provider.verificar_token(token)
    await provider.verificar_token(token)
    assert call_count == 1  # un solo fetch


async def test_kid_nuevo_dispara_refetch(
    rsa_key_1: RSAPrivateKey, rsa_key_2: RSAPrivateKey
) -> None:
    """Si llega un kid no conocido, refrescamos. Si en el segundo intento
    está, lo aceptamos."""
    # Primer fetch: solo kid-1. Segundo fetch: ambos.
    jwks_initial: dict[str, Any] = {"keys": [_jwk_from_rsa(rsa_key_1, "kid-1")]}
    jwks_rotated: dict[str, Any] = {
        "keys": [
            _jwk_from_rsa(rsa_key_1, "kid-1"),
            _jwk_from_rsa(rsa_key_2, "kid-2"),
        ]
    }
    fetches = [jwks_initial, jwks_rotated]

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = fetches.pop(0) if len(fetches) > 1 else fetches[0]
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Clock fake que avanza: forzamos cache expiry para que el segundo verify
    # refetche y vea kid-2.
    base = datetime.now(UTC)
    clock_values = iter([base, base, base + timedelta(hours=2), base + timedelta(hours=2)])

    def clock() -> datetime:
        return next(clock_values)

    provider = ClerkAuthProvider(
        issuer=ISSUER,
        jwks_url=JWKS_URL,
        http_client=client,
        clock=clock,
    )

    token1 = _sign(rsa_key_1, kid="kid-1")
    await provider.verificar_token(token1)  # ok con la versión inicial del JWKS

    token2 = _sign(rsa_key_2, kid="kid-2")
    claims = await provider.verificar_token(token2)
    assert claims.sub == "user_test_1"
