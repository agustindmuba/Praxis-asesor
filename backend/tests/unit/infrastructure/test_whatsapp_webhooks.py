"""Tests de helpers de webhooks Meta WhatsApp (feat-41.3).

- `verificar_firma_meta`: HMAC SHA-256 OK/KO + edge cases (sin header,
  prefijo inválido, body distinto).
- `parsear_webhook`: extrae status updates + inbound messages,
  tolerante a payloads malformados.
- `clasificar_inbound`: SI/SÍ/OK/etc. → opt_in, NO/BAJA/etc. →
  opt_out, otros → None.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from praxis.domain import EstadoEnvio
from praxis.infrastructure.whatsapp.webhooks import (
    clasificar_inbound,
    parsear_webhook,
    verificar_firma_meta,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# verificar_firma_meta
# ---------------------------------------------------------------------------


def _firmar(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()


class TestVerificarFirma:
    def test_ok(self) -> None:
        body = b'{"foo":"bar"}'
        secret = "topsecret"
        sig = _firmar(body, secret)
        assert verificar_firma_meta(
            body_raw=body, header_signature=sig, app_secret=secret,
        ) is True

    def test_firma_distinta_falla(self) -> None:
        body = b'{"foo":"bar"}'
        sig = _firmar(body, "secret_correcto")
        assert verificar_firma_meta(
            body_raw=body, header_signature=sig, app_secret="secret_otro",
        ) is False

    def test_body_modificado_falla(self) -> None:
        secret = "topsecret"
        sig = _firmar(b'{"foo":"bar"}', secret)
        assert verificar_firma_meta(
            body_raw=b'{"foo":"baz"}',
            header_signature=sig,
            app_secret=secret,
        ) is False

    def test_sin_header_falla(self) -> None:
        assert verificar_firma_meta(
            body_raw=b"x",
            header_signature=None,
            app_secret="x",
        ) is False

    def test_prefijo_invalido_falla(self) -> None:
        assert verificar_firma_meta(
            body_raw=b"x",
            header_signature="md5=abcd",
            app_secret="x",
        ) is False


# ---------------------------------------------------------------------------
# parsear_webhook
# ---------------------------------------------------------------------------


class TestParsearWebhook:
    def test_status_delivered(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.X",
                            "status": "delivered",
                            "timestamp": "1717000000",
                            "recipient_id": "5491155551234",
                        }],
                    },
                }],
            }],
        }
        evento = parsear_webhook(payload)
        assert len(evento.statuses) == 1
        assert evento.statuses[0].message_id_meta == "wamid.X"
        assert evento.statuses[0].nuevo_estado == EstadoEnvio.ENTREGADO
        assert evento.statuses[0].error is None

    def test_status_failed_con_error(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.X",
                            "status": "failed",
                            "errors": [{
                                "code": 131026,
                                "title": "Recipient opted out",
                            }],
                        }],
                    },
                }],
            }],
        }
        evento = parsear_webhook(payload)
        assert len(evento.statuses) == 1
        assert evento.statuses[0].nuevo_estado == EstadoEnvio.FALLIDO
        assert evento.statuses[0].error == "Recipient opted out"

    def test_status_desconocido_se_ignora(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [
                            {"id": "wamid.X", "status": "pending_review"},
                        ],
                    },
                }],
            }],
        }
        assert parsear_webhook(payload).statuses == []

    def test_inbound_texto(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "5491155551234",
                            "id": "wamid.in.1",
                            "timestamp": "1717000001",
                            "text": {"body": "SI"},
                            "type": "text",
                        }],
                    },
                }],
            }],
        }
        evento = parsear_webhook(payload)
        assert len(evento.mensajes) == 1
        m = evento.mensajes[0]
        assert m.from_e164 == "+5491155551234"
        assert m.body == "SI"

    def test_inbound_no_texto_se_ignora(self) -> None:
        """v1: solo procesamos `type: text`."""
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "549...",
                            "id": "wamid.x",
                            "type": "audio",
                            "audio": {"id": "..."},
                        }],
                    },
                }],
            }],
        }
        assert parsear_webhook(payload).mensajes == []

    def test_payload_basura_no_explota(self) -> None:
        evento = parsear_webhook({})
        assert evento.statuses == []
        assert evento.mensajes == []

        evento = parsear_webhook({"entry": "no_es_una_lista"})  # type: ignore[arg-type]
        assert evento.statuses == []
        assert evento.mensajes == []

    def test_combinacion_statuses_y_mensajes(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [
                            {"id": "wamid.S1", "status": "sent"},
                            {"id": "wamid.S2", "status": "read"},
                        ],
                        "messages": [
                            {
                                "from": "549...",
                                "id": "wamid.M1",
                                "type": "text",
                                "text": {"body": "NO"},
                            },
                        ],
                    },
                }],
            }],
        }
        evento = parsear_webhook(payload)
        assert len(evento.statuses) == 2
        assert len(evento.mensajes) == 1


# ---------------------------------------------------------------------------
# clasificar_inbound
# ---------------------------------------------------------------------------


class TestClasificarInbound:
    @pytest.mark.parametrize("body,esperado", [
        ("SI", "opt_in"),
        ("sí", "opt_in"),
        ("ok", "opt_in"),
        ("OKAY", "opt_in"),
        ("acepto", "opt_in"),
        ("Confirmo!", "opt_in"),
        ("yes", "opt_in"),
        ("NO", "opt_out"),
        ("baja", "opt_out"),
        ("cancelar", "opt_out"),
        ("STOP", "opt_out"),
        ("unsubscribe", "opt_out"),
        ("hola, ¿cómo va?", None),
        ("123", None),
        ("", None),
    ])
    def test_clasificacion(self, body: str, esperado: str | None) -> None:
        assert clasificar_inbound(body) == esperado


# ---------------------------------------------------------------------------
# Smoke: payload completo (round-trip parse + class)
# ---------------------------------------------------------------------------


def test_smoke_payload_meta_realista() -> None:
    """Verifica que un payload tipo Meta de verdad parsee bien."""
    payload_str = """
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "id": "1234567890",
        "changes": [{
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "5491155550000",
              "phone_number_id": "100"
            },
            "statuses": [{
              "id": "wamid.HBgM5491155551234FQIAERgSNkY0RjU2NDg2RkExNUVDOTkA",
              "status": "delivered",
              "timestamp": "1717000010",
              "recipient_id": "5491155551234"
            }],
            "messages": [{
              "from": "5491155551234",
              "id": "wamid.in.x",
              "timestamp": "1717000020",
              "text": {"body": "Si"},
              "type": "text"
            }]
          }
        }]
      }]
    }
    """
    evento = parsear_webhook(json.loads(payload_str))
    assert len(evento.statuses) == 1
    assert evento.statuses[0].nuevo_estado == EstadoEnvio.ENTREGADO
    assert len(evento.mensajes) == 1
    assert clasificar_inbound(evento.mensajes[0].body) == "opt_in"
