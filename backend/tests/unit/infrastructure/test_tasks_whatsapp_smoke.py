"""Smoke test minimal de la Celery task de WhatsApp (feat-41.4).

NO ejecuta la task — solo verifica que:

- La task está registrada en `celery_app.tasks`.
- Está en el `beat_schedule` con crontab.
- `_construir_sender` devuelve Fake si no hay token, real si lo hay.
"""

from __future__ import annotations

import pytest
from celery.schedules import crontab

from praxis.config import get_settings
from praxis.infrastructure.queue.celery_app import celery_app
from praxis.infrastructure.queue.tasks_whatsapp import _construir_sender
from praxis.infrastructure.whatsapp import (
    FakeWhatsAppSender,
    WhatsAppCloudApiSender,
)

pytestmark = pytest.mark.unit


def test_task_registrada() -> None:
    assert (
        "praxis.whatsapp.enviar_briefings_diarios" in celery_app.tasks
    )


def test_beat_schedule_incluye_briefing() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "whatsapp-enviar-briefings-diarios" in schedule
    s = schedule["whatsapp-enviar-briefings-diarios"]
    assert isinstance(s["schedule"], crontab)
    assert s["task"] == "praxis.whatsapp.enviar_briefings_diarios"


def test_construir_sender_sin_token_devuelve_fake() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.meta_whatsapp_token = None
    settings.meta_whatsapp_phone_number_id = None
    sender = _construir_sender()
    assert isinstance(sender, FakeWhatsAppSender)


def test_construir_sender_con_token_devuelve_real() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.meta_whatsapp_token = "tok"
    settings.meta_whatsapp_phone_number_id = "phone123"
    try:
        sender = _construir_sender()
        assert isinstance(sender, WhatsAppCloudApiSender)
    finally:
        settings.meta_whatsapp_token = None
        settings.meta_whatsapp_phone_number_id = None
