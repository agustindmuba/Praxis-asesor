#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27",
#     "beautifulsoup4>=4.12",
#     "lxml>=5.0",
# ]
# ///
"""Spike de exploración del portal HCDN (Cámara de Diputados).

Hallazgo del spike: NO hay una URL canónica del tipo /proyectos/<exp>.html.
Las URLs `proyecto.jsp?exp=...` están deprecadas (404), y las versiones
con slug de diputado (`/diputados/<slug>/proyecto.html?exp=...`) requieren
conocer el slug.

La vía limpia es **POST a /proyectos/resultado.html** con el número descompuesto
en `strNumExp` (NNNN), `strNumExpOrig` (D|S|PE|...), `strNumExpAnio` (YYYY).
El response trae la ficha completa: extracto, sumario, firmantes, comisiones,
trámite, link al PDF original.

Uso:
    uv run spike/hcdn/explore.py

Salida:
    spike/_cache/hcdn_<exp>.html        (HTML crudo)
    spike/_cache/hcdn_resultados.json   (parsed)
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"
RATE_LIMIT_SECONDS = 1.0  # 1 req/seg por dominio (CLAUDE.md §7).

CACHE_DIR = Path(__file__).parent.parent / "_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://www.diputados.gob.ar"
RESULTADO_URL = f"{BASE}/proyectos/resultado.html"

# Lista corta de expedientes para validar el spike. Mezcla años y tipos.
SAMPLE_EXPEDIENTES = [
    ("1497", "D", "2024"),  # Propato — Datos Personales
    ("0001", "D", "2024"),  # primer expediente del año
    ("0001", "PE", "2024"),  # un proyecto del Ejecutivo
]


# ---------------------------------------------------------------------------
# Modelo del spike
# ---------------------------------------------------------------------------


@dataclass
class Firmante:
    nombre: str
    distrito: str
    bloque: str


@dataclass
class Giro:
    comision: str


@dataclass
class TramiteEvento:
    camara: str
    movimiento: str
    fecha: str
    resultado: str


@dataclass
class ExpedienteHcdn:
    numero: str  # ej "1497-D-2024"
    extracto: str | None = None
    sumario: str | None = None
    firmantes: list[Firmante] = field(default_factory=list)
    giros: list[Giro] = field(default_factory=list)
    tramite: list[TramiteEvento] = field(default_factory=list)
    pdf_url: str | None = None
    parseo_completo: bool = False


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------


def _cache_path(numero: str) -> Path:
    safe = numero.replace("/", "_")
    return CACHE_DIR / f"hcdn_{safe}.html"


def fetch_resultado(client: httpx.Client, num: str, orig: str, anio: str) -> str | None:
    """POST a /proyectos/resultado.html con el expediente descompuesto."""
    numero = f"{num}-{orig}-{anio}"
    cache = _cache_path(numero)
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")

    print(f"  POST {RESULTADO_URL} (num={num} orig={orig} anio={anio})")
    time.sleep(RATE_LIMIT_SECONDS)
    data = {
        "zezion": "true",
        "strTipo": "",
        "strNumExp": num,
        "strNumExpOrig": orig,
        "strNumExpAnio": anio,
        "strCamIni": "",
        "strFirmante": "",
        "strTipoFirmante": "",
        "strComision": "",
        "strFechaInicio": "",
        "strFechaFin": "",
        "strPalabras": "",
        "strMostrarTramites": "on",
        "strMostrarDictamenes": "on",
        "strMostrarFirmantes": "on",
        "strMostrarComisiones": "on",
        "strCantPagina": "20",
    }
    try:
        r = client.post(RESULTADO_URL, data=data, timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        print(f"    error: {exc}")
        return None

    if r.status_code != 200:
        print(f"    status: {r.status_code}")
        return None

    if "no se encontr" in r.text.lower() or len(r.text) < 5000:
        print(f"    payload sospechoso (len={len(r.text)})")
        return None

    cache.write_text(r.text, encoding="utf-8")
    return r.text


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------


def _norm(text: str | None) -> str | None:
    if text is None:
        return None
    return " ".join(text.split()) or None


def parse_resultado(html: str, numero: str) -> ExpedienteHcdn:
    soup = BeautifulSoup(html, "lxml")
    exp = ExpedienteHcdn(numero=numero)

    # 1. Extracto: <div class="dp-texto">.
    dp = soup.find("div", class_="dp-texto")
    if isinstance(dp, Tag):
        exp.extracto = _norm(dp.get_text(" "))

    # 2. Sumario: <div id="sumarioNNNNNN"> (oculto, alimenta un modal).
    sumario_div = soup.find("div", id=re.compile(r"^sumario\d+"))
    if isinstance(sumario_div, Tag):
        exp.sumario = _norm(sumario_div.get_text(" "))

    # 3. Firmantes: tabla con headers FIRMANTE / DISTRITO / BLOQUE.
    exp.firmantes = _parse_table_with_headers(
        soup,
        required=["firmante", "distrito", "bloque"],
        builder=lambda cells: Firmante(nombre=cells[0], distrito=cells[1], bloque=cells[2]),
        min_cols=3,
    )

    # 4. Giros: tabla con header COMISIÓN (puede estar sola o con más cols).
    exp.giros = _parse_table_with_headers(
        soup,
        required=["comisi"],
        builder=lambda cells: Giro(comision=cells[0]),
        min_cols=1,
    )

    # 5. Trámite: tabla con CÁMARA / MOVIMIENTO / FECHA / RESULTADO.
    exp.tramite = _parse_table_with_headers(
        soup,
        required=["mara", "movimi", "fecha", "resultado"],
        builder=lambda cells: TramiteEvento(
            camara=cells[0], movimiento=cells[1], fecha=cells[2], resultado=cells[3]
        ),
        min_cols=4,
    )

    # 6. PDF: link a www4.hcdn.gob.ar terminando en .pdf y con el número.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf") and numero.replace("/", "-") in href:
            exp.pdf_url = href if href.startswith("http") else f"{BASE}{href}"
            break

    exp.parseo_completo = bool(exp.extracto and exp.firmantes and exp.tramite)
    return exp


def _parse_table_with_headers(
    soup: BeautifulSoup,
    required: list[str],
    builder,
    min_cols: int,
) -> list:
    """Encuentra la primera tabla cuyo set de headers (lowercased) contenga
    TODOS los substrings de `required`, y construye una lista de objetos."""
    results = []
    for table in soup.find_all("table"):
        headers = [(_norm(th.get_text()) or "").lower() for th in table.find_all("th")]
        if not headers:
            continue
        if all(any(req in h for h in headers) for req in required):
            for row in table.find_all("tr"):
                cells = [_norm(td.get_text()) or "" for td in row.find_all("td")]
                if len(cells) >= min_cols:
                    results.append(builder(cells))
            if results:
                return results
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print(f"Spike HCDN -- {len(SAMPLE_EXPEDIENTES)} expedientes via POST /proyectos/resultado.html")
    print(f"User-Agent: {USER_AGENT}")
    print(f"Rate limit: {RATE_LIMIT_SECONDS}s/req")
    print(f"Cache: {CACHE_DIR}")
    print("-" * 70)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "es-AR,es;q=0.9",
        "Referer": f"{BASE}/proyectos/",
    }
    resultados: list[ExpedienteHcdn] = []

    with httpx.Client(headers=headers) as client:
        for num, orig, anio in SAMPLE_EXPEDIENTES:
            numero = f"{num}-{orig}-{anio}"
            print(f"\n-> {numero}")
            html = fetch_resultado(client, num, orig, anio)
            if html is None:
                print("  [!] no se pudo obtener HTML")
                continue
            print(f"  [OK] {len(html)} bytes")
            exp = parse_resultado(html, numero)
            resultados.append(exp)
            print(f"  extracto: {(exp.extracto or '-')[:80]}")
            print(f"  sumario:  {(exp.sumario or '-')[:80]}")
            print(
                f"  firmantes={len(exp.firmantes)} | "
                f"giros={len(exp.giros)} | "
                f"tramite={len(exp.tramite)}"
            )
            print(f"  PDF: {exp.pdf_url or '-'}")
            print(f"  parseo_completo: {exp.parseo_completo}")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    out_path = CACHE_DIR / "hcdn_resultados.json"
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
