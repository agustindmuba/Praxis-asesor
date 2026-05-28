"""Tests integración de la dependency `current_context` de FastAPI.

Levantamos una app de prueba con un endpoint protegido y verificamos
el mapeo error → HTTP status. La sesión usa SQLite in-memory; el auth
provider es un fake controlado para no acoplar a Clerk.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.api.deps import current_context, get_auth_provider, get_session
from praxis.application.ports import AuthProvider
from praxis.domain import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    Despacho,
    MembresiaDespacho,
    RequestContext,
    Rol,
    Usuario,
)
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyUsuarioRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fake auth provider configurable por test
# ---------------------------------------------------------------------------


class FakeAuth(AuthProvider):
    """Lookup por token → claims. Cualquier otro token → AuthError(INVALID_TOKEN)."""

    def __init__(self, valid_tokens: dict[str, AuthClaims]) -> None:
        self._tokens = valid_tokens

    async def verificar_token(self, token: str) -> AuthClaims:
        claims = self._tokens.get(token)
        if claims is None:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "token desconocido en fake")
        return claims


# ---------------------------------------------------------------------------
# Fixtures: DB + app
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seed(session: AsyncSession) -> dict[str, UUID | str]:
    """Crea usuario, despacho, membresía. Devuelve los UUIDs + token válido."""
    despacho = await SqlAlchemyDespachoRepository(session).crear(
        Despacho(id=uuid4(), nombre="Despacho Test")
    )
    usuario = await SqlAlchemyUsuarioRepository(session).crear(
        Usuario(
            id=uuid4(),
            email="ana@x.com",
            nombre="Ana",
            auth_provider_id="clerk_user_1",
        )
    )
    await SqlAlchemyMembresiaDespachoRepository(session).agregar(
        MembresiaDespacho(
            usuario_id=usuario.id,
            despacho_id=despacho.id,
            rol=Rol.ASESOR,
        )
    )
    await session.commit()
    return {
        "usuario_id": usuario.id,
        "despacho_id": despacho.id,
        "token": "valid-token-ana",
    }


def _build_app(*, session: AsyncSession, auth: AuthProvider) -> FastAPI:
    """Construye una app de prueba con un endpoint protegido + overrides."""
    app = FastAPI()

    @app.get("/me")
    async def me(
        ctx: Annotated[RequestContext, Depends(current_context)],
    ) -> dict[str, str]:
        return {
            "usuario_email": ctx.usuario.email,
            "despacho_nombre": ctx.despacho.nombre,
            "rol": ctx.rol.value,
        }

    # Override de get_session: usa la misma sesión del test (no abre nuevas).
    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_auth_provider] = lambda: auth
    return app


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_endpoint_protegido_responde_200_con_token_valido(
    session: AsyncSession, seed: dict[str, UUID | str]
) -> None:
    auth = FakeAuth({"valid-token-ana": AuthClaims(sub="clerk_user_1")})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)

    response = client.get(
        "/me",
        headers={
            "Authorization": "Bearer valid-token-ana",
            "X-Despacho-Id": str(seed["despacho_id"]),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["usuario_email"] == "ana@x.com"
    assert body["despacho_nombre"] == "Despacho Test"
    assert body["rol"] == "asesor"


# ---------------------------------------------------------------------------
# Header errors (no llegan al caso de uso)
# ---------------------------------------------------------------------------


def test_401_si_falta_authorization(session: AsyncSession, seed: dict[str, UUID | str]) -> None:
    auth = FakeAuth({})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get("/me", headers={"X-Despacho-Id": str(seed["despacho_id"])})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_401_si_authorization_mal_formado(
    session: AsyncSession, seed: dict[str, UUID | str]
) -> None:
    auth = FakeAuth({})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": "NotBearer xxx",
            "X-Despacho-Id": str(seed["despacho_id"]),
        },
    )
    assert response.status_code == 401


def test_400_si_falta_x_despacho_id(session: AsyncSession) -> None:
    auth = FakeAuth({"t": AuthClaims(sub="clerk_user_1")})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get("/me", headers={"Authorization": "Bearer t"})
    assert response.status_code == 400


def test_400_si_x_despacho_id_no_es_uuid(session: AsyncSession) -> None:
    auth = FakeAuth({"t": AuthClaims(sub="clerk_user_1")})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get(
        "/me",
        headers={"Authorization": "Bearer t", "X-Despacho-Id": "no-soy-un-uuid"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Errors del caso de uso → HTTP status
# ---------------------------------------------------------------------------


def test_401_si_token_invalido(session: AsyncSession, seed: dict[str, UUID | str]) -> None:
    """Token que el AuthProvider rechaza → 401."""
    auth = FakeAuth({})  # ningún token válido
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": "Bearer cualquier-cosa",
            "X-Despacho-Id": str(seed["despacho_id"]),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"


def test_401_si_usuario_no_provisionado(session: AsyncSession, seed: dict[str, UUID | str]) -> None:
    """Token válido pero el sub no matchea ningún usuario en DB."""
    auth = FakeAuth({"t": AuthClaims(sub="clerk_user_FANTASMA")})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": "Bearer t",
            "X-Despacho-Id": str(seed["despacho_id"]),
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "user_not_provisioned"


def test_403_si_no_es_miembro_del_despacho(
    session: AsyncSession, seed: dict[str, UUID | str]
) -> None:
    """El usuario existe pero apunta a un despacho_id donde no es miembro."""
    auth = FakeAuth({"t": AuthClaims(sub="clerk_user_1")})
    app = _build_app(session=session, auth=auth)
    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": "Bearer t",
            "X-Despacho-Id": str(uuid4()),  # despacho inexistente
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_a_member"
    # 403 no manda WWW-Authenticate.
    assert "www-authenticate" not in {k.lower() for k in response.headers}
