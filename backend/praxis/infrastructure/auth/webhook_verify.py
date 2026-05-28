"""Verificación de firmas de webhooks Clerk (vía Svix).

Wrap fino sobre `svix.webhooks.Webhook` para que el router no tenga que
saber del SDK directamente. Si en el futuro reemplazamos Svix por otra cosa,
solo cambiamos este archivo.
"""

from __future__ import annotations

from typing import Any

from svix.webhooks import Webhook, WebhookVerificationError


class WebhookSignatureError(Exception):
    """Falla de verificación de firma del webhook."""


class SvixWebhookVerifier:
    """Verifica firmas de Svix usando el secret del endpoint.

    Args:
        secret: el endpoint signing secret (formato `whsec_...` que da Clerk).
    """

    def __init__(self, secret: str) -> None:
        self._webhook = Webhook(secret)

    def verify(self, *, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        """Verifica la firma y devuelve el body parseado como dict.

        Args:
            raw_body: el body crudo de la request (bytes). NO el JSON parseado
                — Svix verifica sobre los bytes exactos.
            headers: headers con `svix-id`, `svix-timestamp`, `svix-signature`.
                Los nombres de headers son case-insensitive en HTTP; el SDK los
                busca lowercased.

        Returns:
            El body parseado a dict.

        Raises:
            WebhookSignatureError: si la firma no verifica o falta algún header.
        """
        # Svix requiere headers con prefijo `svix-`. Normalizamos a lowercase
        # para evitar sorpresas (HTTP es case-insensitive).
        normalized = {k.lower(): v for k, v in headers.items()}
        try:
            payload: Any = self._webhook.verify(raw_body, normalized)
        except WebhookVerificationError as exc:
            raise WebhookSignatureError(str(exc)) from exc
        # Svix devuelve el JSON parseado.
        if not isinstance(payload, dict):
            raise WebhookSignatureError("payload del webhook no es un objeto JSON")
        return payload
