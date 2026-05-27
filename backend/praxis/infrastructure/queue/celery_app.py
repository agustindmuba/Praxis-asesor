"""Configuración de Celery.

La app se levanta con:
    uv run celery -A praxis.infrastructure.queue.celery_app worker --loglevel=info

Y, en otro proceso, el scheduler (Celery Beat) para tareas periódicas:
    uv run celery -A praxis.infrastructure.queue.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from praxis.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "praxis",
    broker=str(_settings.redis_url),
    backend=str(_settings.redis_url),
    # Autodiscover de tareas: módulos cuyo path coincida con esta lista.
    include=["praxis.infrastructure.queue.tasks"],
)

# Configuración general.
celery_app.conf.update(
    # Serialización: JSON (no pickle, por seguridad).
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone: UTC siempre; las conversiones a hora local viven en la UI.
    timezone="UTC",
    enable_utc=True,
    # Tracking de estado.
    task_track_started=True,
    # Límites duros y suaves para evitar workers atascados.
    task_time_limit=300,  # 5 min: aborta el proceso.
    task_soft_time_limit=240,  # 4 min: dispara SoftTimeLimitExceeded para cleanup.
    # Acknowledge late: la tarea se considera consumida cuando termina,
    # no cuando se toma del broker. Si el worker muere mid-task, la tarea
    # vuelve a la cola (visible al siguiente worker).
    task_acks_late=True,
    # Prefetch bajo: cada worker pide solo lo que está procesando.
    # Evita acumular tareas en workers que después mueren.
    worker_prefetch_multiplier=1,
)
