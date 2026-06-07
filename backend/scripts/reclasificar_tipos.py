"""Re-clasifica el campo `tipo` de todos los expedientes existentes
aplicando `inferir_tipo_desde_titulo` (feat-43.1.3).

Necesario porque el parser de feat-1 era muy permisivo y dejó 435/443
expedientes como `proyecto_ley` aunque la mayoría sean declaraciones o
resoluciones.

Idempotente: se puede correr múltiples veces. Reporta el cambio neto
por tipo al final.

Uso:
    uv run python -m scripts.reclasificar_tipos
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from sqlalchemy import select

from praxis.domain.inferencia_tipo import inferir_tipo_desde_titulo
from praxis.domain.value_objects import Camara, OrigenExpediente
from praxis.infrastructure.db.engine import SessionLocal
from praxis.infrastructure.persistence.models import ExpedienteOrm

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("reclasificar_tipos")


async def main() -> None:
    cambios: Counter[tuple[str, str]] = Counter()
    total = 0

    async with SessionLocal() as session:
        result = await session.execute(select(ExpedienteOrm))
        expedientes = list(result.scalars())
        total = len(expedientes)
        log.info("Procesando %d expedientes...", total)

        for exp in expedientes:
            tipo_actual = exp.tipo
            try:
                origen = OrigenExpediente(exp.origen) if exp.origen else None
            except ValueError:
                origen = None
            try:
                camara = Camara(exp.camara) if exp.camara else None
            except ValueError:
                camara = None

            tipo_nuevo = inferir_tipo_desde_titulo(
                exp.titulo or "",
                sumario=exp.sumario or "",
                origen=origen,
                camara=camara,
            )

            if tipo_nuevo.value != tipo_actual:
                cambios[(tipo_actual, tipo_nuevo.value)] += 1
                exp.tipo = tipo_nuevo.value

        await session.commit()

    log.info("\n=== Resumen ===")
    log.info("Total expedientes: %d", total)
    log.info("Sin cambio:       %d", total - sum(cambios.values()))
    log.info("Cambiados:        %d", sum(cambios.values()))
    log.info("\n=== Cambios por tipo ===")
    for (antes, despues), n in sorted(cambios.items(), key=lambda x: -x[1]):
        log.info("  %s → %s: %d", antes, despues, n)


if __name__ == "__main__":
    asyncio.run(main())
