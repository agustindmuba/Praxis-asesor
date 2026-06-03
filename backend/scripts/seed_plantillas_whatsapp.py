"""Seed las plantillas WhatsApp v1 en la DB local.

Uso:
    .venv/Scripts/python.exe scripts/seed_plantillas_whatsapp.py
    .venv/Scripts/python.exe scripts/seed_plantillas_whatsapp.py \\
        --mark-aprobada briefing_diario

El primer modo upsertea TODAS las plantillas del catálogo v1 con
estado=PENDIENTE_APROBACION. El segundo flag marca UNA plantilla como
APROBADA (lo corre el operador después de que Meta apruebe).

Las plantillas también necesitan registrarse manualmente en Meta
WhatsApp Manager con el mismo `contenido_referencia`. Ver
`docs/runbooks/whatsapp-plantillas.md` (a redactar).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.domain import EstadoMetaPlantilla, PlantillaWhatsApp
from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyPlantillaWhatsAppRepository,
)
from praxis.infrastructure.whatsapp.plantillas_v1 import PLANTILLAS_V1

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("seed-plantillas-whatsapp")


async def _seed_todas() -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        repo = SqlAlchemyPlantillaWhatsAppRepository(session)
        for p in PLANTILLAS_V1:
            actual = await repo.buscar_por_name(p.name)
            if actual is None:
                await repo.upsert(p)
                log.info("Nueva: %s (idioma=%s, categoría=%s)",
                         p.name, p.idioma, p.categoria.value)
            else:
                log.info("Existe: %s (estado=%s)",
                         p.name, actual.estado_meta.value)
        await session.commit()


async def _marcar_aprobada(name: str) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        repo = SqlAlchemyPlantillaWhatsAppRepository(session)
        actual = await repo.buscar_por_name(name)
        if actual is None:
            log.error("Plantilla %s no existe en la DB. Seedear primero.", name)
            return
        actualizada = PlantillaWhatsApp(
            name=actual.name,
            categoria=actual.categoria,
            body_params=list(actual.body_params),
            contenido_referencia=actual.contenido_referencia,
            idioma=actual.idioma,
            estado_meta=EstadoMetaPlantilla.APROBADA,
            aprobada_en=datetime.now(UTC),
        )
        await repo.upsert(actualizada)
        await session.commit()
        log.info("Marcada APROBADA: %s", name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mark-aprobada",
        type=str,
        default=None,
        help="Marca esa plantilla como APROBADA en lugar de seedear todas.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.mark_aprobada:
        asyncio.run(_marcar_aprobada(args.mark_aprobada))
    else:
        asyncio.run(_seed_todas())


if __name__ == "__main__":
    main()
