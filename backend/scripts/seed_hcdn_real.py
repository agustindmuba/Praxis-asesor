"""Seed real: itera sobre números HCDN secuenciales y los persiste en DB.

Para que la UI no se vea insípida con 2 expedientes fake, este script
trae proyectos reales del portal HCDN haciendo una llamada por número.

Uso:
    uv run python -m scripts.seed_hcdn_real --anio 2025 --desde 1 --hasta 200
    uv run python -m scripts.seed_hcdn_real --anio 2024 --desde 1 --hasta 150 --origen D

Respeta el rate limit del HcdnScraper (1 req/s). Para un rango de 200
números, espera ~3-4 minutos. Idempotente: si un expediente ya existe
en DB, lo saltea sin error.

Progreso en stdout: cada N requests imprime un resumen. Ctrl+C corta
limpio (los expedientes ya bajados quedan en DB).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

import httpx
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.domain import (
    Camara,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
    NumeroExpediente,
    OrigenExpediente,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteRepository,
)
from praxis.infrastructure.scrapers.hcdn import HcdnScraper

log = structlog.get_logger()


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    origen = OrigenExpediente.from_code(args.origen)
    print(f"[seed-hcdn] DB: {settings.database_url}")
    print(f"[seed-hcdn] Rango: {args.desde}..{args.hasta}-{origen.value}-{args.anio}")
    print(f"[seed-hcdn] Total a probar: {args.hasta - args.desde + 1}")
    print()

    creados = 0
    duplicados = 0
    no_encontrados = 0
    errores = 0

    started_at = time.monotonic()

    try:
        async with httpx.AsyncClient() as http_client:
            scraper = HcdnScraper(http_client)
            for n in range(args.desde, args.hasta + 1):
                try:
                    numero = NumeroExpediente(
                        numero=n,
                        origen=origen,
                        anio=args.anio,
                        camara=Camara.HCDN,
                    )
                except ValueError as exc:
                    print(f"  ! número {n} inválido: {exc}")
                    continue

                # Llamamos al scraper.
                try:
                    expediente = await scraper.buscar_por_numero(numero)
                except ExpedienteNoEncontrado:
                    no_encontrados += 1
                    if args.verbose:
                        print(f"  · {numero} no encontrado")
                    continue
                except FuenteNoDisponible as exc:
                    errores += 1
                    print(f"  ✗ {numero}: fuente no disponible ({exc})")
                    continue
                except Exception as exc:
                    errores += 1
                    print(f"  ✗ {numero}: error inesperado ({type(exc).__name__}: {exc})")
                    continue

                # Persistimos. Idempotente: IntegrityError = ya existe.
                async with sm() as session:
                    repo = SqlAlchemyExpedienteRepository(session)
                    try:
                        creado = await repo.crear(expediente)
                        await session.commit()
                        creados += 1
                        print(
                            f"  + {creado.numero} :: "
                            f"{(creado.titulo or '')[:80]}"
                        )
                    except IntegrityError:
                        await session.rollback()
                        duplicados += 1
                        if args.verbose:
                            print(f"  ↻ {numero} ya estaba en DB")
                    except Exception as exc:
                        await session.rollback()
                        errores += 1
                        print(f"  ✗ {numero}: error al persistir ({exc})")

                # Resumen cada 25 números.
                hechos = n - args.desde + 1
                if hechos % 25 == 0:
                    elapsed = time.monotonic() - started_at
                    rate = hechos / elapsed if elapsed > 0 else 0
                    print(
                        f"  ─ progreso: {hechos}/{args.hasta - args.desde + 1} "
                        f"({rate:.1f} req/s · "
                        f"+{creados} ↻{duplicados} ·{no_encontrados} ✗{errores})"
                    )
    except KeyboardInterrupt:
        print()
        print("[seed-hcdn] Interrumpido por usuario. Lo bajado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Creados:        {creados}")
    print(f"  Ya estaban:     {duplicados}")
    print(f"  No encontrados: {no_encontrados}")
    print(f"  Errores:        {errores}")
    print(f"  Tiempo total:   {elapsed:.1f}s")
    print("=" * 60)
    return 0 if errores == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seed de expedientes HCDN reales")
    p.add_argument("--anio", type=int, required=True, help="Año (ej. 2025)")
    p.add_argument("--desde", type=int, default=1, help="Número inicial (default 1)")
    p.add_argument(
        "--hasta",
        type=int,
        default=200,
        help="Número final inclusivo (default 200)",
    )
    p.add_argument(
        "--origen",
        default="D",
        choices=[o.value for o in OrigenExpediente],
        help="Código de origen HCDN (default D = Diputados)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Imprime los 'no encontrado' y 'duplicados' (mucho ruido)",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
