"""Tasks Celery del pipeline HCDN — detección automática del Orden del Día
(feat-45.4).

- `praxis.hcdn.detectar_od` (cron cada 1h durante horario de sesiones):
  llama a `DetectarNuevoOd` que polea el portal del Plan de Labor,
  detecta sesiones nuevas e importa el OD con sus expedientes.

La task es idempotente: si no hay sesiones nuevas, no hace nada. Si
hay, las importa hasta `max_nuevas` por corrida (default 3).

Sync wrapper porque Celery está pensado sync; usamos `asyncio.run()`
para llamar al pipeline async.
"""

from __future__ import annotations

import logging

from praxis.infrastructure.queue.celery_app import celery_app
from praxis.infrastructure.queue._async_runtime import run_task_async

log = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="praxis.hcdn.detectar_od",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=600,
)
def detectar_od_task(self, max_nuevas: int = 3) -> dict:  # type: ignore[no-untyped-def]
    """Llama a DetectarNuevoOd y devuelve un dict con métricas.

    `max_nuevas`: cuántas sesiones nuevas procesar por corrida. Defaut
    bajo (3) porque cada item dispara llamadas a HCDN y queremos
    distribuir la carga si el portal publica un lote grande de OD.
    """

    async def _correr() -> dict:
        from praxis.application.use_cases.detectar_nuevo_od import (
            DetectarNuevoOd,
        )
        from praxis.infrastructure.db.engine import SessionLocal
        from praxis.infrastructure.persistence.repositories import (
            SqlAlchemyOrdenDelDiaRepository,
        )

        async with SessionLocal() as session:
            uc = DetectarNuevoOd(
                session=session,
                ordenes_repo=SqlAlchemyOrdenDelDiaRepository(session),
            )
            res = await uc.ejecutar(max_nuevas=max_nuevas)
            return {
                "sesiones_disponibles": res.sesiones_disponibles_total,
                "sesiones_nuevas": res.sesiones_nuevas,
                "ods_creados": res.ods_creados,
                "expedientes_resueltos": res.expedientes_resueltos_total,
                "expedientes_no_encontrados": res.expedientes_no_encontrados_total,
            }

    log.info("praxis.hcdn.detectar_od start max_nuevas=%d", max_nuevas)
    out = run_task_async(_correr())
    log.info("praxis.hcdn.detectar_od done %s", out)
    return out
