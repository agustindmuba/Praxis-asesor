"""Seed inicial de comisiones HCDN (feat-61.5).

Corre el scraper contra el portal HCDN una vez y persiste:
- Las 46 comisiones permanentes (upsert por slug).
- Para cada comisión: integrantes (DELETE+INSERT) + reuniones futuras
  (upsert por fecha+título).

Pensado para correrse 1 vez al sembrar el sistema, después Celery beat
lo mantiene fresco (1 corrida nocturna).

Uso:
    PYTHONUTF8=1 uv run python -m scripts.seed_comisiones_hcdn
    PYTHONUTF8=1 uv run python -m scripts.seed_comisiones_hcdn --max 5
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyComisionHcdnRepository,
)
from praxis.infrastructure.scrapers.hcdn.comisiones import (
    ComisionesHcdnScraper,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("seed-comisiones-hcdn")


async def _seed(*, max_comisiones: int | None = None) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    hoy = date.today()
    hasta = hoy + timedelta(days=120)

    async with ComisionesHcdnScraper() as scraper:
        comisiones = await scraper.listar_permanentes()
        log.info("Indice: %d comisiones permanentes", len(comisiones))

        if max_comisiones is not None:
            comisiones = comisiones[:max_comisiones]
            log.info("Cap aplicado: procesando %d", len(comisiones))

        total_integrantes = 0
        total_reuniones = 0

        for i, c in enumerate(comisiones, start=1):
            log.info("[%d/%d] %s (%s)", i, len(comisiones), c.slug, c.nombre)
            async with sessionmaker() as session:
                repo = SqlAlchemyComisionHcdnRepository(session)
                persistida = await repo.upsert(c)
                assert persistida.id is not None

                integrantes = await scraper.listar_integrantes(c.slug)
                if integrantes:
                    await repo.reemplazar_integrantes(
                        comision_id=persistida.id,
                        integrantes=integrantes,
                    )
                    total_integrantes += len(integrantes)

                reuniones = await scraper.listar_reuniones(
                    c.slug, desde=hoy, hasta=hasta,
                )
                if reuniones:
                    await repo.upsert_reuniones(
                        comision_id=persistida.id,
                        reuniones=reuniones,
                    )
                    total_reuniones += len(reuniones)

                await session.commit()

        log.info(
            "Listo. Comisiones: %d, integrantes: %d, reuniones: %d",
            len(comisiones), total_integrantes, total_reuniones,
        )

    # Enriquecimiento automático de reuniones pendientes (feat-61.4.B).
    # Importa acá para evitar el cycle con el script en cli mode.
    if total_reuniones > 0:
        from scripts.enriquecer_reuniones_pendientes import (
            enriquecer_reuniones_pendientes,
        )
        log.info("Iniciando enriquecimiento automático…")
        enriquecidas, fallidas = await enriquecer_reuniones_pendientes(
            dias=120,
        )
        log.info(
            "Enriquecimiento: %d ok, %d fallidas",
            enriquecidas, fallidas,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Cap de comisiones a procesar (default: todas).",
    )
    args = parser.parse_args()
    asyncio.run(_seed(max_comisiones=args.max))


if __name__ == "__main__":
    main()
