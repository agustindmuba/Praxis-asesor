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
        "praxis.infrastructure.queue.tasks_hcdn",
        "praxis.infrastructure.queue.tasks_comisiones",
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
    # (UTC-3).
    #
    # IMPORTANTE — feat-49.fix-bo-schedule:
    # El Boletín Oficial nacional publica su edición diaria
    # ALREDEDOR de las 8 hs ART. Antes de esa hora la edición del
    # día NO existe (queda la del día anterior). Por eso el
    # pipeline de BO arranca a partir de las 8 hs ART y NO antes —
    # si scrapeaba a las 5:30 traía la edición vieja o vacía.
    #
    # feat-64 — PIPELINE EXPRESS. El asesor no puede esperar hasta
    # las 9:30 para su briefing: a las 9 ya está en reunión. Bajamos
    # los tiempos entre etapas a 5-10 min. TODO al unísono a las 8:20.
    #   08:00 ART → ingestar la edición del día recién publicada (~2 min)
    #   08:05 ART → clasificar las normas nuevas con LLM (~5 min)
    #   08:15 ART → evaluar accionabilidad por despacho (~2 min)
    #   08:20 ART → enviar briefing diario por WhatsApp
    #               (comisiones ya enriquecidas desde las 07:00 ART)
    beat_schedule={
        "bo-ingestar-diario": {
            "task": "praxis.bo.ingestar_diario",
            # 11:00 UTC = 08:00 ART
            "schedule": crontab(hour="11", minute="0"),
        },
        "bo-clasificar-pendientes": {
            "task": "praxis.bo.clasificar_pendientes",
            # 11:05 UTC = 08:05 ART
            "schedule": crontab(hour="11", minute="5"),
        },
        "bo-evaluar-accionables-por-despacho": {
            "task": "praxis.bo.evaluar_accionables_por_despacho",
            # 11:15 UTC = 08:15 ART
            "schedule": crontab(hour="11", minute="15"),
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
        # feat-64: 11:20 UTC = 08:20 ART. Corre DESPUÉS del pipeline BO
        # express (ingestar 08:00 → clasificar 08:05 → evaluar 08:15),
        # por eso a las 08:20 ya tiene TODO el material fresco del día.
        # El asesor recibe todo antes de arrancar su primera reunión.
        "whatsapp-enviar-briefings-diarios": {
            "task": "praxis.whatsapp.enviar_briefings_diarios",
            "schedule": crontab(hour="11", minute="20"),
        },
        # HCDN: detectar OD nuevo del Plan de Labor (feat-45.4).
        # Corre cada 1 hora durante horario de sesiones argentino:
        # martes y jueves entre 12:00 y 22:00 UTC (9-19 ART).
        # Fuera de ese rango el portal HCDN no actualiza temarios.
        "hcdn-detectar-od": {
            "task": "praxis.hcdn.detectar_od",
            "schedule": crontab(
                minute="0",
                hour="12-22",
                day_of_week="tue,thu",
            ),
        },
        # WhatsApp aviso "mañana hay sesión" (feat-45.5).
        # 21:00 UTC = 18:00 ART, día anterior a la sesión. Para cada
        # OD con fecha_sesion=mañana, manda WhatsApp con link al briefing.
        "whatsapp-aviso-proxima-sesion": {
            "task": "praxis.whatsapp.enviar_avisos_proxima_sesion",
            "schedule": crontab(hour="21", minute="0"),
        },
        # Comisiones HCDN (feat-61). Scrape diario madrugada + enriquecer
        # antes del briefing 08:20 ART (feat-64).
        # 07:00 UTC = 04:00 ART → scrape.
        # 10:00 UTC = 07:00 ART → enriquecer.
        "comisiones-scrape-diario": {
            "task": "praxis.comisiones.scrape_diario",
            "schedule": crontab(hour="7", minute="0"),
        },
        "comisiones-enriquecer-pendientes": {
            "task": "praxis.comisiones.enriquecer_pendientes",
            "schedule": crontab(hour="10", minute="0"),
        },
    },
)
