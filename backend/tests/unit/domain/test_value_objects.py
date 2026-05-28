"""Tests unitarios de value objects del dominio."""

from __future__ import annotations

import pytest

from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)

pytestmark = pytest.mark.unit


# --- TipoExpediente ----------------------------------------------------------


def test_tipo_from_text_ley() -> None:
    assert TipoExpediente.from_text("Proyecto De Ley") == TipoExpediente.PROYECTO_LEY
    assert TipoExpediente.from_text("LEY") == TipoExpediente.PROYECTO_LEY


def test_tipo_from_text_otros() -> None:
    assert TipoExpediente.from_text("Proyecto De Resolución") == TipoExpediente.PROYECTO_RESOLUCION
    assert (
        TipoExpediente.from_text("Proyecto De Declaración") == TipoExpediente.PROYECTO_DECLARACION
    )
    assert (
        TipoExpediente.from_text("Proyecto De Comunicación") == TipoExpediente.PROYECTO_COMUNICACION
    )
    assert TipoExpediente.from_text("Decreto") == TipoExpediente.DECRETO


def test_tipo_from_text_mensaje_pe() -> None:
    # `from_text` reconoce el marcador "mensaje" para distinguir un mensaje
    # del PE de un proyecto. Para distinción contextual con origen, el
    # parser HCDN usa una heurística más rica (ver `_inferir_tipo`).
    assert TipoExpediente.from_text("Mensaje") == TipoExpediente.MENSAJE_PE
    assert TipoExpediente.from_text("Mensaje del Poder Ejecutivo") == TipoExpediente.MENSAJE_PE
    assert TipoExpediente.from_text("MENSAJE N° 1/2024") == TipoExpediente.MENSAJE_PE


def test_tipo_from_text_desconocido_cae_a_otro() -> None:
    assert TipoExpediente.from_text("algo raro") == TipoExpediente.OTRO


# --- OrigenExpediente --------------------------------------------------------


def test_origen_from_code_validos() -> None:
    assert OrigenExpediente.from_code("D") == OrigenExpediente.DIPUTADO
    assert OrigenExpediente.from_code("s") == OrigenExpediente.SENADOR
    assert OrigenExpediente.from_code(" PE ") == OrigenExpediente.EJECUTIVO
    assert OrigenExpediente.from_code("JGM") == OrigenExpediente.JEFATURA_GABINETE


def test_origen_from_code_revision_diputados() -> None:
    # Amendment 1 ADR 0002: CD se mapea a REVISION_DIPUTADOS (antes caía a OTRO).
    assert OrigenExpediente.from_code("CD") == OrigenExpediente.REVISION_DIPUTADOS


def test_origen_from_code_revision_senado() -> None:
    assert OrigenExpediente.from_code("CS") == OrigenExpediente.REVISION_SENADO


def test_origen_from_code_particular() -> None:
    assert OrigenExpediente.from_code("P") == OrigenExpediente.PARTICULAR


def test_origen_from_code_oficial_varios() -> None:
    assert OrigenExpediente.from_code("OV") == OrigenExpediente.OFICIAL_VARIOS


def test_origen_from_code_invalido_cae_a_otro() -> None:
    # Códigos que no existen en el enum deben caer a OTRO.
    assert OrigenExpediente.from_code("ZZZ") == OrigenExpediente.OTRO
    assert OrigenExpediente.from_code("???") == OrigenExpediente.OTRO


# --- NumeroExpediente: parse / format ----------------------------------------


def test_numero_parse_hcdn_estandar() -> None:
    n = NumeroExpediente.parse_hcdn("1497-D-2024")
    assert n.numero == 1497
    assert n.origen == OrigenExpediente.DIPUTADO
    assert n.anio == 2024
    assert n.camara == Camara.HCDN


def test_numero_parse_hcdn_con_espacios() -> None:
    n = NumeroExpediente.parse_hcdn("  4330 - D - 2021 ")
    assert n.numero == 4330
    assert n.anio == 2021


def test_numero_parse_hcdn_pe() -> None:
    n = NumeroExpediente.parse_hcdn("0001-PE-2024")
    assert n.origen == OrigenExpediente.EJECUTIVO


def test_numero_parse_hcdn_invalido() -> None:
    with pytest.raises(ValueError, match="Formato HCDN inválido"):
        NumeroExpediente.parse_hcdn("no-es-un-numero")


def test_numero_parse_hsn_estandar() -> None:
    n = NumeroExpediente.parse_hsn("239/24")
    assert n.numero == 239
    assert n.anio == 2024
    assert n.camara == Camara.HSN
    assert n.origen == OrigenExpediente.SENADOR


def test_numero_parse_hsn_con_origen_explicito() -> None:
    n = NumeroExpediente.parse_hsn("1/24", origen=OrigenExpediente.OTRO)
    assert n.origen == OrigenExpediente.OTRO


def test_numero_parse_hsn_anio_historico() -> None:
    # YY=99 → 1999, YY=24 → 2024.
    assert NumeroExpediente.parse_hsn("100/99").anio == 1999
    assert NumeroExpediente.parse_hsn("100/24").anio == 2024


def test_numero_parse_hsn_invalido() -> None:
    with pytest.raises(ValueError, match="Formato HSN inválido"):
        NumeroExpediente.parse_hsn("239-S-24")  # estilo HCDN, no HSN


def test_numero_format_hcdn() -> None:
    n = NumeroExpediente(numero=1, origen=OrigenExpediente.DIPUTADO, anio=2024, camara=Camara.HCDN)
    assert n.format_hcdn() == "0001-D-2024"


def test_numero_format_hsn() -> None:
    n = NumeroExpediente(numero=239, origen=OrigenExpediente.SENADOR, anio=2024, camara=Camara.HSN)
    assert n.format_hsn() == "239/24"


def test_numero_str_segun_camara() -> None:
    nh = NumeroExpediente(
        numero=1497, origen=OrigenExpediente.DIPUTADO, anio=2024, camara=Camara.HCDN
    )
    assert str(nh) == "1497-D-2024"
    ns = NumeroExpediente(numero=239, origen=OrigenExpediente.SENADOR, anio=2024, camara=Camara.HSN)
    assert str(ns) == "239/24"


def test_numero_invariantes() -> None:
    with pytest.raises(ValueError, match="positivo"):
        NumeroExpediente(numero=0, origen=OrigenExpediente.DIPUTADO, anio=2024, camara=Camara.HCDN)
    with pytest.raises(ValueError, match="rango"):
        NumeroExpediente(numero=1, origen=OrigenExpediente.DIPUTADO, anio=1900, camara=Camara.HCDN)


def test_numero_es_inmutable() -> None:
    n = NumeroExpediente.parse_hcdn("1-D-2024")
    with pytest.raises((AttributeError, TypeError)):
        n.numero = 2  # type: ignore[misc]


# --- EstadoExpediente --------------------------------------------------------


def test_estado_default_desconocido() -> None:
    # Default que usaremos para expedientes sin estado inferido.
    assert EstadoExpediente.DESCONOCIDO.value == "desconocido"


def test_estado_media_sancion_valores_existen() -> None:
    # Amendment 1 ADR 0002: APROBADO_PARCIAL se desdobló en dos valores que
    # indican en qué cámara hay media sanción. Siglas (hcdn/hsn) por
    # consistencia con Camara.
    assert EstadoExpediente.MEDIA_SANCION_HCDN.value == "media_sancion_hcdn"
    assert EstadoExpediente.MEDIA_SANCION_HSN.value == "media_sancion_hsn"
