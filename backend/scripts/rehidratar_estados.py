"""Rehidrata `estado` y campos de caducidad de los expedientes ya persistidos.

Hasta feat/25, el scraper HCDN dejaba `estado=DESCONOCIDO` en todos los
expedientes que persistía. Eso vacía al Panel de Inteligencia (no hay
etapa actual, no hay peers comparables) en los ~200 expedientes que
sembramos con `scripts/seed_hcdn_real.py`.

Este script no toca la fuente: aplica la heurística de
`praxis.domain.inferencia_estado.inferir_estado_y_caducidad` sobre el
trámite ya guardado, y persiste los 4 campos derivados:

  - estado
  - fecha_caducidad
  - fecha_caducidad_original
  - prorrogado

Es idempotente: correrlo dos veces da el mismo resultado.

Uso:
    uv run python -m scripts.rehidratar_estados
    uv run python -m scripts.rehidratar_estados --dry-run
    uv run python -m scripts.rehidratar_estados --batch 100 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from praxis.config import get_settings
from praxis.domain.inferencia_estado import inferir_estado_y_caducidad
from praxis.infrastructure.persistence.mappers import to_expediente
from praxis.infrastructure.persistence.models import ExpedienteOrm


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[rehidratar] DB: {settings.database_url}")
    print(f"[rehidratar] Batch size: {args.batch}")
    print(f"[rehidratar] Dry run: {args.dry_run}")
    print()

    total = 0
    cambios_estado = 0
    cambios_caducidad = 0
    sin_cambios = 0
    contador_por_estado: dict[str, int] = {}

    started_at = time.monotonic()

    try:
        offset = 0
        while True:
            async with sm() as session:
                # selectinload del trámite — la inferencia lo necesita.
                stmt = (
                    select(ExpedienteOrm)
                    .order_by(ExpedienteOrm.id)
                    .limit(args.batch)
                    .offset(offset)
                    .options(
                        selectinload(ExpedienteOrm.firmantes),
                        selectinload(ExpedienteOrm.giros),
                        selectinload(ExpedienteOrm.tramite),
                    )
                )
                result = await session.execute(stmt)
                orms = list(result.scalars())

                if not orms:
                    break

                for orm in orms:
                    total += 1
                    expediente = to_expediente(orm)
                    inferencia = inferir_estado_y_caducidad(expediente)

                    cambio_estado = orm.estado != inferencia.estado.value
                    cambio_caducidad = (
                        orm.fecha_caducidad != inferencia.fecha_caducidad
                        or orm.fecha_caducidad_original != inferencia.fecha_caducidad_original
                        or orm.prorrogado != inferencia.prorrogado
                    )

                    if cambio_estado:
                        cambios_estado += 1
                        if args.verbose:
                            print(
                                f"  ~ {expediente.numero}: "
                                f"{orm.estado} → {inferencia.estado.value}"
                            )

                    if cambio_caducidad:
                        cambios_caducidad += 1

                    if not (cambio_estado or cambio_caducidad):
                        sin_cambios += 1

                    contador_por_estado[inferencia.estado.value] = (
                        contador_por_estado.get(inferencia.estado.value, 0) + 1
                    )

                    if not args.dry_run:
                        orm.estado = inferencia.estado.value
                        orm.fecha_caducidad = inferencia.fecha_caducidad
                        orm.fecha_caducidad_original = inferencia.fecha_caducidad_original
                        orm.prorrogado = inferencia.prorrogado

                if not args.dry_run:
                    await session.commit()

                hechos = total
                elapsed = time.monotonic() - started_at
                rate = hechos / elapsed if elapsed > 0 else 0
                print(
                    f"  - batch offset={offset} | acumulado: {hechos} "
                    f"({rate:.0f}/s | ~{cambios_estado} estado, "
                    f"~{cambios_caducidad} caducidad, ={sin_cambios} sin cambios)"
                )
                offset += args.batch
    except KeyboardInterrupt:
        print()
        print("[rehidratar] Interrumpido por usuario.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Total recorridos:   {total}")
    print(f"  Cambios de estado:  {cambios_estado}")
    print(f"  Cambios caducidad:  {cambios_caducidad}")
    print(f"  Sin cambios:        {sin_cambios}")
    print(f"  Tiempo total:       {elapsed:.1f}s")
    if args.dry_run:
        print("  (dry-run: NO se persistió nada)")
    print()
    print("  Distribución de estados resultante:")
    for estado, n in sorted(contador_por_estado.items(), key=lambda x: -x[1]):
        print(f"    {estado:30s} {n:5d}")
    print("=" * 60)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Rehidrata estado + caducidad de los expedientes en DB"
    )
    p.add_argument(
        "--batch",
        type=int,
        default=200,
        help="Cantidad de expedientes a procesar por transacción (default 200)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="No persiste cambios; solo reporta qué pasaría",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Imprime cada cambio de estado",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
