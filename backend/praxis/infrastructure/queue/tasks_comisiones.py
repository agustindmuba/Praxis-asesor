"""Celery tasks de comisiones HCDN (feat-61).

- `praxis.comisiones.scrape_diario`: refresca el catálogo + integrantes +
  agenda próximas 120 días desde HCDN.
- `praxis.comisiones.enriquecer_pendientes`: analiza con LLM las
  reuniones futuras sin `enriquecida_en` (idempotente).

Ambas son seguras de correr concurrentemente: el scraper es idempotente
por (camara, slug); el enriquecimiento por reunion_id.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyComisionHcdnRepository,
)
from praxis.infrastructure.queue._async_runtime import run_task_async
from praxis.infrastructure.queue.celery_app import celery_app
from praxis.infrastructure.scrapers.hcdn.comisiones import (
    ComisionesHcdnScraper,
)

log = logging.getLogger(__name__)


@celery_app.task(name="praxis.comisiones.scrape_diario")  # type: ignore[untyped-decorator]
def scrape_diario_task() -> dict[str, int]:
    """Refresca catálogo + integrantes + agenda. Idempotente."""
    return run_task_async(_scrape_diario_async())


async def _scrape_diario_async() -> dict[str, int]:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    hoy = date.today()
    hasta = hoy + timedelta(days=120)
    total_integrantes = 0
    total_reuniones = 0
    async with ComisionesHcdnScraper() as scraper:
        comisiones = await scraper.listar_permanentes()
        log.info("comisiones.scrape: %d permanentes", len(comisiones))
        for c in comisiones:
            async with sessionmaker() as session:
                repo = SqlAlchemyComisionHcdnRepository(session)
                persistida = await repo.upsert(c)
                assert persistida.id is not None
                integrantes = await scraper.listar_integrantes(c.slug)
                if integrantes:
                    await repo.reemplazar_integrantes(
                        comision_id=persistida.id, integrantes=integrantes,
                    )
                    total_integrantes += len(integrantes)
                reuniones = await scraper.listar_reuniones(
                    c.slug, desde=hoy, hasta=hasta,
                )
                if reuniones:
                    await repo.upsert_reuniones(
                        comision_id=persistida.id, reuniones=reuniones,
                    )
                    total_reuniones += len(reuniones)
                await session.commit()
    log.info(
        "comisiones.scrape OK: %d comisiones, %d integrantes, %d reuniones",
        len(comisiones), total_integrantes, total_reuniones,
    )
    return {
        "comisiones": len(comisiones),
        "integrantes": total_integrantes,
        "reuniones": total_reuniones,
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    name="praxis.comisiones.enriquecer_pendientes",
    time_limit=900,
    soft_time_limit=840,
)
def enriquecer_pendientes_task() -> dict[str, int]:
    """Llama al LLM para reuniones futuras sin enriquecer. Idempotente."""
    return run_task_async(_enriquecer_pendientes_async())


async def _enriquecer_pendientes_async() -> dict[str, int]:
    # Importa acá para que el reload del Celery worker no levante el LLM
    # de entrada (Anthropic instancia un cliente HTTP en el __init__).
    from scripts.enriquecer_reuniones_pendientes import (
        enriquecer_reuniones_pendientes,
    )
    enriquecidas, fallidas = await enriquecer_reuniones_pendientes(dias=30)
    return {"enriquecidas": enriquecidas, "fallidas": fallidas}
