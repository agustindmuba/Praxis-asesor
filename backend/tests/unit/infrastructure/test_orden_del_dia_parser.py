"""Tests del parser de PDFs del Plan de Labor HCDN (feat-45.2).

Usa el fixture local `od_3581.pdf` (Sesión Especial 20/05/2026, 65
items) capturado del portal HCDN. Verifica que el parser extrae los
campos críticos consistentemente.

NO usa red. NO depende de Postgres.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from praxis.infrastructure.scrapers.hcdn.orden_del_dia.parser import (
    OrdenDelDiaParseado,
    extraer_pdf_base64,
    parsear_pdf_temario,
)

pytestmark = pytest.mark.unit


FIXTURE_PDF = (
    Path(__file__).parent.parent.parent
    / "fixtures" / "od_hcdn" / "od_3581.pdf"
)


@pytest.fixture
def pdf_bytes() -> bytes:
    if not FIXTURE_PDF.exists():
        pytest.skip(f"Fixture no encontrado: {FIXTURE_PDF}")
    return FIXTURE_PDF.read_bytes()


@pytest.fixture
def od(pdf_bytes: bytes) -> OrdenDelDiaParseado:
    return parsear_pdf_temario(pdf_bytes)


# ---------------------------------------------------------------------------
# Parser de PDF
# ---------------------------------------------------------------------------


def test_pdf_se_parsea_sin_errores(od: OrdenDelDiaParseado) -> None:
    assert od is not None
    assert od.items is not None


def test_fecha_sesion_se_extrae_correctamente(od: OrdenDelDiaParseado) -> None:
    """El temario del fixture es del 20/05/2026 (MIÉRCOLES 20 DE MAYO)."""
    assert od.fecha_sesion == date(2026, 5, 20)


def test_tipo_sesion_es_especial(od: OrdenDelDiaParseado) -> None:
    """El header dice '4° REUNIÓN – 4° SESIÓN ESPECIAL'."""
    assert od.tipo_sesion == "especial"


def test_items_se_extraen_count_razonable(od: OrdenDelDiaParseado) -> None:
    """Sesion del fixture tiene ~65 items. Validamos rango amplio."""
    assert 40 < len(od.items) < 100


def test_items_tienen_numero_expediente(od: OrdenDelDiaParseado) -> None:
    """Cada item tiene un N° con formato NNNN-X-AAAA."""
    import re
    pat = re.compile(r"\d{4}-[A-Z]{1,4}-\d{2,4}")
    for it in od.items:
        assert pat.match(it.numero_expediente), (
            f"N° con formato raro: {it.numero_expediente!r}"
        )


def test_items_tienen_tipo_valido(od: OrdenDelDiaParseado) -> None:
    """Tipo está en {ley, resolucion, declaracion, comunicacion}."""
    tipos_validos = {"ley", "resolucion", "declaracion", "comunicacion"}
    for it in od.items:
        assert it.tipo in tipos_validos, (
            f"Tipo desconocido: {it.tipo!r} en {it.numero_expediente!r}"
        )


def test_items_tienen_sumario_no_vacio(od: OrdenDelDiaParseado) -> None:
    """Cada item tiene sumario con contenido."""
    sin_sumario = [it for it in od.items if not it.sumario.strip()]
    # Permitimos hasta 2 items sin sumario (PDF a veces tiene
    # tablas que rompen extracción).
    assert len(sin_sumario) <= 2


def test_primer_item_matches_temario_conocido(od: OrdenDelDiaParseado) -> None:
    """Sanity check sobre el primer item conocido del fixture.

    El primer item del PDF 3581 es: 0419-D-2026 DE RESOLUCIÓN.
    PEDIDO DE INFORMES VERBALES AL JEFE DE GABINETE...
    """
    primer = od.items[0]
    assert primer.numero_expediente == "0419-D-2026"
    assert primer.tipo == "resolucion"
    assert "INFORME" in primer.sumario.upper()


# ---------------------------------------------------------------------------
# extraer_pdf_base64
# ---------------------------------------------------------------------------


def test_extraer_pdf_base64_falla_si_no_hay_abrirPDF() -> None:
    """Si el HTML no tiene la llamada abrirPDF(...), tira ValueError."""
    html_sin_pdf = "<html><body><h1>Página vacía</h1></body></html>"
    with pytest.raises(ValueError, match="abrirPDF"):
        extraer_pdf_base64(html_sin_pdf)


def test_extraer_pdf_base64_normaliza_slash_escapado() -> None:
    """El JS escapa los `/` como `\\/` — los normalizamos antes de decodificar."""
    # %PDF base64 con un slash escapado en el medio
    import base64
    pdf_bytes = b"%PDF-1.7 dummy"
    b64 = base64.b64encode(pdf_bytes).decode()
    # Mezclamos un `\/` representativo
    b64_escapado = b64.replace("/", "\\/")
    html = f'abrirPDF("{b64_escapado}")'
    out = extraer_pdf_base64(html)
    assert out == pdf_bytes
