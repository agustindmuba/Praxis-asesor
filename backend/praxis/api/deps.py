"""Dependencies de FastAPI compartidas entre routers.

`current_context()` es el guardian de los endpoints protegidos:
- Extrae el bearer token del header `Authorization`.
- Extrae el `despacho_id` del header `X-Despacho-Id`.
- Llama al caso de uso `ResolverContextoRequest` para obtener un
  `RequestContext` validado (usuario + despacho + rol).
- Mapea `AuthError` a HTTPException con el status code apropiado.

Ver `docs/specs/09-auth-multitenancy.md` §"FastAPI dep".
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application import (
    AuthProvider,
    LlmProvider,
    ResolverContextoRequest,
)
from praxis.application.ports import WhatsAppSender
from praxis.config import Settings, get_settings
from praxis.domain import AuthClaims, AuthError, AuthErrorCode, RequestContext
from praxis.infrastructure.auth import ClerkAuthProvider, DevAuthProvider
from praxis.infrastructure.db.engine import get_session
from praxis.infrastructure.llm import FakeLlmProvider
from praxis.infrastructure.llm.anthropic_provider import AnthropicLlmProvider
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyUsuarioRepository,
)
from praxis.infrastructure.whatsapp import (
    FakeWhatsAppSender,
    WhatsAppCloudApiSender,
)

# ----------------------------------------------------------------------
# DB session
# ----------------------------------------------------------------------

# Reutilizamos `get_session` de infrastructure (yield AsyncSession por request).
SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ----------------------------------------------------------------------
# Auth provider (singleton por proceso)
# ----------------------------------------------------------------------


_auth_provider: AuthProvider | None = None


def get_auth_provider(settings: Annotated[Settings, Depends(get_settings)]) -> AuthProvider:
    """Devuelve un singleton de AuthProvider construido desde settings.

    Tres modos:
    1. Clerk configurado → `ClerkAuthProvider` (producción y dev real).
    2. Sin Clerk + `ENV=dev` → `DevAuthProvider` que acepta tokens fake
       con prefijo `dev:`. SOLO para que un dev pueda probar la UI sin
       configurar Clerk. Inseguro por design.
    3. Sin Clerk + ENV != dev → stub que siempre devuelve 401. Esto
       evita arrancar prod accidentalmente sin auth.
    """
    global _auth_provider
    if _auth_provider is not None:
        return _auth_provider

    if settings.clerk_issuer and settings.clerk_jwks_url:
        _auth_provider = ClerkAuthProvider(
            issuer=settings.clerk_issuer,
            jwks_url=settings.clerk_jwks_url,
            audience=settings.clerk_audience,
        )
    elif settings.env == "dev":
        _auth_provider = DevAuthProvider()
    else:
        _auth_provider = _UnconfiguredAuthProvider()
    return _auth_provider


class _UnconfiguredAuthProvider(AuthProvider):
    """Stub que falla siempre. Se usa cuando Clerk no está configurado."""

    async def verificar_token(self, token: str) -> AuthClaims:
        del token  # no usado: este stub falla siempre.
        raise AuthError(
            AuthErrorCode.INVALID_TOKEN,
            "Auth provider no configurado (faltan CLERK_ISSUER/CLERK_JWKS_URL)",
        )


# ----------------------------------------------------------------------
# Caso de uso ResolverContextoRequest
# ----------------------------------------------------------------------


def get_resolver(
    session: SessionDep,
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> ResolverContextoRequest:
    """Arma el caso de uso con repos concretos sobre la sesión actual."""
    return ResolverContextoRequest(
        auth=auth,
        usuarios=SqlAlchemyUsuarioRepository(session),
        despachos=SqlAlchemyDespachoRepository(session),
        membresias=SqlAlchemyMembresiaDespachoRepository(session),
    )


# ----------------------------------------------------------------------
# Headers
# ----------------------------------------------------------------------


def _extract_bearer(authorization: str | None) -> str:
    """Extrae el token del header `Authorization: Bearer <token>`.

    Raises HTTPException 401 si falta o tiene formato inválido.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta header Authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header Authorization mal formado (se esperaba 'Bearer <token>')",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


def _parse_despacho_id(raw: str | None) -> UUID:
    """Parsea el header X-Despacho-Id como UUID. 400 si falta o no parsea."""
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falta header X-Despacho-Id",
        )
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-Despacho-Id no es un UUID válido: {raw!r}",
        ) from exc


# ----------------------------------------------------------------------
# current_context: el guard principal
# ----------------------------------------------------------------------


# Códigos que mapean a 401 (problemas de identidad del usuario).
_CODES_401 = {
    AuthErrorCode.INVALID_TOKEN,
    AuthErrorCode.TOKEN_EXPIRED,
    AuthErrorCode.WRONG_ISSUER,
    AuthErrorCode.USER_NOT_PROVISIONED,
}
# Códigos que mapean a 403 (autenticado pero no autorizado en ese tenant).
_CODES_403 = {
    AuthErrorCode.NOT_A_MEMBER,
    AuthErrorCode.DESPACHO_NOT_FOUND,
}


async def current_context(
    resolver: Annotated[ResolverContextoRequest, Depends(get_resolver)],
    authorization: Annotated[str | None, Header()] = None,
    x_despacho_id: Annotated[str | None, Header()] = None,
) -> RequestContext:
    """Resuelve el contexto autenticado de un request.

    Cualquier endpoint protegido pone:
        `ctx: RequestContext = Depends(current_context)`
    y obtiene usuario + despacho + rol ya verificados.
    """
    token = _extract_bearer(authorization)
    despacho_id = _parse_despacho_id(x_despacho_id)
    try:
        return await resolver.execute(token=token, despacho_id=despacho_id)
    except AuthError as exc:
        if exc.code in _CODES_401:
            http_status = status.HTTP_401_UNAUTHORIZED
            headers = {"WWW-Authenticate": "Bearer"}
        else:
            http_status = status.HTTP_403_FORBIDDEN
            headers = None
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code.value, "detail": exc.detalle},
            headers=headers,
        ) from exc


CurrentContext = Annotated[RequestContext, Depends(current_context)]


# ----------------------------------------------------------------------
# LLM provider (singleton por proceso)
# ----------------------------------------------------------------------


_llm_provider: LlmProvider | None = None


def get_llm_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LlmProvider:
    """Devuelve un singleton del LlmProvider.

    Selección:
    - Si `settings.anthropic_api_key` está seteada → `AnthropicLlmProvider`
      (Sonnet 4.5 real con prompt caching, gasta API).
    - Sino → `FakeLlmProvider` (default en dev, costo cero).

    Recordatorio operativo: setear cap mensual en Anthropic Console
    (Settings → Limits) para acotar el gasto. Ver
    `docs/runbooks/anthropic-llm.md`.
    """
    global _llm_provider
    if _llm_provider is not None:
        return _llm_provider

    if settings.anthropic_api_key:
        _llm_provider = AnthropicLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    else:
        _llm_provider = FakeLlmProvider()
    return _llm_provider


LlmProviderDep = Annotated[LlmProvider, Depends(get_llm_provider)]


# ---------------------------------------------------------------------------
# WhatsAppSender (spec 17, feat-41.2)
# ---------------------------------------------------------------------------


_whatsapp_sender: WhatsAppSender | None = None


def get_whatsapp_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhatsAppSender:
    """Devuelve un singleton del WhatsAppSender.

    Selección:
    - Si `meta_whatsapp_token` + `meta_whatsapp_phone_number_id` están
      ambos seteados → `WhatsAppCloudApiSender` (HTTP real a Meta).
    - Sino → `FakeWhatsAppSender` (default en dev, sin red ni gasto).

    Recordatorio operativo: Meta cobra por conversación iniciada
    (~$0.005-0.05 USD según país). Configurar límite de gasto en App
    Manager → Limits. Ver `docs/runbooks/meta-whatsapp.md` (a redactar
    en feat-41.6).
    """
    global _whatsapp_sender
    if _whatsapp_sender is not None:
        return _whatsapp_sender

    if (
        settings.meta_whatsapp_token
        and settings.meta_whatsapp_phone_number_id
    ):
        _whatsapp_sender = WhatsAppCloudApiSender(
            access_token=settings.meta_whatsapp_token,
            phone_number_id=settings.meta_whatsapp_phone_number_id,
        )
    else:
        _whatsapp_sender = FakeWhatsAppSender()
    return _whatsapp_sender


WhatsAppSenderDep = Annotated[
    WhatsAppSender, Depends(get_whatsapp_sender),
]


__all__ = [
    "CurrentContext",
    "LlmProviderDep",
    "SessionDep",
    "WhatsAppSenderDep",
    "current_context",
    "get_auth_provider",
    "get_llm_provider",
    "get_resolver",
    "get_session",
    "get_whatsapp_sender",
]
