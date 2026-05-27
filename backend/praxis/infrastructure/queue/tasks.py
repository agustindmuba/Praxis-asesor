"""Tareas Celery del backend Praxis Asesor.

Tareas reales (scraping, alertas, ingestas) se irán agregando módulo por módulo.
Este archivo arranca con un `ping` para verificar el pipeline end-to-end.
"""

from __future__ import annotations

from praxis.infrastructure.queue.celery_app import celery_app


@celery_app.task(name="praxis.ping")  # type: ignore[untyped-decorator]  # Celery sin tipado preciso
def ping() -> str:
    """Tarea de prueba: encolar y verificar que un worker la consume."""
    return "pong"
