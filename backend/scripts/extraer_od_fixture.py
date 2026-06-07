"""Extrae el PDF del temario embebido en el HTML del portal HCDN.

Uso (one-shot para capturar fixture):
    uv run python -m scripts.extraer_od_fixture /tmp/od_3581.html tests/fixtures/od_hcdn/od_3581.pdf
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path


def extraer(html_path: Path, out_pdf: Path) -> None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    # El HTML tiene `abrirPDF("...base64...")` que setea el src del <embed>.
    # El base64 puede tener \/ escapado en el HTML para JS — lo normalizamos.
    m = re.search(r'abrirPDF\("([A-Za-z0-9+/=\\\\]+)"\)', html)
    if not m:
        raise SystemExit("No se encontró la llamada abrirPDF(...) en el HTML")
    b64 = m.group(1).replace("\\/", "/").replace("\\", "")
    pdf = base64.b64decode(b64)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(pdf)
    print(f"PDF guardado: {out_pdf} ({len(pdf)} bytes)")


if __name__ == "__main__":
    extraer(Path(sys.argv[1]), Path(sys.argv[2]))
