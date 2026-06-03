"""Tests de `FakeWhatsAppSender` y `WhatsAppCloudApiSender` (feat-41.2).

- FakeWhatsAppSender: registra envíos, simula éxito/fallo/rechazo.
- WhatsAppCloudApiSender: HTTP real mockeado con `httpx.MockTransport`.
  Cubre payload correcto, parsing de respuesta 200, errores con
  códigos de rechazo (131026 = opt-out, 131047 = plantilla no
  aprobada), errores transitorios (500), errores de red.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from praxis.infrastructure.whatsapp import (
    META_GRAPH_API_BASE,
    FakeWhatsAppSender,
    WhatsAppCloudApiSender,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# FakeWhatsAppSender
# ---------------------------------------------------------------------------


class TestFakeWhatsAppSender:
    async def test_modo_exitoso_default(self) -> None:
        sender = FakeWhatsAppSender()
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="briefing_diario",
            idioma="es_AR",
            body_params_ordered=["Pablo", "01/06/2026"],
        )
        assert r.exitoso is True
        assert r.message_id_meta is not None
        assert r.message_id_meta.startswith("wamid.fake.")
        # Registró el envío.
        assert len(sender.envios) == 1
        assert sender.envios[0].plantilla_name == "briefing_diario"

    async def test_modo_fallido(self) -> None:
        sender = FakeWhatsAppSender(modo_fallo="fallido", error="timeout")
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        assert r.exitoso is False
        assert r.rechazado is False
        assert r.error == "timeout"

    async def test_modo_rechazado(self) -> None:
        sender = FakeWhatsAppSender(
            modo_fallo="rechazado",
            error="opt_out",
            error_meta_code=131026,
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        assert r.exitoso is False
        assert r.rechazado is True
        assert r.error_meta_code == 131026

    async def test_envios_es_inmutable_desde_afuera(self) -> None:
        sender = FakeWhatsAppSender()
        await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        # `envios` devuelve una copia → mutar la lista NO afecta al sender.
        copia = sender.envios
        copia.clear()
        assert len(sender.envios) == 1


# ---------------------------------------------------------------------------
# WhatsAppCloudApiSender (HTTP mockeado)
# ---------------------------------------------------------------------------


def _make_mock_client(
    handler: httpx.MockTransport,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=handler,
        timeout=5.0,
        headers={"Content-Type": "application/json"},
    )


def _capture() -> tuple[list[httpx.Request], list[dict[str, Any]]]:
    requests: list[httpx.Request] = []
    bodies: list[dict[str, Any]] = []

    def _record(req: httpx.Request) -> None:
        requests.append(req)
        bodies.append(json.loads(req.content.decode("utf-8")))

    # Hack para acceder a closures de los tests.
    _record._requests = requests  # type: ignore[attr-defined]
    _record._bodies = bodies  # type: ignore[attr-defined]
    return requests, bodies


class TestWhatsAppCloudApiSender:
    async def test_payload_correcto_y_respuesta_exitosa(self) -> None:
        requests, bodies = _capture()

        def handler(req: httpx.Request) -> httpx.Response:
            requests.append(req)
            bodies.append(json.loads(req.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"messages": [{"id": "wamid.real.ABC"}]},
            )

        client = _make_mock_client(httpx.MockTransport(handler))
        sender = WhatsAppCloudApiSender(
            access_token="tok-test",
            phone_number_id="123456789",
            client=client,
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="briefing_diario",
            idioma="es_AR",
            body_params_ordered=["Pablo", "01/06/2026"],
        )
        await sender.aclose()

        assert r.exitoso is True
        assert r.message_id_meta == "wamid.real.ABC"
        # Verificamos la URL.
        assert len(requests) == 1
        assert (
            str(requests[0].url)
            == f"{META_GRAPH_API_BASE}/123456789/messages"
        )
        # Body correcto.
        body = bodies[0]
        assert body["messaging_product"] == "whatsapp"
        assert body["to"] == "5491155551234"  # SIN el +
        assert body["type"] == "template"
        assert body["template"]["name"] == "briefing_diario"
        assert body["template"]["language"]["code"] == "es_AR"
        params = body["template"]["components"][0]["parameters"]
        assert [p["text"] for p in params] == ["Pablo", "01/06/2026"]

    async def test_error_meta_opt_out_es_rechazo(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": 131026,
                        "message": "Recipient phone number is opted out.",
                        "type": "OAuthException",
                    },
                },
            )

        sender = WhatsAppCloudApiSender(
            access_token="tok",
            phone_number_id="123",
            client=_make_mock_client(httpx.MockTransport(handler)),
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        await sender.aclose()
        assert r.exitoso is False
        assert r.rechazado is True
        assert r.error_meta_code == 131026

    async def test_error_meta_plantilla_pausada_es_rechazo(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": {"code": 131056, "message": "Paused"}},
            )

        sender = WhatsAppCloudApiSender(
            access_token="tok",
            phone_number_id="123",
            client=_make_mock_client(httpx.MockTransport(handler)),
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        await sender.aclose()
        assert r.exitoso is False
        assert r.rechazado is True

    async def test_500_no_es_rechazo(self) -> None:
        """HTTP 5xx → fallido transitorio (no rechazado), el caller
        puede reintentar."""
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="upstream error")

        sender = WhatsAppCloudApiSender(
            access_token="tok",
            phone_number_id="123",
            client=_make_mock_client(httpx.MockTransport(handler)),
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        await sender.aclose()
        assert r.exitoso is False
        assert r.rechazado is False

    async def test_error_de_red_es_fallido(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated network failure")

        sender = WhatsAppCloudApiSender(
            access_token="tok",
            phone_number_id="123",
            client=_make_mock_client(httpx.MockTransport(handler)),
        )
        r = await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="x",
            idioma="es_AR",
            body_params_ordered=[],
        )
        await sender.aclose()
        assert r.exitoso is False
        assert r.rechazado is False
        assert "network_error" in (r.error or "")

    async def test_envio_sin_body_params(self) -> None:
        """Si la plantilla no tiene placeholders, components viaja
        como lista vacía."""
        captured_body: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(req.content.decode("utf-8")))
            return httpx.Response(
                200, json={"messages": [{"id": "wamid.x"}]},
            )

        sender = WhatsAppCloudApiSender(
            access_token="tok",
            phone_number_id="123",
            client=_make_mock_client(httpx.MockTransport(handler)),
        )
        await sender.enviar(
            telefono_e164="+5491155551234",
            plantilla_name="opt_in_solicitud",
            idioma="es_AR",
            body_params_ordered=[],
        )
        await sender.aclose()
        assert captured_body["template"]["components"] == []
