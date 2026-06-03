"""Configuración de Celery.

La app se levanta con:
    uv run celery -A praxis.infrastructure.queue.celery_app worker --loglevel=info

Y, en otro proceso, el scheduler (Celery Beat) para tareas periódicas:
    uv run celery -A praxis.infrastructure.queue.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from praxis.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "praxis",
    broker=str(_settings.redis_url),
    backend=str(_settings.redis_url),
    # Autodiscover de tareas: módulos cuyo path coincida con esta lista.
    include=[
        "praxis.infrastructure.queue.tasks",
        "praxis.infrastructure.queue.tasks_bo",
        "praxis.infrastructure.queue.tasks_noticias",
        "praxis.infrastructure.queue.tasks_whatsapp",
    ],
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
    # Beat schedule (UTC). Horarios pensados para Buenos Aires
    # (UTC-3): 05:00 ART = 08:00 UTC, 05:30 ART = 08:30 UTC,
    # 06:00 ART = 09:00 UTC. Ver spec 15 §"Pipeline diario".
    beat_schedule={
        "bo-ingestar-diario": {
            "task": "praxis.bo.ingestar_diario",
            # 08:00 UTC = 05:00 ART
            "schedule": crontab(hour="8", minute="0"),
        },
        "bo-clasificar-pendientes": {
            "task": "praxis.bo.clasificar_pendientes",
            # 08:30 UTC = 05:30 ART
            "schedule": crontab(hour="8", minute="30"),
        },
        "bo-evaluar-accionables-por-despacho": {
            "task": "praxis.bo.evaluar_accionables_por_despacho",
            # 09:00 UTC = 06:00 ART
            "schedule": crontab(hour="9", minute="0"),
        },
        # Noticias (spec 16, feat-40.5.D). Polling continuo
        # durante el día — los medios actualizan a lo largo del día.
        "noticias-procesar-fuentes": {
            "task": "praxis.noticias.procesar_fuentes",
            # Cada 15 min. Si se necesita más fino para alertas
            # urgentes, bajar a 5 min con cuidado del rate limit
            # del scraping (ADR 0007).
            "schedule": crontab(minute="*/15"),
        },
        "noticias-enviar-alertas-pendientes": {
            "task": "praxis.noticias.enviar_alertas_pendientes",
            # Cada 10 min. Anti-flood interno garantiza ≤ 1 alerta
            # agrupada por despacho por hora (ADR 0009).
            "schedule": crontab(minute="*/10"),
        },
        # WhatsApp briefing diario (spec 17, feat-41.4).
        # Default 07:00 ART = 10:00 UTC. Si el polling de noticias
        # corre a las 15 min de la hora y BO se evalúa a 09:00 UTC,
        # cuando esta task corre ya está todo listo para resumir.
        "whatsapp-enviar-briefings-diarios": {
            "task": "praxis.whatsapp.enviar_briefings_diarios",
            "schedule": crontab(hour="10", minute="0"),
        },
    },
)
