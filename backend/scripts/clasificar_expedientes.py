"""Clasifica tematicamente los expedientes ya persistidos.

Para feat/27. Itera la tabla expediente, llama al caso de uso
`ClasificarExpedienteTematicamente` con el `FakeLlmProvider` (sin API,
gratis). Idempotente: si el expediente ya tiene clasificación cacheada,
se saltea.

Uso:
    uv run python -m scripts.clasificar_expedientes
    uv run python -m scripts.clasificar_expedientes --batch 100 --max 50
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.application.use_cases import ClasificarExpedienteTematicamente
from praxis.config import get_settings
from praxis.infrastructure.llm.fake import FakeLlmProvider
from praxis.infrastructure.persistence.models import ExpedienteOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteAreaTematicaRepository,
    SqlAlchemyExpedienteRepository,
)


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    llm = FakeLlmProvider()

    print(f"[clasificar] DB: {settings.database_url}")
    print(f"[clasificar] Modelo: {llm.nombre_modelo}")
    print(f"[clasificar] Batch: {args.batch}; Max: {args.max or 'sin límite'}")
    print()

    nuevos = 0
    cacheados = 0
    contador_por_area: dict[str, int] = {}
    started_at = time.monotonic()

    try:
        offset = 0
        while True:
            async with sm() as session:
                # Sólo los UUIDs (no cargar relaciones pesadas).
                stmt = (
                    select(ExpedienteOrm.id)
                    .order_by(ExpedienteOrm.id)
                    .limit(args.batch)
                    .offset(offset)
                )
                result = await session.execute(stmt)
                ids = [row[0] for row in result]
                if not ids:
                    break

            for exp_id in ids:
                async with sm() as session:
                    expedientes = SqlAlchemyExpedienteRepository(session)
                    clasificaciones = SqlAlchemyExpedienteAreaTematicaRepository(session)
                    uc = ClasificarExpedienteTematicamente(
                        expedientes=expedientes,
                        clasificaciones=clasificaciones,
                        llm=llm,
                    )
                    # ¿Estaba cacheado?
                    pre = await clasificaciones.buscar_por_expediente(exp_id)
                    result_clf = await uc.execute(exp_id)
                    await session.commit()

                    contador_por_area[result_clf.area.value] = (
                        contador_por_area.get(result_clf.area.value, 0) + 1
                    )
                    if pre is None:
                        nuevos += 1
                    else:
                        cacheados += 1

                if args.max is not None and (nuevos + cacheados) >= args.max:
                    break

            offset += args.batch
            elapsed = time.monotonic() - started_at
            total = nuevos + cacheados
            rate = total / elapsed if elapsed > 0 else 0
            print(
                f"  - batch offset={offset} | acumulado: {total} "
                f"(+{nuevos} nuevos, ={cacheados} cacheados | {rate:.0f}/s)"
            )

            if args.max is not None and (nuevos + cacheados) >= args.max:
                break
    except KeyboardInterrupt:
        print()
        print("[clasificar] Interrumpido.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Total procesados: {nuevos + cacheados}")
    print(f"  Nuevos:           {nuevos}")
    print(f"  Cacheados:        {cacheados}")
    print(f"  Tiempo total:     {elapsed:.1f}s")
    print()
    print("  Distribución por área temática:")
    for area, n in sorted(contador_por_area.items(), key=lambda x: -x[1]):
        print(f"    {area:25s} {n:4d}")
    print("=" * 60)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Clasifica tematicamente los expedientes en DB"
    )
    p.add_argument(
        "--batch",
        type=int,
        default=200,
        help="Cantidad de expedientes por batch (default 200)",
    )
    p.add_argument(
        "--max",
        type=int,
        default=None,
        help="Cantidad máxima de expedientes a procesar",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
