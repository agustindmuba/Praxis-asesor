"""Tests de contrato del parser HCDN.

Usan HTML real capturado del portal (fixtures en `tests/fixtures/hcdn/`).
NO hacen HTTP. Si el portal HCDN cambia su estructura y la nueva captura
ya no produce el output esperado, estos tests fallan y avisan que hay
que actualizar el parser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.domain import (
    Camara,
    NumeroExpediente,
    TipoExpediente,
)
from praxis.infrastructure.scrapers.hcdn.parser import parse_resultado_hcdn

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hcdn"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


# --- 1497-D-2024 (Propato, Datos Personales) ---------------------------------


def test_parser_1497_d_2024_extracto_y_sumario() -> None:
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)

    assert expediente.numero == numero
    assert expediente.camara == Camara.HCDN
    assert "PROTECCION DE DATOS PERSONALES" in (expediente.titulo or "")
    assert expediente.sumario is not None
    assert "LEY 25326" in expediente.sumario


def test_parser_1497_d_2024_firmantes() -> None:
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)

    assert len(expediente.firmantes) == 1
    f = expediente.firmantes[0]
    assert "PROPATO" in f.nombre
    assert f.distrito == "BUENOS AIRES"
    assert f.bloque is not None and "UNI" in f.bloque  # "UNIÓN POR LA PATRIA"
    assert f.orden == 1


def test_parser_1497_d_2024_giros() -> None:
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)

    assert len(expediente.giros) == 1
    assert "ASUNTOS CONSTITUCIONALES" in expediente.giros[0].comision


def test_parser_1497_d_2024_pdf_url() -> None:
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)

    assert expediente.texto_url is not None
    assert "1497-D-2024.pdf" in expediente.texto_url
    assert "www4.hcdn.gob.ar" in expediente.texto_url


def test_parser_1497_d_2024_tramite_no_vacio() -> None:
    """El expediente tiene al menos un evento (adhesiones)."""
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)

    assert len(expediente.tramite) >= 1
    for ev in expediente.tramite:
        assert ev.evento  # no vacío
        assert ev.fuente == "scraper:hcdn"


# --- 0001-D-2024 (Educación) -------------------------------------------------


def test_parser_0001_d_2024_dos_firmantes_y_tres_giros() -> None:
    numero = NumeroExpediente.parse_hcdn("0001-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_0001-D-2024.html"), numero)

    assert len(expediente.firmantes) == 2
    assert len(expediente.giros) == 3
    # Confirmar que el orden de firmantes está bien (autor principal primero).
    assert expediente.firmantes[0].orden == 1
    assert expediente.firmantes[1].orden == 2


def test_parser_0001_d_2024_tramite_puede_estar_vacio() -> None:
    """Para expedientes recién ingresados, trámite puede ser []. No debe fallar."""
    numero = NumeroExpediente.parse_hcdn("0001-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_0001-D-2024.html"), numero)
    # En este expediente del spike, trámite estaba vacío.
    # Si el portal lo actualiza, esto puede cambiar — assertion laxa.
    assert isinstance(expediente.tramite, list)


# --- 0001-PE-2024 (Mensaje del Ejecutivo) -----------------------------------


def test_parser_0001_pe_2024_origen_ejecutivo() -> None:
    numero = NumeroExpediente.parse_hcdn("0001-PE-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_0001-PE-2024.html"), numero)

    assert expediente.numero.origen.value == "PE"


def test_parser_0001_pe_2024_cuatro_firmantes_y_dos_giros() -> None:
    numero = NumeroExpediente.parse_hcdn("0001-PE-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_0001-PE-2024.html"), numero)

    assert len(expediente.firmantes) == 4
    assert len(expediente.giros) == 2


def test_parser_0001_pe_2024_tramite_con_eventos() -> None:
    numero = NumeroExpediente.parse_hcdn("0001-PE-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_0001-PE-2024.html"), numero)

    # En el spike capturamos 6 eventos en este expediente; mantenemos la
    # aserción laxa por si el portal agrega más en el futuro.
    assert len(expediente.tramite) >= 6
    # Al menos un evento debería tener fecha parseada (no todos).
    eventos_con_fecha = [t for t in expediente.tramite if t.fecha is not None]
    assert len(eventos_con_fecha) >= 1
    # Y todos deben tener cámara plausible (HCDN o HSN).
    for ev in expediente.tramite:
        assert ev.camara in (Camara.HCDN, Camara.HSN)


# --- Sanity: el parser rechaza HTML obviamente inválido ----------------------


def test_parser_html_invalido_lanza() -> None:
    """Si el HTML no tiene ninguna marca de ficha, debe levantar ValueError."""
    numero = NumeroExpediente.parse_hcdn("1-D-2024")
    with pytest.raises(ValueError, match="ficha"):
        parse_resultado_hcdn("<html><body>nada</body></html>", numero)


# --- Sanity: tipo inferido ---------------------------------------------------


def test_parser_tipo_default_ley_si_no_hay_marcador() -> None:
    numero = NumeroExpediente.parse_hcdn("1497-D-2024")
    expediente = parse_resultado_hcdn(_load("hcdn_1497-D-2024.html"), numero)
    # Sin marcador explícito de "declaración" o "resolución" → default LEY.
    assert expediente.tipo == TipoExpediente.LEY
