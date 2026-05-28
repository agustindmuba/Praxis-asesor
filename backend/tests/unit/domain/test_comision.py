"""Tests unitarios de `Comision` y `TipoComision`."""

from __future__ import annotations

import pytest

from praxis.domain import Camara, Comision, TipoComision

pytestmark = pytest.mark.unit


# --- TipoComision.from_text -------------------------------------------------


def test_tipo_from_text_unicameral_permanente() -> None:
    assert TipoComision.from_text("UNICAMERAL PERMANENTE") == TipoComision.PERMANENTE


def test_tipo_from_text_bicameral_permanente() -> None:
    assert TipoComision.from_text("BICAMERAL PERMANENTE") == TipoComision.BICAMERAL_PERMANENTE


def test_tipo_from_text_bicameral_especial() -> None:
    assert TipoComision.from_text("BICAMERAL ESPECIAL") == TipoComision.BICAMERAL_ESPECIAL


def test_tipo_from_text_solo_especial() -> None:
    assert TipoComision.from_text("ESPECIAL") == TipoComision.ESPECIAL


def test_tipo_from_text_solo_permanente() -> None:
    assert TipoComision.from_text("PERMANENTE") == TipoComision.PERMANENTE


def test_tipo_from_text_solo_bicameral_default_permanente() -> None:
    """Sin palabra "ESPECIAL" ni "PERMANENTE" pero con "BICAMERAL"."""
    assert TipoComision.from_text("BICAMERAL") == TipoComision.BICAMERAL_PERMANENTE


def test_tipo_from_text_desconocido_cae_a_otro() -> None:
    assert TipoComision.from_text("algo raro") == TipoComision.OTRO


def test_tipo_from_text_case_insensitive() -> None:
    assert TipoComision.from_text("bicameral especial") == TipoComision.BICAMERAL_ESPECIAL


# --- Comision ----------------------------------------------------------------


def test_comision_minima() -> None:
    c = Comision(
        nombre="ASUNTOS CONSTITUCIONALES",
        tipo=TipoComision.PERMANENTE,
        camara=Camara.HCDN,
    )
    assert c.slug is None
    assert c.categoria_tematica is None


def test_comision_con_slug_y_categoria() -> None:
    c = Comision(
        nombre="ASUNTOS CONSTITUCIONALES",
        tipo=TipoComision.PERMANENTE,
        camara=Camara.HCDN,
        slug="caconstitucionales",
        categoria_tematica="Justicia, Seguridad y Derechos",
    )
    assert c.slug == "caconstitucionales"


def test_comision_nombre_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="nombre"):
        Comision(nombre="  ", tipo=TipoComision.PERMANENTE, camara=Camara.HCDN)


def test_comision_es_inmutable() -> None:
    c = Comision(nombre="X", tipo=TipoComision.PERMANENTE, camara=Camara.HCDN)
    with pytest.raises((AttributeError, TypeError)):
        c.nombre = "Y"  # type: ignore[misc]
