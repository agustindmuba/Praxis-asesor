"""Seed real: trae las votaciones nominales de HCDN y las persiste en DB.

El briefing pre-sesión (spec 14) recomienda voto en base a cómo votaron
los bloques en proyectos similares. Para que la recomendación tenga
sustento real, necesitamos un corpus de votaciones, no fake data.

Uso:
    uv run python -m scripts.seed_votaciones_hcdn --anio 2025
    uv run python -m scripts.seed_votaciones_hcdn --anio 2026 --max 50
    uv run python -m scripts.seed_votaciones_hcdn --desde 5800 --hasta 5937 -v

El portal expone hasta 500 actas más recientes en el listado. Para ir
más atrás se filtra por año. Cada acta detalle es ~885 KB con rate
limit 1 req/s, así que sembrar un año entero toma ~3-5 minutos.

Idempotente: si una votación ya está en DB (UNIQUE acta_id_hcdn), se
saltea.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.domain import ExpedienteNoEncontrado, FuenteNoDisponible
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyVotacionRepository,
)
from praxis.infrastructure.scrapers.hcdn.votaciones import (
    VotacionesHcdnScraper,
)


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[seed-votaciones] DB: {settings.database_url}")
    if args.anio:
        print(f"[seed-votaciones] Filtro: anio={args.anio}")
    elif args.desde or args.hasta:
        print(f"[seed-votaciones] Rango: {args.desde or 'inicio'}..{args.hasta or 'fin'}")
    if args.max:
        print(f"[seed-votaciones] Máximo: {args.max} actas")
    print()

    creados = 0
    duplicados = 0
    errores = 0
    started_at = time.monotonic()

    try:
        async with httpx.AsyncClient() as http_client:
            scraper = VotacionesHcdnScraper(http_client)

            print("[seed-votaciones] Bajando índice...")
            indice = await scraper.listar_indice(anio=args.anio)
            print(f"[seed-votaciones] Índice trae {len(indice)} actas")
            print()

            # Filtrar por rango si corresponde
            actas_ids = [it.acta_id for it in indice]
            if args.desde is not None:
                actas_ids = [a for a in actas_ids if a >= args.desde]
            if args.hasta is not None:
                actas_ids = [a for a in actas_ids if a <= args.hasta]
            if args.max:
                actas_ids = actas_ids[: args.max]

            print(f"[seed-votaciones] A procesar: {len(actas_ids)} actas")
            print()

            for n, acta_id in enumerate(actas_ids, 1):
                # Check rápido de duplicado antes de gastar request
                async with sm() as session:
                    repo = SqlAlchemyVotacionRepository(session)
                    existente = await repo.buscar_por_acta_id_hcdn(acta_id)
                    if existente is not None:
                        duplicados += 1
                        if args.verbose:
                            print(f"  ↻ acta {acta_id} ya estaba (id={existente.id})")
                        continue

                # Bajar el detalle
                try:
                    votacion, votos = await scraper.obtener_acta(acta_id)
                except (FuenteNoDisponible, ExpedienteNoEncontrado) as exc:
                    errores += 1
                    print(f"  ✗ acta {acta_id}: fuente no disponible ({exc})")
                    continue
                except Exception as exc:
                    errores += 1
                    print(
                        f"  ✗ acta {acta_id}: error inesperado "
                        f"({type(exc).__name__}: {exc})"
                    )
                    continue

                # Persistir
                async with sm() as session:
                    repo = SqlAlchemyVotacionRepository(session)
                    try:
                        creado = await repo.crear(votacion, votos)
                        await session.commit()
                        creados += 1
                        print(
                            f"  + acta {acta_id} :: {votacion.fecha} :: "
                            f"{votacion.asunto[:70]} ({len(votos)} votos)"
                        )
                        del creado  # solo lo necesitamos para confirmar el insert
                    except IntegrityError:
                        await session.rollback()
                        duplicados += 1
                        if args.verbose:
                            print(f"  ↻ acta {acta_id} race condition / ya existía")
                    except Exception as exc:
                        await session.rollback()
                        errores += 1
                        print(f"  ✗ acta {acta_id}: error al persistir ({exc})")

                # Progreso cada 10 actas
                if n % 10 == 0:
                    elapsed = time.monotonic() - started_at
                    rate = n / elapsed if elapsed > 0 else 0
                    print(
                        f"  - progreso: {n}/{len(actas_ids)} "
                        f"({rate:.2f}/s | +{creados} dup{duplicados} err{errores})"
                    )
    except KeyboardInterrupt:
        print()
        print("[seed-votaciones] Interrumpido. Lo bajado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Actas creadas:  {creados}")
    print(f"  Ya estaban:     {duplicados}")
    print(f"  Errores:        {errores}")
    print(f"  Tiempo total:   {elapsed:.1f}s")
    print("=" * 60)
    return 0 if errores == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seed real de votaciones nominales HCDN"
    )
    p.add_argument(
        "--anio",
        type=int,
        default=None,
        help="Filtra por año (1993-2026). Sin esto: últimas 500.",
    )
    p.add_argument(
        "--desde",
        type=int,
        default=None,
        help="Acta_id mínimo a procesar (filtro local sobre el índice)",
    )
    p.add_argument(
        "--hasta",
        type=int,
        default=None,
        help="Acta_id máximo a procesar (filtro local sobre el índice)",
    )
    p.add_argument(
        "--max",
        type=int,
        default=None,
        help="Cantidad máxima de actas a procesar (corta el índice)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Imprime las actas ya existentes (mucho ruido)",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
