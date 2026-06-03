"""`WhatsAppCloudApiSender` — cliente HTTP contra Meta WhatsApp Cloud API.

Endpoint: `POST {base}/{phone_number_id}/messages` con
`Authorization: Bearer {access_token}`.

Body (plantilla):
```
{
  "messaging_product": "whatsapp",
  "to": "+5491155551234",
  "type": "template",
  "template": {
    "name": "briefing_diario",
    "language": {"code": "es_AR"},
    "components": [
      {"type": "body", "parameters": [
        {"type": "text", "text": "Pablo"},
        {"type": "text", "text": "01/06/2026"}
      ]}
    ]
  }
}
```

Respuesta exitosa (HTTP 200):
```
{"messages": [{"id": "wamid.HBgM..."}]}
```

Respuesta de error (HTTP 4xx/5xx):
```
{"error": {"code": 131056, "message": "...", "type": "..."}}
```

Tabla rápida de codes que clasificamos como `rechazado=True` (errores
de negocio, no transitorios):

- 131000: generic OK-formed but rejected
- 131005: access_token revoked / sin permiso
- 131008: parámetros faltantes
- 131026: el receptor no puede recibir (opt-out, número inválido)
- 131047: plantilla rechazada / no aprobada
- 131056: plantilla pausada por calidad
- 132000-132999: errores de plantilla en general

Cualquier otro código + errores de red → `rechazado=False`
(transitorio, el caller puede reintentar).

Ver https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from praxis.application.ports import ResultadoEnvioWhatsApp, WhatsAppSender

log = logging.getLogger(__name__)

META_GRAPH_API_BASE = "https://graph.facebook.com/v18.0"
TIMEOUT_SECONDS = 30.0

# Códigos Meta que tratamos como "rechazado" (no reintentables).
_RECHAZO_CODES: frozenset[int] = frozenset({
    131000, 131005, 131008, 131026, 131047, 131056,
})


class WhatsAppCloudApiSender(WhatsAppSender):
    """Cliente HTTP real. Se inyecta vía `praxis.api.deps.WhatsAppSenderDep`
    cuando `Settings.meta_whatsapp_token` está seteado."""

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = META_GRAPH_API_BASE,
    ) -> None:
        self._token = access_token
        self._phone_id = phone_number_id
        self._base = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )

    async def enviar(
        self,
        *,
        telefono_e164: str,
        plantilla_name: str,
        idioma: str,
        body_params_ordered: list[str],
    ) -> ResultadoEnvioWhatsApp:
        url = f"{self._base}/{self._phone_id}/messages"
        payload = self._construir_payload(
            telefono_e164=telefono_e164,
            plantilla_name=plantilla_name,
            idioma=idioma,
            body_params_ordered=body_params_ordered,
        )

        try:
            resp = await self._client.post(url, json=payload)
        except httpx.RequestError as exc:
            log.warning(
                "WhatsAppCloudApi: error de red al mandar %s a %s: %s",
                plantilla_name, telefono_e164, exc,
            )
            return ResultadoEnvioWhatsApp(
                exitoso=False,
                error=f"network_error: {exc}",
                rechazado=False,
            )

        return self._parsear_respuesta(resp, plantilla_name, telefono_e164)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _construir_payload(
        self,
        *,
        telefono_e164: str,
        plantilla_name: str,
        idioma: str,
        body_params_ordered: list[str],
    ) -> dict[str, Any]:
        parameters = [
            {"type": "text", "text": valor}
            for valor in body_params_ordered
        ]
        return {
            "messaging_product": "whatsapp",
            # Meta requiere el número SIN el `+` inicial.
            "to": telefono_e164.lstrip("+"),
            "type": "template",
            "template": {
                "name": plantilla_name,
                "language": {"code": idioma},
                "components": [
                    {"type": "body", "parameters": parameters},
                ] if parameters else [],
            },
        }

    def _parsear_respuesta(
        self,
        resp: httpx.Response,
        plantilla_name: str,
        telefono_e164: str,
    ) -> ResultadoEnvioWhatsApp:
        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code == 200 and "messages" in data:
            msgs = data["messages"]
            if msgs and isinstance(msgs, list) and "id" in msgs[0]:
                return ResultadoEnvioWhatsApp(
                    exitoso=True,
                    message_id_meta=str(msgs[0]["id"]),
                )

        # Error: extraer code/message del body.
        error_obj = data.get("error") if isinstance(data, dict) else None
        if isinstance(error_obj, dict):
            code_raw = error_obj.get("code")
            try:
                code = int(code_raw) if code_raw is not None else None
            except (TypeError, ValueError):
                code = None
            message = str(error_obj.get("message", "(sin mensaje)"))
        else:
            code = None
            message = f"HTTP {resp.status_code}: {resp.text[:200]}"

        rechazado = code in _RECHAZO_CODES if code is not None else False
        log.warning(
            "WhatsAppCloudApi: %s a %s → HTTP %d code=%s msg=%s",
            plantilla_name, telefono_e164, resp.status_code, code, message,
        )
        return ResultadoEnvioWhatsApp(
            exitoso=False,
            error=message,
            rechazado=rechazado,
            error_meta_code=code,
        )
