"""Segundo round del spike BO: investigar alternativas al SPA.

El primer round descubrió que el portal BO es una SPA React: las URLs
con fecha distinta devuelven el mismo HTML inicial y los datos los
fetcha JavaScript. Pero hay dos pistas más prometedoras:

1. PDFs del día por sección en S3:
   `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/<seccion>.pdf`
2. Posible patrón histórico:
   `https://s3.arsat.com.ar/cdn-bo-001/<YYYY>/<MM>/<DD>/<seccion>.pdf`
3. SAIJ — `https://www.argentina.gob.ar/normativa` — alternativa
   estructurada del Estado para normativa nacional.
4. Endpoints SOAP/JSON inferibles del HTML del SPA.

Este round prueba esos 4 vectores con 1 req/seg.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

UA = "PraxisAsesor/0.1 (+contacto@dominio.com; monitoreo legislativo Praxis Asesor)"
RATE_LIMIT_SECONDS = 1.0
TIMEOUT_SECONDS = 30.0
OUT_DIR = Path(__file__).resolve().parent.parent / "spikes" / "bo"


async def fetch(client: httpx.AsyncClient, url: str, label: str) -> tuple[int, bytes, str]:
    try:
        resp = await client.get(url, follow_redirects=False)
    except httpx.RequestError as exc:
        print(f"  [X] {label:55s} ERR  {exc!s:.60s}")
        return 0, b"", ""

    body = resp.content
    ctype = resp.headers.get("content-type", "-").split(";", 1)[0]
    flag = "[OK]" if resp.is_success else "[X] "
    print(f"  {flag} {label:55s} {resp.status_code:3d}  {ctype:25s}  {len(body):>9d} B")
    return resp.status_code, body, ctype


async def probar_pdf_del_dia(client: httpx.AsyncClient) -> None:
    print("\n# PDFs del día (las 4 secciones)")
    base = "https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia"
    for seccion in ("primera", "segunda", "tercera", "cuarta"):
        status, body, _ctype = await fetch(
            client, f"{base}/{seccion}.pdf", label=f"S3 pdf-del-dia/{seccion}.pdf",
        )
        if status == 200 and b"%PDF" in body[:10]:
            (OUT_DIR / f"pdf_del_dia__{seccion}.pdf").write_bytes(body)
        await asyncio.sleep(RATE_LIMIT_SECONDS)


async def probar_pdf_historico(client: httpx.AsyncClient) -> None:
    print("\n# PDFs históricos por fecha (patrones probables)")
    base = "https://s3.arsat.com.ar/cdn-bo-001"
    fechas = [date.today() - timedelta(days=d) for d in (1, 2, 7, 14)]
    secciones = ("primera", "cuarta")    # las 2 prioritarias del MVP
    # Probar varios layouts posibles de carpeta:
    for fecha in fechas:
        anio = fecha.year
        mes = f"{fecha.month:02d}"
        dia = f"{fecha.day:02d}"
        candidates = [
            f"{base}/{anio}/{mes}/{dia}/primera.pdf",
            f"{base}/{anio}-{mes}-{dia}/primera.pdf",
            f"{base}/{anio}{mes}{dia}/primera.pdf",
            f"{base}/historico/{anio}/{mes}/{dia}/primera.pdf",
            f"{base}/seccion/primera/{anio}{mes}{dia}.pdf",
            f"{base}/seccion/primera/{anio}-{mes}-{dia}.pdf",
            f"{base}/pdfs/{anio}-{mes}-{dia}/primera.pdf",
        ]
        for url in candidates:
            await fetch(client, url, label=f"S3 {fecha} ({url[42:80]})")
            await asyncio.sleep(RATE_LIMIT_SECONDS)
        # Solo probar todos los candidates con la primera fecha; con las
        # demás, intentar solo los que hayan respondido antes.
        if fecha != fechas[0]:
            break
        _ = secciones  # acá se ampliaría a todas las secciones si vale.


async def probar_saij(client: httpx.AsyncClient) -> None:
    print("\n# SAIJ — argentina.gob.ar/normativa")
    urls = [
        "https://www.argentina.gob.ar/normativa",
        "https://www.argentina.gob.ar/normativa?jurisdiccion=Nacional",
        "https://www.argentina.gob.ar/normativa/nacional",
        "https://www.argentina.gob.ar/normativa/nacional/decretos",
    ]
    for url in urls:
        await fetch(client, url, label=f"SAIJ {url[36:74]}")
        await asyncio.sleep(RATE_LIMIT_SECONDS)


async def probar_endpoints_inferibles(client: httpx.AsyncClient) -> None:
    print("\n# Endpoints API inferibles del SPA")
    base = "https://www.boletinoficial.gob.ar"
    urls = [
        f"{base}/seccion/all",
        f"{base}/seccion/primera/json",
        f"{base}/api/seccion/primera",
        f"{base}/seccion/actualizar/0",
        f"{base}/seccion/primera/2026-06-01.json",
        f"{base}/redirect/primera/0/01-06-2026",
        f"{base}/redirect/primera/0/01062026",
    ]
    for url in urls:
        await fetch(client, url, label=f"BO {url[37:75]}")
        await asyncio.sleep(RATE_LIMIT_SECONDS)


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("# Spike BO round 2 — alternativas al SPA")
    print(f"# Output: {OUT_DIR}\n")
    started_at = time.time()
    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept": "*/*"},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        await probar_pdf_del_dia(client)
        await probar_pdf_historico(client)
        await probar_saij(client)
        await probar_endpoints_inferibles(client)
    print(f"\n# Done en {time.time() - started_at:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
