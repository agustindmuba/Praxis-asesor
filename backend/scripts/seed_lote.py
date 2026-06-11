"""Wrapper que dispara seed_hcdn_real + seed_hsn_real en lote por rango
de años (feat-50.helper).

Iterá años de forma DESCENDENTE (más reciente primero) porque:
- Más reciente = más útil políticamente.
- Si se corta a la mitad, lo que quedó es lo más relevante.

Ejecuta cada año en su propio subprocess (uv run python -m ...). Si uno
falla, sigue con el siguiente. Idempotente: los duplicados se saltean.

Uso típico:
    # HCDN + HSN 2015-2022 en cadena (16 corridas seguidas)
    uv run python -m scripts.seed_lote --camara ambas --desde-anio 2015 --hasta-anio 2022

    # Solo HCDN, todos los años 2015-2022
    uv run python -m scripts.seed_lote --camara HCDN --desde-anio 2015 --hasta-anio 2022

    # Solo HSN del histórico 2000-2014
    uv run python -m scripts.seed_lote --camara HSN --desde-anio 2000 --hasta-anio 2014

Ctrl+C corta limpio: termina el subprocess actual y para.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# UTF-8 en stdout (Windows cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


CAMARAS_VALIDAS = ("HCDN", "HSN", "ambas")


def correr_hcdn(anio: int, desde: int, hasta: int) -> int:
    """Llama a seed_hcdn_real para un año. Devuelve el exit code."""
    print(f"\n{'━' * 70}")
    print(f"━ HCDN {anio} (rango {desde}..{hasta})")
    print(f"{'━' * 70}\n", flush=True)
    cmd = [
        sys.executable, "-m", "scripts.seed_hcdn_real",
        "--anio", str(anio),
        "--desde", str(desde),
        "--hasta", str(hasta),
    ]
    return subprocess.call(cmd)


def correr_hsn(anio: int) -> int:
    """Llama a seed_hsn_real para un año. Devuelve el exit code."""
    print(f"\n{'━' * 70}")
    print(f"━ HSN {anio} (todos los orígenes, stop por 15 fantasmas)")
    print(f"{'━' * 70}\n", flush=True)
    cmd = [
        sys.executable, "-m", "scripts.seed_hsn_real",
        "--anio", str(anio),
    ]
    return subprocess.call(cmd)


def main(args: argparse.Namespace) -> int:
    if args.desde_anio > args.hasta_anio:
        print(
            f"ERROR: --desde-anio ({args.desde_anio}) > "
            f"--hasta-anio ({args.hasta_anio})"
        )
        return 1

    # Iterar de hasta_anio hacia desde_anio (descendente).
    anios = list(range(args.hasta_anio, args.desde_anio - 1, -1))
    fases = []
    if args.camara in ("HCDN", "ambas"):
        fases.append(("HCDN", correr_hcdn))
    if args.camara in ("HSN", "ambas"):
        fases.append(("HSN", correr_hsn))

    total_pasos = len(anios) * len(fases)
    print(f"\n{'═' * 70}")
    print(f"  SEED LOTE")
    print(f"{'═' * 70}")
    print(f"  Cámara(s):  {args.camara}")
    print(f"  Años:       {anios}")
    print(f"  Total pasos: {total_pasos}")
    print(f"  HCDN rango por año: {args.hcdn_desde}..{args.hcdn_hasta}")
    print(f"{'═' * 70}\n", flush=True)

    paso = 0
    started_at = time.monotonic()
    fallidos = []

    try:
        for anio in anios:
            for nombre, fn in fases:
                paso += 1
                elapsed = time.monotonic() - started_at
                eta_avg = elapsed / paso if paso > 1 else 0
                eta_restante = eta_avg * (total_pasos - paso)
                eta_min = int(eta_restante / 60)
                print(
                    f"\n[{paso}/{total_pasos}] · {nombre} {anio} · "
                    f"transcurrido {int(elapsed/60)}min · ETA ~{eta_min}min",
                    flush=True,
                )
                if nombre == "HCDN":
                    rc = fn(anio, args.hcdn_desde, args.hcdn_hasta)
                else:
                    rc = fn(anio)
                if rc != 0:
                    fallidos.append(f"{nombre} {anio} (rc={rc})")
                    print(
                        f"⚠ {nombre} {anio} terminó con rc={rc}, sigo...",
                        flush=True,
                    )
    except KeyboardInterrupt:
        print(
            f"\n\n━ Interrumpido por usuario en el paso {paso}/{total_pasos}",
            flush=True,
        )

    elapsed = time.monotonic() - started_at
    print(f"\n{'═' * 70}")
    print(f"  RESUMEN")
    print(f"{'═' * 70}")
    print(f"  Pasos completados: {paso}/{total_pasos}")
    print(f"  Tiempo total:      {int(elapsed/60)} min ({int(elapsed)}s)")
    if fallidos:
        print(f"  Fallidos ({len(fallidos)}):")
        for f in fallidos:
            print(f"    · {f}")
    else:
        print(f"  Sin fallos")
    print(f"{'═' * 70}")
    return 0 if not fallidos else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seed lote: HCDN + HSN en cadena por rango de años"
    )
    p.add_argument(
        "--camara",
        default="ambas",
        choices=CAMARAS_VALIDAS,
        help="Qué cámara(s) procesar (default: ambas)",
    )
    p.add_argument(
        "--desde-anio", type=int, required=True,
        help="Año mínimo (ej. 2015)",
    )
    p.add_argument(
        "--hasta-anio", type=int, required=True,
        help="Año máximo (ej. 2022)",
    )
    p.add_argument(
        "--hcdn-desde", type=int, default=1,
        help="N° inicial HCDN por año (default 1)",
    )
    p.add_argument(
        "--hcdn-hasta", type=int, default=5000,
        help="N° final HCDN por año (default 5000)",
    )
    return p


if __name__ == "__main__":
    sys.exit(main(_build_parser().parse_args()))
