"""Helpers para procesar webhooks de Meta WhatsApp Cloud API.

Dos tipos de eventos vienen al endpoint POST /webhooks/whatsapp:

1. **Status updates**: cuando un mensaje que mandamos cambia de
   estado (sent/delivered/read/failed). Identificamos el envío por
   `message_id_meta` y actualizamos `EnvioWhatsApp.estado`.

2. **Inbound messages**: cuando el usuario nos manda un texto. Para
   v1 sólo nos interesa SI / NO (opt-in / opt-out) y todo lo demás
   se loguea.

Verificación de firma:

Meta firma cada POST con `X-Hub-Signature-256: sha256=<hex>` usando
HMAC-SHA256 del raw body con la app_secret como clave. Rechazamos
todo lo que no verifique para prevenir spoofing.

Estructura del payload (relevante):

```
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "...",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {...},
            "statuses": [
              {
                "id": "wamid.HBgM...",
                "status": "delivered",  # sent|delivered|read|failed
                "timestamp": "...",
                "recipient_id": "5491155551234",
                "errors": [{"code": ..., "title": "..."}],  # opcional
              }
            ],
            "messages": [
              {
                "from": "5491155551234",
                "id": "wamid.HBgN...",
                "timestamp": "...",
                "text": {"body": "SI"},
                "type": "text",
              }
            ]
          }
        }
      ]
    }
  ]
}
```
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

from praxis.domain import EstadoEnvio

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verificación de firma HMAC
# ---------------------------------------------------------------------------


def verificar_firma_meta(
    *,
    body_raw: bytes,
    header_signature: str | None,
    app_secret: str,
) -> bool:
    """True si la firma del header coincide con el HMAC del raw body.

    Args:
        body_raw: bytes EXACTOS del request body (no parseados).
        header_signature: valor del header `X-Hub-Signature-256`,
            con formato `sha256=<hex>`. Si es None → False.
        app_secret: App Secret de la app de Meta.

    Usa `hmac.compare_digest` para resistir timing attacks.
    """
    if not header_signature or not header_signature.startswith("sha256="):
        return False
    esperado = header_signature[len("sha256="):]
    calculado = hmac.new(
        app_secret.encode("utf-8"),
        body_raw,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperado, calculado)


# ---------------------------------------------------------------------------
# Parseo del payload
# ---------------------------------------------------------------------------


# Mapeo de strings de Meta → EstadoEnvio del dominio.
# Meta usa: sent, delivered, read, failed.
_META_STATUS_MAP: dict[str, EstadoEnvio] = {
    "sent": EstadoEnvio.ENVIADO,
    "delivered": EstadoEnvio.ENTREGADO,
    "read": EstadoEnvio.LEIDO,
    "failed": EstadoEnvio.FALLIDO,
}


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    """Snapshot de un cambio de estado para `EnvioWhatsApp`."""

    message_id_meta: str
    nuevo_estado: EstadoEnvio
    error: str | None  # solo si nuevo_estado == FALLIDO


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Mensaje entrante de un usuario. v1 solo procesamos `text`."""

    from_e164: str  # con `+` ya prefijado
    body: str
    message_id_meta: str


@dataclass(frozen=True, slots=True)
class WebhookEvento:
    """Resultado de parsear un payload completo del webhook."""

    statuses: list[StatusUpdate]
    mensajes: list[InboundMessage]


def parsear_webhook(payload: dict[str, Any]) -> WebhookEvento:
    """Extrae status updates + mensajes entrantes de un payload Meta.

    Tolerante: si el payload tiene forma distinta (ej. cambios de
    eventos que no soportamos), simplemente devuelve listas vacías.
    """
    statuses: list[StatusUpdate] = []
    mensajes: list[InboundMessage] = []

    entries = payload.get("entry", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return WebhookEvento(statuses=[], mensajes=[])

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            # Status updates.
            for s in value.get("statuses", []) or []:
                if not isinstance(s, dict):
                    continue
                sid = s.get("id")
                sst = s.get("status")
                if not isinstance(sid, str) or not isinstance(sst, str):
                    continue
                estado = _META_STATUS_MAP.get(sst)
                if estado is None:
                    log.info(
                        "Webhook Meta: status '%s' desconocido para %s",
                        sst, sid,
                    )
                    continue
                error_msg: str | None = None
                if estado == EstadoEnvio.FALLIDO:
                    errores = s.get("errors")
                    if isinstance(errores, list) and errores:
                        e0 = errores[0]
                        if isinstance(e0, dict):
                            error_msg = str(
                                e0.get("title")
                                or e0.get("message")
                                or e0.get("code")
                                or "fallido_sin_detalle",
                            )
                statuses.append(
                    StatusUpdate(
                        message_id_meta=sid,
                        nuevo_estado=estado,
                        error=error_msg,
                    ),
                )
            # Inbound messages.
            for m in value.get("messages", []) or []:
                if not isinstance(m, dict):
                    continue
                if m.get("type") != "text":
                    continue
                text_obj = m.get("text", {})
                body = (
                    text_obj.get("body", "").strip()
                    if isinstance(text_obj, dict)
                    else ""
                )
                from_raw = m.get("from", "")
                mid = m.get("id", "")
                if not body or not isinstance(from_raw, str):
                    continue
                # Meta manda el `from` sin `+`; lo agregamos para
                # tener consistencia con `telefono_e164` del dominio.
                from_e164 = (
                    from_raw if from_raw.startswith("+") else f"+{from_raw}"
                )
                mensajes.append(
                    InboundMessage(
                        from_e164=from_e164,
                        body=body,
                        message_id_meta=str(mid),
                    ),
                )

    return WebhookEvento(statuses=statuses, mensajes=mensajes)


# ---------------------------------------------------------------------------
# Clasificación de mensajes inbound
# ---------------------------------------------------------------------------


# Palabras que cuentan como opt-in (afirmar suscripción).
_OPT_IN_PALABRAS = frozenset({
    "si", "sí", "ok", "okay", "confirmo", "acepto", "yes",
})

# Palabras que cuentan como opt-out (cancelar).
_OPT_OUT_PALABRAS = frozenset({
    "no", "baja", "cancelar", "stop", "darme de baja",
    "no quiero", "unsubscribe",
})


def clasificar_inbound(body: str) -> str | None:
    """Clasifica el body del usuario como `opt_in`, `opt_out` o `None`
    (no procesable v1).

    Normaliza minúsculas + strip de puntuación final.
    """
    normalizado = body.strip().lower().rstrip(".!?¡¿")
    if normalizado in _OPT_IN_PALABRAS:
        return "opt_in"
    if normalizado in _OPT_OUT_PALABRAS:
        return "opt_out"
    return None
