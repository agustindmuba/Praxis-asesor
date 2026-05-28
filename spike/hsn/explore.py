#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27",
#     "beautifulsoup4>=4.12",
#     "lxml>=5.0",
# ]
# ///
"""Spike de exploración del portal HSN (Senado de la Nación).

Hallazgo del spike:
- URL canónica del detalle: /parlamentario/comisiones/verExp/NUM.YY/ORIGEN/TIPO.
- Página server-side rendered, UTF-8.
- Estructura interna: 5 tablas identificables por su atributo `summary=`:
    summary='Número de Expediente'        → cabecera con Nº/Origen/Tipo/Extracto.
    summary='Listado de Autores'          → autores.
    summary='Fechas en Mesa de Entradas'  → fechas Mesa + Dado Cuenta + DAE.
    summary='Fechas en Dirección Comisiones' → fecha Dir. Gral. Comisiones + dictamen.
    summary='Giros del Expediente a Comisiones' → giros con fechas in/out.
- PDF del texto: dentro de <div id="textoOriginal">, link a /parlamentario/parlamentaria/<docId>/downloadPdf.
- HSN NO tiene un event-log de trámite tipo HCDN: el "trámite" se reconstruye
  desde los timestamps de cada etapa (Mesa → DAE → Dir. Comisiones → Giros).

Uso:
    uv run spike/hsn/explore.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"
RATE_LIMIT_SECONDS = 1.0

CACHE_DIR = Path(__file__).parent.parent / "_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://www.senado.gob.ar"

# (num, anio_yy, origen, tipo)
SAMPLE_EXPEDIENTES = [
    ("239", "24", "S", "PL"),  # Sapag — etiquetado transgénicos
    ("1", "24", "CD", "PL"),  # primer CD-source de 2024
    ("1497", "20", "S", "PC"),  # de 2020, valida histórico
]


# ---------------------------------------------------------------------------
# Modelo del spike
# ---------------------------------------------------------------------------


@dataclass
class GiroHsn:
    comision: str
    fecha_ingreso: str | None = None
    fecha_egreso: str | None = None


@dataclass
class ExpedienteHsn:
    numero: str
    origen: str
    tipo: str
    url_origen: str
    origen_full: str | None = None
    tipo_full: str | None = None
    extracto: str | None = None
    autores: list[str] = field(default_factory=list)
    fecha_mesa_entradas: str | None = None
    fecha_dado_cuenta: str | None = None
    numero_dae: str | None = None
    fecha_dir_comisiones: str | None = None
    fecha_dictamen_mesa: str | None = None
    giros: list[GiroHsn] = field(default_factory=list)
    texto_pdf_url: str | None = None
    parseo_completo: bool = False


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------


def _cache_path(num: str, anio: str, origen: str, tipo: str) -> Path:
    return CACHE_DIR / f"hsn_{num}_{anio}_{origen}_{tipo}.html"


def fetch_expediente(
    client: httpx.Client, num: str, anio: str, origen: str, tipo: str
) -> tuple[str, str] | None:
    url = f"{BASE}/parlamentario/comisiones/verExp/{num}.{anio}/{origen}/{tipo}"
    cache = _cache_path(num, anio, origen, tipo)
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace"), url

    print(f"  GET {url}")
    time.sleep(RATE_LIMIT_SECONDS)
    try:
        r = client.get(url, timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        print(f"    error: {exc}")
        return None
    if r.status_code != 200:
        print(f"    status: {r.status_code}")
        return None
    if len(r.text) < 2000:
        print(f"    payload sospechoso (len={len(r.text)})")
        return None
    cache.write_text(r.text, encoding="utf-8")
    return r.text, url


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Colapsa whitespace y trimea. Esencial: HSN tiene mucho `\\n\\t` en cells."""
    return " ".join(text.split()).strip()


def _table_rows(table) -> list[list[str]]:
    """Devuelve filas de datos (sin la fila de headers) ya limpias."""
    out = []
    for row in table.find_all("tr"):
        if row.find("th") and not row.find("td"):
            continue
        cells = [_clean(td.get_text(" ")) for td in row.find_all("td")]
        if any(cells):
            out.append(cells)
    return out


def parse_hsn(html: str, num: str, anio: str, origen: str, tipo: str, url: str) -> ExpedienteHsn:
    soup = BeautifulSoup(html, "lxml")
    exp = ExpedienteHsn(
        numero=f"{num}/{anio}",
        origen=origen,
        tipo=tipo,
        url_origen=url,
    )

    # 1. Cabecera (summary='Número de Expediente').
    main = soup.find("table", summary=re.compile(r"N.mero de Expediente", re.I))
    if main:
        rows = _table_rows(main)
        if rows:
            row = rows[0]
            if len(row) >= 2:
                exp.origen_full = row[1] or None
            if len(row) >= 3:
                exp.tipo_full = row[2] or None
            if len(row) >= 4:
                exp.extracto = row[3] or None

    # 2. Autores (summary='Listado de Autores').
    autores_t = soup.find("table", summary=re.compile(r"Autores", re.I))
    if autores_t:
        for row in _table_rows(autores_t):
            for c in row:
                if c:
                    exp.autores.append(c)

    # 3. Mesa de Entradas (summary='Fechas en Mesa de Entradas').
    mesa = soup.find("table", summary=re.compile(r"Mesa de Entradas", re.I))
    if mesa:
        rows = _table_rows(mesa)
        if rows:
            row = rows[0]
            if len(row) >= 1:
                exp.fecha_mesa_entradas = row[0] or None
            if len(row) >= 2:
                exp.fecha_dado_cuenta = row[1] or None
            if len(row) >= 3:
                # El DAE viene mezclado con "Tipo: NORMAL" → tomar solo el primer token.
                dae_raw = row[2]
                exp.numero_dae = dae_raw.split()[0] if dae_raw else None

    # 4. Dir Comisiones (summary='Fechas en Dirección Comisiones').
    dir_com = soup.find("table", summary=re.compile(r"Direcci.n Comisiones", re.I))
    if dir_com:
        rows = _table_rows(dir_com)
        if rows:
            row = rows[0]
            if len(row) >= 1:
                exp.fecha_dir_comisiones = row[0] or None
            if len(row) >= 2:
                exp.fecha_dictamen_mesa = row[1] or None

    # 5. Giros (summary='Giros del Expediente a Comisiones').
    giros_t = soup.find("table", summary=re.compile(r"Giros del Expediente", re.I))
    if giros_t:
        for row in _table_rows(giros_t):
            if not row[0]:
                continue
            # La columna "comisión" trae "DE SALUD ORDEN DE GIRO: 1" — separamos.
            comision_raw = row[0]
            m = re.match(r"^(.+?)\s+ORDEN DE GIRO:\s*\d+\s*$", comision_raw, re.I)
            comision = _clean(m.group(1)) if m else comision_raw
            g = GiroHsn(comision=comision)
            if len(row) >= 2:
                g.fecha_ingreso = row[1] or None
            if len(row) >= 3:
                g.fecha_egreso = row[2] or None
            exp.giros.append(g)

    # 6. PDF: dentro de <div id="textoOriginal">.
    texto_div = soup.find("div", id="textoOriginal")
    if texto_div:
        a = texto_div.find("a", href=True)
        if a:
            href = a["href"]
            exp.texto_pdf_url = href if href.startswith("http") else f"{BASE}{href}"

    exp.parseo_completo = bool(exp.extracto and exp.autores)
    return exp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    # Forzar UTF-8 en stdout (Windows console default es cp1252).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    print(f"Spike HSN -- {len(SAMPLE_EXPEDIENTES)} expedientes via GET /parlamentario/...")
    print(f"User-Agent: {USER_AGENT}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s/req")
    print(f"Cache: {CACHE_DIR}")
    print("-" * 70)

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"}
    resultados: list[ExpedienteHsn] = []

    with httpx.Client(headers=headers) as client:
        for num, anio, origen, tipo in SAMPLE_EXPEDIENTES:
            etiqueta = f"{num}/{anio}/{origen}/{tipo}"
            print(f"\n-> {etiqueta}")
            fetched = fetch_expediente(client, num, anio, origen, tipo)
            if fetched is None:
                print("  [!] no se pudo obtener HTML")
                continue
            html, url = fetched
            print(f"  [OK] {len(html)} bytes")
            exp = parse_hsn(html, num, anio, origen, tipo, url)
            resultados.append(exp)
            print(f"  origen: {exp.origen_full} | tipo: {exp.tipo_full}")
            print(f"  extracto: {(exp.extracto or '-')[:90]}")
            print(f"  autores: {'; '.join(exp.autores) or '-'}")
            print(
                f"  mesa_entr: {exp.fecha_mesa_entradas or '-'} | "
                f"dado_cuenta: {exp.fecha_dado_cuenta or '-'} | "
                f"DAE: {exp.numero_dae or '-'}"
            )
            print(
                f"  dir_comisiones: {exp.fecha_dir_comisiones or '-'} | "
                f"dictamen_mesa: {exp.fecha_dictamen_mesa or '-'}"
            )
            print(f"  giros={len(exp.giros)}: {[g.comision for g in exp.giros]}")
            print(f"  PDF: {exp.texto_pdf_url or '-'}")
            print(f"  parseo_completo: {exp.parseo_completo}")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    out_path = CACHE_DIR / "hsn_resultados.json"
    out_path.write_text(
        json.dumps([asdict(r) for r in resultados], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Guardado: {out_path}")
    completos = sum(1 for r in resultados if r.parseo_completo)
    print(f"Expedientes con parseo completo: {completos}/{len(resultados)}")
    return 0 if completos > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
