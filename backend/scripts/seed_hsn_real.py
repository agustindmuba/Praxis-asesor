"""Seed real: itera números HSN secuenciales y los persiste (feat-49.4).

Modelo de numeración HSN: cada expediente tiene UN N° único por
(origen, año). El TIPO (PL, PR, PD, PC) NO es parte del identificador
— solo aparece en la URL canónica del portal:

    https://www.senado.gob.ar/parlamentario/comisiones/verExp/N.YY/ORIGEN/TIPO

Para resolver el N° 239 de S/2024, el script prueba PL → PR → PD → PC
hasta encontrar uno que devuelva HTML válido. En promedio ~1.5 requests
por número existente (la mayoría son PL).

Series soportadas (orígenes):
    S   — Senadores (mayoritaria)
    CD  — Revisión desde Diputados
    PE  — Ejecutivo

Uso:
    # Año entero, todos los orígenes — recomendado
    uv run python -m scripts.seed_hsn_real --anio 2024

    # Solo origen S, hasta el 2000
    uv run python -m scripts.seed_hsn_real --anio 2024 --origen S --hasta 2000

    # Smoke con 5 N° por origen
    uv run python -m scripts.seed_hsn_real --anio 2024 --limite-por-origen 5 -v

Idempotente: los duplicados (IntegrityError) se saltean.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

# UTF-8 en stdout (Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
    TipoExpediente,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteRepository,
)
from praxis.infrastructure.scrapers.hsn import HsnScraper

log = structlog.get_logger()


# Orden en que probamos tipos para cada N°. PL primero porque es el más
# común; el resto va por frecuencia decreciente.
TIPOS_A_PROBAR: list[TipoExpediente] = [
    TipoExpediente.PROYECTO_LEY,
    TipoExpediente.PROYECTO_RESOLUCION,
    TipoExpediente.PROYECTO_DECLARACION,
    TipoExpediente.PROYECTO_COMUNICACION,
]


ORIGENES_POR_DEFECTO: list[OrigenExpediente] = [
    OrigenExpediente.SENADOR,
    OrigenExpediente.REVISION_DIPUTADOS,
    OrigenExpediente.EJECUTIVO,
]


async def resolver_tipo(
    scraper: HsnScraper, numero: NumeroExpediente
) -> tuple[TipoExpediente | None, object]:
    """Prueba los 4 tipos hasta encontrar uno que devuelva expediente.

    Devuelve (tipo_encontrado, expediente) o (None, None) si ninguno
    devolvió HTML válido. Cada prueba respeta el rate-limit del scraper.
    """
    for tipo in TIPOS_A_PROBAR:
        try:
            expediente = await scraper.buscar_por_numero(numero, tipo=tipo)
            return tipo, expediente
        except ExpedienteNoEncontrado:
            continue
    return None, None


async def procesar_origen(
    *,
    scraper: HsnScraper,
    sm,
    anio: int,
    origen: OrigenExpediente,
    desde: int,
    hasta: int | None,
    stop_tras_404: int,
    verbose: bool,
) -> dict[str, int]:
    """Itera N° de un origen específico y persiste cada uno encontrado."""
    creados = 0
    duplicados = 0
    no_encontrados = 0
    errores = 0
    consecutivos_404 = 0

    etiqueta = f"{anio}/{origen.value}"
    print(f"\n=== Origen {etiqueta} ===")

    n = desde
    while True:
        if hasta is not None and n > hasta:
            break

        try:
            numero = NumeroExpediente(
                numero=n,
                origen=origen,
                anio=anio,
                camara=Camara.HSN,
            )
        except ValueError as exc:
            print(f"  ! N°{n}: {exc}")
            n += 1
            continue

        try:
            tipo, expediente = await resolver_tipo(scraper, numero)
        except FuenteNoDisponible as exc:
            errores += 1
            consecutivos_404 = 0
            print(f"  ✗ {numero}: fuente ({exc})")
            n += 1
            continue
        except Exception as exc:
            errores += 1
            consecutivos_404 = 0
            print(f"  ✗ {numero}: {type(exc).__name__}: {exc}")
            n += 1
            continue

        if tipo is None or expediente is None:
            no_encontrados += 1
            consecutivos_404 += 1
            if verbose:
                print(f"  · {numero}: ningún tipo válido ({consecutivos_404}/{stop_tras_404})")
            if consecutivos_404 >= stop_tras_404:
                print(f"  ─ stop por {stop_tras_404} 404 consecutivos en n°{n}")
                break
            n += 1
            continue

        consecutivos_404 = 0
        async with sm() as session:
            repo = SqlAlchemyExpedienteRepository(session)
            try:
                creado = await repo.crear(expediente)
                await session.commit()
                creados += 1
                print(
                    f"  + {creado.numero}/{tipo.value} :: "
                    f"{(creado.titulo or '')[:70]}"
                )
            except IntegrityError:
                await session.rollback()
                duplicados += 1
                if verbose:
                    print(f"  ↻ {numero} ya estaba")
            except Exception as exc:
                await session.rollback()
                errores += 1
                print(f"  ✗ {numero}: persist ({exc})")

        n += 1

    print(
        f"  resumen {etiqueta}: +{creados} ↻{duplicados} "
        f"·{no_encontrados} ✗{errores}"
    )
    return {
        "creados": creados,
        "duplicados": duplicados,
        "no_encontrados": no_encontrados,
        "errores": errores,
    }


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[seed-hsn] DB: {settings.database_url}")
    print(f"[seed-hsn] Año: {args.anio}")
    print(f"[seed-hsn] Stop tras 404 consecutivos: {args.stop_tras_404}")
    if args.limite_por_origen:
        print(f"[seed-hsn] Límite por origen: {args.limite_por_origen}")

    if args.origen:
        origenes = [OrigenExpediente.from_code(args.origen)]
    else:
        origenes = ORIGENES_POR_DEFECTO
    print(f"[seed-hsn] Orígenes: {[o.value for o in origenes]}")

    totales = {"creados": 0, "duplicados": 0, "no_encontrados": 0, "errores": 0}
    started_at = time.monotonic()

    try:
        async with httpx.AsyncClient() as http_client:
            scraper = HsnScraper(http_client)
            for origen in origenes:
                hasta = (
                    args.hasta
                    if args.hasta is not None
                    else (
                        args.limite_por_origen + args.desde - 1
                        if args.limite_por_origen
                        else None
                    )
                )
                serie = await procesar_origen(
                    scraper=scraper,
                    sm=sm,
                    anio=args.anio,
                    origen=origen,
                    desde=args.desde,
                    hasta=hasta,
                    stop_tras_404=args.stop_tras_404,
                    verbose=args.verbose,
                )
                for k, v in serie.items():
                    totales[k] += v
    except KeyboardInterrupt:
        print()
        print("[seed-hsn] Interrumpido. Lo commiteado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Creados:        {totales['creados']}")
    print(f"  Ya estaban:     {totales['duplicados']}")
    print(f"  No encontrados: {totales['no_encontrados']}")
    print(f"  Errores:        {totales['errores']}")
    print(f"  Tiempo total:   {elapsed:.1f}s")
    print("=" * 60)
    return 0 if totales["errores"] == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seed de expedientes HSN reales")
    p.add_argument("--anio", type=int, required=True, help="Año (ej. 2024)")
    p.add_argument("--desde", type=int, default=1, help="N° inicial por origen")
    p.add_argument(
        "--hasta", type=int, default=None,
        help="N° final inclusivo por origen (default: stop por 404)"
    )
    p.add_argument(
        "--limite-por-origen", type=int, default=None,
        help="Máximo de N° a probar por origen (alternativo a --hasta)",
    )
    p.add_argument(
        "--stop-tras-404", type=int, default=15,
        help="Cortar serie tras N 404 consecutivos (default 15)",
    )
    p.add_argument(
        "--origen", default=None,
        help="Si se setea, procesa solo este origen (S/CD/PE)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
