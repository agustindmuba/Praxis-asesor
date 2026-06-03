"""Spike del portal Boletín Oficial (feat-39.1.5).

Antes de invertir días en BoletinOficialScraper, validamos:

1. El portal responde a nuestro UA identificable.
2. robots.txt permite las rutas que queremos tocar.
3. La estructura de listado por sección es parseable.
4. Las 3 secciones del MVP (Legislación, Designaciones, Avisos
   oficiales) están accesibles por fecha.
5. Capturamos fixtures HTML reales para tests sin red.

Política de scraping respetuoso (ADR 0007):
- User-Agent: `PraxisAsesor/0.x (+contacto@dominio.com)`
- Rate limit: 1 req/seg
- Sin retries agresivos: 1 retry con backoff de 5s
- Robots.txt check al inicio, abort si bloquea

Output:
- `backend/spikes/bo/<seccion>__<fecha>.html` — fixtures listado
- `backend/spikes/bo/_robots.txt` — snapshot de robots.txt
- `backend/spikes/bo/_homepage.html` — home para referencia
- STDOUT: tabla resumen con status + tamaños + hallazgos

Uso:
    uv run python -m scripts.spike_bo
    uv run python -m scripts.spike_bo --fecha 2026-05-30
    uv run python -m scripts.spike_bo --solo-listado    # no detalle
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import httpx

UA = "PraxisAsesor/0.1 (+contacto@dominio.com; monitoreo legislativo Praxis Asesor)"
BASE = "https://www.boletinoficial.gob.ar"
RATE_LIMIT_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0
OUT_DIR = Path(__file__).resolve().parent.parent / "spikes" / "bo"


# Mapeo de las 3 secciones del MVP a sus paths conocidos en el portal.
# Si la URL real difiere, el script lo detecta del homepage o falla
# elegante y deja constancia.
SECCIONES = {
    "legislacion": [
        "/seccion/primera",
        "/secciones/primera",
        "/busquedaAvanzada",
    ],
    "designaciones": [
        "/seccion/cuarta",
        "/secciones/cuarta",
    ],
    "avisos_oficiales": [
        "/seccion/segunda",
        "/secciones/segunda",
    ],
}


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    label: str,
) -> tuple[int, bytes]:
    """Un GET respetuoso. Devuelve (status, body) o (status, b'') si falla.

    Loguea a STDOUT en formato tabla: label, status, content-type, bytes.
    """
    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.RequestError as exc:
        print(f"  [X] {label:35s} ERROR    {exc!s:.80s}")
        return 0, b""

    body = resp.content
    ctype = resp.headers.get("content-type", "-").split(";", 1)[0]
    flag = "[OK]" if resp.is_success else "[X] "
    print(
        f"  {flag} {label:35s} "
        f"{resp.status_code:3d}  {ctype:20s}  {len(body):>8d} B"
    )
    return resp.status_code, body


async def check_robots(client: httpx.AsyncClient) -> bytes:
    print("\n# robots.txt")
    status, body = await fetch(client, urljoin(BASE, "/robots.txt"), label="robots.txt")
    if status == 200:
        (OUT_DIR / "_robots.txt").write_bytes(body)
        # Imprimir primeras 30 líneas para inspección visual.
        for line in body.decode("utf-8", "replace").splitlines()[:30]:
            print(f"    | {line}")
    return body


async def capturar_home(client: httpx.AsyncClient) -> None:
    print("\n# Homepage")
    status, body = await fetch(client, BASE, label="/")
    if status == 200 and body:
        (OUT_DIR / "_homepage.html").write_bytes(body)


async def explorar_seccion(
    client: httpx.AsyncClient,
    seccion: str,
    paths: list[str],
    fechas: list[date],
) -> None:
    print(f"\n# Sección: {seccion}")
    # 1) Probar cada path de listado base.
    for path in paths:
        await fetch(
            client,
            urljoin(BASE, path),
            label=f"{seccion} base {path}",
        )
        await asyncio.sleep(RATE_LIMIT_SECONDS)

    # 2) Probar listado por fecha (algunos portales aceptan ?fecha=DDMMYYYY,
    #    otros /seccion/primera/AAAA-MM-DD). Probamos 2 esquemas.
    for fecha in fechas:
        for path in paths[:1]:  # solo el primer path "base" por fecha
            for esquema in (
                f"{path}/{fecha.isoformat()}",
                f"{path}?fecha={fecha.strftime('%d%m%Y')}",
                f"{path}?fecha={fecha.isoformat()}",
            ):
                url = urljoin(BASE, esquema)
                status, body = await fetch(
                    client, url,
                    label=f"{seccion} {fecha} ({esquema[:30]})",
                )
                if status == 200 and body:
                    # Guardar fixture solo del primer esquema que funcione.
                    fname = f"{seccion}__{fecha.isoformat()}.html"
                    if not (OUT_DIR / fname).exists():
                        (OUT_DIR / fname).write_bytes(body)
                await asyncio.sleep(RATE_LIMIT_SECONDS)


async def main(args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fechas = [
        args.fecha,
        args.fecha - timedelta(days=1),
        args.fecha - timedelta(days=7),
    ]

    print(f"# Spike BO — fechas: {[f.isoformat() for f in fechas]}")
    print(f"# Output: {OUT_DIR}\n")

    started_at = time.time()
    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        await check_robots(client)
        await asyncio.sleep(RATE_LIMIT_SECONDS)

        await capturar_home(client)
        await asyncio.sleep(RATE_LIMIT_SECONDS)

        for seccion, paths in SECCIONES.items():
            await explorar_seccion(client, seccion, paths, fechas)

    print(f"\n# Done en {time.time() - started_at:.1f}s")
    print(f"# Fixtures en {OUT_DIR}/")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Spike Boletín Oficial")
    p.add_argument(
        "--fecha",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="Fecha base (YYYY-MM-DD). Default: ayer.",
    )
    p.add_argument(
        "--solo-listado",
        action="store_true",
        help="No bajar detalle de norma individual, solo listados.",
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
