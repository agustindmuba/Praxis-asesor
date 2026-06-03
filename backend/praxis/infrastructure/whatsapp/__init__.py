"""Implementaciones del puerto `WhatsAppSender` (spec 17 / feat-41.2).

- `FakeWhatsAppSender`: sin red, devuelve message_id sintético. Para
  dev local + tests integración del caso de uso de feat-41.4.
- `WhatsAppCloudApiSender`: cliente HTTP real contra Meta WhatsApp
  Cloud API. Selector automático según `Settings.meta_whatsapp_token`
  está en `praxis.api.deps`.
"""

from praxis.infrastructure.whatsapp.cloud_api import (
    META_GRAPH_API_BASE,
    WhatsAppCloudApiSender,
)
from praxis.infrastructure.whatsapp.fake import FakeWhatsAppSender

__all__ = [
    "META_GRAPH_API_BASE",
    "FakeWhatsAppSender",
    "WhatsAppCloudApiSender",
]
