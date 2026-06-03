"""Webhooks Meta WhatsApp Cloud API (feat-41.3).

Dos endpoints:

- `GET /webhooks/whatsapp` — handshake de verificación. Meta lo
  pega cuando configurás el webhook en App Manager. Devuelve el
  `hub.challenge` solo si `hub.verify_token` matchea el de settings.

- `POST /webhooks/whatsapp` — eventos. Meta firma cada POST con
  `X-Hub-Signature-256: sha256=<hex>` usando el App Secret. Verificamos
  la firma sobre el raw body ANTES de parsear. Si valida → invocamos
  `ProcesarWebhookWhatsApp` y devolvemos 200.

Devolver 200 incluso en errores parciales internos es a propósito:
Meta reintenta automáticamente todo lo que no devuelva 200. Si nos
quedamos con un payload que no podemos procesar (ej. cambios de
schema), preferimos perder ese evento que enchular la queue de Meta.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from praxis.api.deps import SessionDep
from praxis.application.use_cases import ProcesarWebhookWhatsApp
from praxis.config import get_settings
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
)
from praxis.infrastructure.whatsapp.webhooks import (
    parsear_webhook,
    verificar_firma_meta,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])


# ---------------------------------------------------------------------------
# GET — handshake de verificación
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="Handshake de verificación de webhook Meta",
)
async def verificar_handshake(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> int:
    """Meta llama acá una vez cuando configurás el webhook URL en App
    Manager. Devolvemos el `hub.challenge` literal si el token matchea
    el `meta_whatsapp_webhook_verify_token` de settings."""
    settings = get_settings()
    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hub.mode debe ser 'subscribe'",
        )
    expected = settings.meta_whatsapp_webhook_verify_token
    if not expected:
        log.warning("Webhook handshake recibido pero verify_token no configurado")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="webhook_verify_token no configurado en el servidor",
        )
    if hub_verify_token != expected:
        log.warning(
            "Webhook handshake con token incorrecto (recibido len=%d)",
            len(hub_verify_token),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="verify_token incorrecto",
        )
    # Meta espera el challenge como INTEGER (raw, sin JSON).
    try:
        return int(hub_challenge)
    except ValueError:
        # Algunos brokers mandan string — devolvemos 0 si no parsea.
        return 0


# ---------------------------------------------------------------------------
# POST — eventos
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Recibe events Meta WhatsApp (status + inbound)",
)
async def recibir_evento(
    request: Request,
    session: SessionDep,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, int | list[str]]:
    """Verifica firma HMAC + parsea + delega al caso de uso.

    Devuelve estadísticas para tracing/Flower; Meta ignora el body."""
    settings = get_settings()
    app_secret = settings.meta_whatsapp_webhook_app_secret
    if not app_secret:
        log.error("Webhook POST recibido pero app_secret no configurado")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="webhook_app_secret no configurado en el servidor",
        )

    body_raw = await request.body()
    if not verificar_firma_meta(
        body_raw=body_raw,
        header_signature=x_hub_signature_256,
        app_secret=app_secret,
    ):
        log.warning(
            "Webhook POST con firma inválida (sig=%r, body_len=%d)",
            x_hub_signature_256, len(body_raw),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="firma HMAC inválida",
        )

    try:
        payload = json.loads(body_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        log.warning("Webhook payload no es JSON UTF-8 válido: %s", exc)
        # Devolvemos 200 para que Meta no reintente; ya logueamos.
        return {"statuses_actualizados": 0, "errores": [str(exc)]}

    evento = parsear_webhook(payload)
    uc = ProcesarWebhookWhatsApp(
        envios=SqlAlchemyEnvioWhatsAppRepository(session),
        destinatarios=SqlAlchemyDestinatarioRepository(session),
        despachos=SqlAlchemyDespachoRepository(session),
    )
    resultado = await uc.ejecutar(evento)
    await session.commit()
    log.info(
        "Webhook procesado: %d statuses, %d opt-ins, %d opt-outs, "
        "%d desconocidos, %d ignorados",
        resultado.statuses_actualizados,
        resultado.opt_ins_aplicados,
        resultado.opt_outs_aplicados,
        resultado.statuses_desconocidos,
        resultado.mensajes_ignorados,
    )
    return {
        "statuses_actualizados": resultado.statuses_actualizados,
        "statuses_desconocidos": resultado.statuses_desconocidos,
        "opt_ins_aplicados": resultado.opt_ins_aplicados,
        "opt_outs_aplicados": resultado.opt_outs_aplicados,
        "mensajes_ignorados": resultado.mensajes_ignorados,
        "errores": resultado.errores,
    }
