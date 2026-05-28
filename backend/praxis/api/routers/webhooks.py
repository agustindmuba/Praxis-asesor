"""Router /webhooks/clerk — recibe eventos firmados por Clerk via Svix."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from praxis.api.deps import SessionDep
from praxis.application import SincronizarUsuarioDesdeClerk
from praxis.config import Settings, get_settings
from praxis.infrastructure.auth.webhook_verify import (
    SvixWebhookVerifier,
    WebhookSignatureError,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyUsuarioRepository,
)

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# Singleton del verifier (depende del secret, que viene de settings).
_verifier: SvixWebhookVerifier | None = None


def get_webhook_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SvixWebhookVerifier:
    """Devuelve un verificador construido con el secret de settings.

    Si el secret no está configurado, devolvemos 503 (no podemos verificar).
    """
    global _verifier
    if _verifier is not None:
        return _verifier
    if not settings.clerk_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook de Clerk no configurado (falta CLERK_WEBHOOK_SECRET)",
        )
    _verifier = SvixWebhookVerifier(settings.clerk_webhook_secret)
    return _verifier


@router.post(
    "/clerk",
    summary="Receptor de webhooks de Clerk (Svix)",
    status_code=status.HTTP_200_OK,
)
async def webhook_clerk(
    request: Request,
    session: SessionDep,
    verifier: Annotated[SvixWebhookVerifier, Depends(get_webhook_verifier)],
) -> dict[str, str]:
    """Procesa un evento firmado del lado de Clerk.

    Pasos:
    1. Leer body crudo (Svix firma sobre los bytes exactos, no sobre el JSON
       reparseado).
    2. Verificar firma con `svix-id`, `svix-timestamp`, `svix-signature`.
    3. Despachar al caso de uso según `type`.
    4. Devolver `{"status": "processed"|"ignored"}`.

    Errores:
    - 400: body no JSON, faltan headers Svix, payload inválido (ej. sin email).
    - 401: firma incorrecta o headers Svix ausentes.
    - 503: webhook no configurado (handled en el dep).
    """
    raw_body = await request.body()
    # Si falta header de Svix, lo tratamos como 400 (no 401) — es input mal
    # formado del cliente, no un intento de forge.
    headers = dict(request.headers)
    missing = [
        h
        for h in ("svix-id", "svix-timestamp", "svix-signature")
        if h not in {k.lower() for k in headers}
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Faltan headers Svix: {', '.join(missing)}",
        )

    try:
        payload = verifier.verify(raw_body=raw_body, headers=headers)
    except WebhookSignatureError as exc:
        log.warning("clerk.webhook_invalid_signature", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firma del webhook inválida",
        ) from exc

    evento_tipo = payload.get("type")
    data = payload.get("data")
    if not isinstance(evento_tipo, str) or not isinstance(data, dict):
        log.warning(
            "clerk.webhook_payload_invalid",
            tipo=evento_tipo,
            data_type=type(data).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload del webhook sin 'type' o 'data' válidos",
        )

    sync = SincronizarUsuarioDesdeClerk(usuarios=SqlAlchemyUsuarioRepository(session))
    try:
        resultado = await sync.execute(evento_tipo=evento_tipo, data=data)
    except ValueError as exc:
        # Errores de parseo del payload (email inválido, etc.) → 400.
        log.warning("clerk.webhook_payload_error", tipo=evento_tipo, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await session.commit()
    return {"status": resultado}


# Para tests / debugging: aceptamos limpiar el singleton del verifier.
def _reset_verifier_for_tests() -> None:
    global _verifier
    _verifier = None


__all__ = ["get_webhook_verifier", "router"]
