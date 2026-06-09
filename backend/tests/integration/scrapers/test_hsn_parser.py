"""Tests de contrato del parser HSN.

Usan HTML real capturado del portal (fixtures en `tests/fixtures/hsn/`).
NO hacen HTTP. Si el portal HSN cambia su estructura y el output esperado
no se reproduce, estos tests fallan y avisan que hay que actualizar el parser.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from praxis.domain import (
    Camara,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.infrastructure.scrapers.hsn.parser import parse_expediente_hsn

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hsn"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


# --- 239/24/S/PL — Sapag, transgénicos ---------------------------------------


def _numero_239() -> NumeroExpediente:
    return NumeroExpediente(
        numero=239,
        origen=OrigenExpediente.SENADOR,
        anio=2024,
        camara=Camara.HSN,
    )


def test_parser_239_24_extracto_y_titulo() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_239_24_S_PL.html"), _numero_239(), TipoExpediente.PROYECTO_LEY
    )
    assert "SAPAG" in (expediente.titulo or "")
    assert "TRANSGENICOS" in (expediente.titulo or "")


def test_parser_239_24_autores_presentes() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_239_24_S_PL.html"), _numero_239(), TipoExpediente.PROYECTO_LEY
    )
    assert len(expediente.firmantes) >= 1
    nombres = " ".join(f.nombre for f in expediente.firmantes)
    assert "Sapag" in nombres


def test_parser_239_24_giros_con_fechas() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_239_24_S_PL.html"), _numero_239(), TipoExpediente.PROYECTO_LEY
    )
    assert len(expediente.giros) == 2
    nombres_comisiones = [g.comision for g in expediente.giros]
    assert "DE SALUD" in nombres_comisiones
    assert "DE INDUSTRIA Y COMERCIO" in nombres_comisiones
    # Las fechas in/out se parsean (al menos las de ingreso).
    for g in expediente.giros:
        assert g.fecha_ingreso == date(2024, 3, 21)


def test_parser_239_24_pdf_url() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_239_24_S_PL.html"), _numero_239(), TipoExpediente.PROYECTO_LEY
    )
    assert expediente.texto_url is not None
    assert "downloadPdf" in expediente.texto_url
    assert "senado.gob.ar" in expediente.texto_url


def test_parser_239_24_fecha_ingreso_y_tramite_derivado() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_239_24_S_PL.html"), _numero_239(), TipoExpediente.PROYECTO_LEY
    )
    assert expediente.fecha_ingreso == date(2024, 3, 12)
    # Tramite derivado: al menos mesa de entradas, dir comisiones, giros, dado cuenta.
    eventos = [ev.evento for ev in expediente.tramite]
    assert "INGRESO A MESA DE ENTRADAS" in eventos
    assert "INGRESO A DIRECCION GENERAL DE COMISIONES" in eventos
    assert eventos.count("GIRO A COMISION") == 2  # uno por giro
    assert "DADO CUENTA EN SESION" in eventos
    # Orden cronológico.
    fechas = [ev.fecha for ev in expediente.tramite if ev.fecha is not None]
    assert fechas == sorted(fechas)
    # Fuente.
    for ev in expediente.tramite:
        assert ev.fuente == "derived:hsn-stages"
        assert ev.camara == Camara.HSN


# --- 1/24/CD/PL — Revisión Diputados (sin autores en HSN) -------------------


def _numero_1_cd() -> NumeroExpediente:
    return NumeroExpediente(
        numero=1,
        origen=OrigenExpediente.REVISION_DIPUTADOS,
        anio=2024,
        camara=Camara.HSN,
    )


def test_parser_1_24_cd_sin_autores_en_hsn() -> None:
    """Expedientes CD-origen no tienen autores en HSN — los autores viven en HCDN."""
    expediente = parse_expediente_hsn(
        _load("hsn_1_24_CD_PL.html"), _numero_1_cd(), TipoExpediente.PROYECTO_LEY
    )
    assert expediente.firmantes == []


def test_parser_1_24_cd_giros_y_extracto() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_1_24_CD_PL.html"), _numero_1_cd(), TipoExpediente.PROYECTO_LEY
    )
    assert "BASES Y PUNTOS DE PARTIDA" in (expediente.titulo or "")
    assert len(expediente.giros) == 3
    nombres = [g.comision for g in expediente.giros]
    assert any("LEGISLACI" in n for n in nombres)  # "DE LEGISLACIÓN GENERAL"


# --- 1497/20/S/PC — Histórico 2020 ------------------------------------------


def _numero_1497() -> NumeroExpediente:
    return NumeroExpediente(
        numero=1497,
        origen=OrigenExpediente.SENADOR,
        anio=2020,
        camara=Camara.HSN,
    )


def test_parser_1497_20_extracto_y_autores() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_1497_20_S_PC.html"),
        _numero_1497(),
        TipoExpediente.PROYECTO_COMUNICACION,
    )
    titulo = expediente.titulo or ""
    assert "BLANCO" in titulo or "BASUALDO" in titulo
    # Dos autores en este expediente.
    assert len(expediente.firmantes) == 2


def test_parser_1497_20_fecha_ingreso_historica() -> None:
    expediente = parse_expediente_hsn(
        _load("hsn_1497_20_S_PC.html"),
        _numero_1497(),
        TipoExpediente.PROYECTO_COMUNICACION,
    )
    assert expediente.fecha_ingreso == date(2020, 7, 14)


# --- Sanity: HTML inválido --------------------------------------------------


def test_parser_html_invalido_lanza() -> None:
    """HTML sin tabla cabecera → ValueError."""
    with pytest.raises(ValueError, match="ficha"):
        parse_expediente_hsn(
            "<html><body>nada</body></html>",
            _numero_239(),
            TipoExpediente.PROYECTO_LEY,
        )


# --- Anti-fantasma: cabecera presente pero TODO vacío -----------------------
# Regresión feat-49.4.fix. El portal HSN devuelve HTTP 200 con cabecera
# vacía para N° que no existen (no devuelve 404). El parser debe detectarlo
# y lanzar ValueError para que el scraper lo trate como ExpedienteNoEncontrado.
# Sin este check, el seed acumula ~75% de basura (35k/47k para HSN/S/2024).


def _numero_fantasma() -> NumeroExpediente:
    return NumeroExpediente(
        numero=100759,
        origen=OrigenExpediente.SENADOR,
        anio=2024,
        camara=Camara.HSN,
    )


def test_parser_expediente_fantasma_lanza() -> None:
    """N° 100759/24 no existe — el portal devuelve cabecera vacía.

    Antes del fix, este HTML se parseaba como expediente válido con
    titulo='Expediente 100759-S-2024', sin firmantes, sin trámite —
    basura que ensucia la búsqueda.
    """
    with pytest.raises(ValueError, match="no existe"):
        parse_expediente_hsn(
            _load("hsn_100759_24_S_PL_vacio.html"),
            _numero_fantasma(),
            TipoExpediente.PROYECTO_LEY,
        )
