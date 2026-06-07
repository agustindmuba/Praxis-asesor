"""Re-scrapea expedientes ya cargados para llenar huecos (feat-48.3).

Caso de uso: el seed inicial bajó 441 expedientes pero solo 229 tienen
sumario en DB (52%). Esto puede ser por:
  - el seed corrió con un parser viejo que no extraía el sumario del modal,
  - errores transitorios del portal (timeout, 5xx) que no se reintentaron,
  - el expediente no tenía sumario en el portal cuando se bajó pero
    ahora sí.

Este script:
  1. Lee de DB todos los expedientes sin sumario (camara=HCDN).
  2. Para cada uno: scrapea con HcdnScraper.buscar_por_numero(...).
  3. UPDATE en DB los campos `sumario`, `titulo`, `texto_url`,
     `estado`, `fecha_caducidad`, `prorrogado`. (Firmantes y trámite
     NO se tocan en este sprint — requieren cleanup cuidadoso.)

Uso:
    # Primero: dry-run para ver cuántos faltan
    uv run python -m scripts.rescrapear_huecos --dry-run

    # Probar con 5 antes de lanzar todo
    uv run python -m scripts.rescrapear_huecos --limite 5 -v

    # Lanzar para todos
    uv run python -m scripts.rescrapear_huecos

Idempotente y resumible: si lo cortás con Ctrl+C, los cambios commiteados
quedan. Re-ejecutarlo solo procesa los que TODAVÍA no tienen sumario.

Rate limit del scraper: 1 req/s. Para 212 expedientes, ~4 min total.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.domain import (
    Camara,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
    NumeroExpediente,
    OrigenExpediente,
)
from praxis.infrastructure.scrapers.hcdn import HcdnScraper

log = structlog.get_logger()


_SELECT_HUECOS = text("""
    SELECT id, numero, origen, anio, camara
    FROM expediente
    WHERE (sumario IS NULL OR sumario = '')
      AND camara = :camara
    ORDER BY anio DESC, numero ASC
""")


_UPDATE_EXPEDIENTE = text("""
    UPDATE expediente SET
        sumario = COALESCE(:sumario, sumario),
        titulo = COALESCE(:titulo, titulo),
        texto_url = COALESCE(:texto_url, texto_url),
        estado = :estado,
        fecha_caducidad = COALESCE(:fecha_caducidad, fecha_caducidad),
        fecha_caducidad_original = COALESCE(
            :fecha_caducidad_original, fecha_caducidad_original
        ),
        prorrogado = :prorrogado,
        actualizado_en = now()
    WHERE id = :id
""")


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[rescrapear-huecos] DB: {settings.database_url}")
    print(f"[rescrapear-huecos] Cámara: {args.camara}")
    if args.limite:
        print(f"[rescrapear-huecos] Límite: {args.limite}")
    if args.dry_run:
        print("[rescrapear-huecos] *** DRY-RUN — no se va a tocar DB ni portal ***")
    print()

    # 1) Leer huecos
    async with sm() as session:
        result = await session.execute(_SELECT_HUECOS, {"camara": args.camara})
        huecos = [
            {
                "id": row[0],
                "numero": row[1],
                "origen": row[2],
                "anio": row[3],
                "camara": row[4],
            }
            for row in result.all()
        ]

    total = len(huecos)
    print(f"[rescrapear-huecos] Expedientes sin sumario: {total}")
    if args.limite and args.limite < total:
        huecos = huecos[: args.limite]
        print(f"[rescrapear-huecos] Procesando primeros {len(huecos)}")
    print()

    if args.dry_run:
        for h in huecos[:10]:
            print(f"  ·  {h['numero']:>4}-{h['origen']}-{h['anio']}")
        if len(huecos) > 10:
            print(f"  ... y {len(huecos) - 10} más")
        await engine.dispose()
        return 0

    if not huecos:
        print("[rescrapear-huecos] Nada para hacer.")
        await engine.dispose()
        return 0

    # 2) Procesar uno por uno
    completados = 0
    sin_cambios = 0
    no_encontrados = 0
    errores = 0
    started_at = time.monotonic()

    try:
        async with httpx.AsyncClient() as http_client:
            scraper = HcdnScraper(http_client)
            for i, h in enumerate(huecos, 1):
                try:
                    numero = NumeroExpediente(
                        numero=h["numero"],
                        origen=OrigenExpediente(h["origen"]),
                        anio=h["anio"],
                        camara=Camara(h["camara"]),
                    )
                except ValueError as exc:
                    print(f"  ! {h['numero']}-{h['origen']}-{h['anio']} inválido: {exc}")
                    errores += 1
                    continue

                try:
                    expediente = await scraper.buscar_por_numero(numero)
                except ExpedienteNoEncontrado:
                    no_encontrados += 1
                    if args.verbose:
                        print(f"  · {numero} no encontrado en portal")
                    continue
                except FuenteNoDisponible as exc:
                    errores += 1
                    print(f"  ✗ {numero}: fuente no disponible ({exc})")
                    continue
                except Exception as exc:
                    errores += 1
                    print(
                        f"  ✗ {numero}: error inesperado "
                        f"({type(exc).__name__}: {exc})"
                    )
                    continue

                # Si el sumario sigue siendo None / vacío después de
                # re-scrapear, no avanzamos — el portal realmente no
                # tiene sumario para este expediente todavía.
                if not expediente.sumario:
                    sin_cambios += 1
                    if args.verbose:
                        print(f"  · {numero}: portal aún no trae sumario")
                    continue

                # UPDATE
                async with sm() as session:
                    try:
                        await session.execute(
                            _UPDATE_EXPEDIENTE,
                            {
                                "id": h["id"],
                                "sumario": expediente.sumario,
                                "titulo": expediente.titulo,
                                "texto_url": expediente.texto_url,
                                "estado": expediente.estado.value,
                                "fecha_caducidad": expediente.fecha_caducidad,
                                "fecha_caducidad_original": (
                                    expediente.fecha_caducidad_original
                                ),
                                "prorrogado": expediente.prorrogado,
                            },
                        )
                        await session.commit()
                        completados += 1
                        if args.verbose:
                            print(
                                f"  ✓ {numero} actualizado :: "
                                f"{(expediente.sumario or '')[:60]}..."
                            )
                    except Exception as exc:
                        await session.rollback()
                        errores += 1
                        print(f"  ✗ {numero}: error al persistir ({exc})")

                # Progreso cada 25
                if i % 25 == 0:
                    elapsed = time.monotonic() - started_at
                    rate = i / elapsed if elapsed > 0 else 0
                    print(
                        f"  ─ progreso: {i}/{len(huecos)} "
                        f"({rate:.1f} req/s · "
                        f"✓{completados} ·{sin_cambios} ?{no_encontrados} ✗{errores})"
                    )

    except KeyboardInterrupt:
        print()
        print("[rescrapear-huecos] Interrumpido. Lo commiteado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Actualizados:        {completados}")
    print(f"  Portal sin sumario:  {sin_cambios}")
    print(f"  No encontrados:      {no_encontrados}")
    print(f"  Errores:             {errores}")
    print(f"  Tiempo total:        {elapsed:.1f}s")
    print("=" * 60)
    return 0 if errores == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Re-scrapea expedientes sin sumario en DB"
    )
    p.add_argument(
        "--camara",
        default="HCDN",
        choices=[c.value for c in Camara],
        help="Cámara objetivo (default HCDN)",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=None,
        help="Límite de expedientes a procesar (default todos)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo cuenta y muestra qué procesaría, no toca portal ni DB",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Imprime una línea por cada expediente procesado",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
