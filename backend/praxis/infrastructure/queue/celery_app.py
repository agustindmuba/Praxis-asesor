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
        "praxis.infrastructure.queue.tasks_rag",
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
    # Default 900s/840s = 15min hard / 14min soft. Es el techo razonable
    # para una task individual; ajuste de 300s original (feat-10) que se
    # quedó corto cuando aparecieron tasks que scrapean N fuentes con
    # LLM por artículo (feat-40.5.B) y batch de briefings WhatsApp con
    # N despachos (feat-41.4). Per-task overrides via decorator
    # `@celery_app.task(time_limit=..., soft_time_limit=...)`.
    task_time_limit=900,
    task_soft_time_limit=840,
    # Acknowledge late: la tarea se considera consumida cuando termina,
    # no cuando se toma del broker. Si el worker muere mid-task, la tarea
    # vuelve a la cola (visible al siguiente worker).
    task_acks_late=True,
    # Prefetch bajo: cada worker pide solo lo que está procesando.
    # Evita acumular tareas en workers que después mueren.
    worker_prefetch_multiplier=1,
    # Beat schedule (UTC). Horarios pensados para Buenos Aires
    # (UTC-3). El asesor recibe el briefing diario a las 8:00 ART;
    # el pipeline de BO + clasificación corre antes para que llegue
    # con todo procesado.
    beat_schedule={
        "bo-ingestar-diario": {
            "task": "praxis.bo.ingestar_diario",
            # 08:30 UTC = 05:30 ART
            "schedule": crontab(hour="8", minute="30"),
        },
        "bo-clasificar-pendientes": {
            "task": "praxis.bo.clasificar_pendientes",
            # 09:00 UTC = 06:00 ART
            "schedule": crontab(hour="9", minute="0"),
        },
        "bo-evaluar-accionables-por-despacho": {
            "task": "praxis.bo.evaluar_accionables_por_despacho",
            # 10:00 UTC = 07:00 ART
            "schedule": crontab(hour="10", minute="0"),
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
        # 11:00 UTC = 08:00 ART. El BO ya está ingestado + clasificado
        # + accionable evaluado para cuando dispara.
        "whatsapp-enviar-briefings-diarios": {
            "task": "praxis.whatsapp.enviar_briefings_diarios",
            "schedule": crontab(hour="11", minute="0"),
        },
    },
)
