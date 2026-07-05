"""Descarga y extracción de texto del PDF de citación de comisión (feat-61.4.B.2).

El PDF contiene el orden del día detallado: expedientes, oradores invitados,
puntos de debate. Pdfplumber lo extrae como texto plano.
"""

from __future__ import annotations

import io
import re

import httpx
import pdfplumber
import structlog

log = structlog.get_logger(__name__)

DEFAULT_USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"
MAX_PDF_BYTES = 8 * 1024 * 1024  # 8 MB cap por PDF
MAX_TEXTO_CHARS = 12_000  # cap para no romper context window LLM


async def descargar_y_extraer(url: str) -> str | None:
    """Baja el PDF y devuelve su texto plano. None si falla."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            log.warning(
                "citacion_pdf.http_no_200", url=url, code=resp.status_code,
            )
            return None
        if len(resp.content) > MAX_PDF_BYTES:
            log.warning(
                "citacion_pdf.demasiado_grande",
                url=url,
                bytes=len(resp.content),
            )
            return None
        return _extraer_texto(resp.content)
    except Exception as exc:
        log.warning("citacion_pdf.error", url=url, error=str(exc))
        return None


def _extraer_texto(pdf_bytes: bytes) -> str:
    """Abre con pdfplumber, junta texto de todas las páginas, colapsa
    espacios. Trunca a MAX_TEXTO_CHARS."""
    paginas: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            t = p.extract_text() or ""
            paginas.append(t)
    raw = "\n".join(paginas)
    # Colapsa whitespace y elimina runs de líneas vacías.
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()[:MAX_TEXTO_CHARS]


# Regex utilitarios para parsing dirigido por LLM downstream.
EXPEDIENTE_RE = re.compile(
    r"\b(\d{1,4})[-\s]?([A-Z])[-\s]?(\d{4})\b",
)
"""Captura nro-origen-año en notación HCDN. Ej: "1234-D-2025"."""


def extraer_expedientes_citados(texto: str) -> list[str]:
    """Lista únicos en formato canónico ej. ['1234-D-2025', ...]."""
    vistos: dict[str, None] = {}
    for m in EXPEDIENTE_RE.finditer(texto):
        clave = f"{int(m.group(1))}-{m.group(2)}-{m.group(3)}"
        vistos.setdefault(clave, None)
    return list(vistos.keys())[:30]  # cap defensivo
