"""Tests unitarios de `Legislador` y `Bloque`."""

from __future__ import annotations

from datetime import date

import pytest

from praxis.domain import Bloque, Camara, Legislador

pytestmark = pytest.mark.unit


def _bloque(camara: Camara = Camara.HCDN) -> Bloque:
    return Bloque(nombre="UNIÓN POR LA PATRIA", camara=camara)


def _legislador(camara: Camara = Camara.HCDN) -> Legislador:
    return Legislador(
        slug="haguirre",
        apellido="Aguirre",
        nombre="Hilda",
        camara=camara,
        distrito="LA RIOJA",
        bloque=_bloque(camara),
        periodo_mandato="2023-2027",
        fecha_inicio_mandato=date(2023, 12, 10),
        fecha_fin_mandato=date(2027, 12, 9),
    )


# --- Bloque ------------------------------------------------------------------


def test_bloque_minimo() -> None:
    b = _bloque()
    assert b.nombre == "UNIÓN POR LA PATRIA"
    assert b.camara == Camara.HCDN


def test_bloque_nombre_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="nombre"):
        Bloque(nombre=" ", camara=Camara.HCDN)


def test_bloque_es_inmutable() -> None:
    b = _bloque()
    with pytest.raises((AttributeError, TypeError)):
        b.nombre = "OTRO"  # type: ignore[misc]


# --- Legislador --------------------------------------------------------------


def test_legislador_minimo() -> None:
    leg = _legislador()
    assert leg.slug == "haguirre"
    assert leg.apellido == "Aguirre"
    assert leg.camara == Camara.HCDN
    assert leg.bloque.nombre == "UNIÓN POR LA PATRIA"
    # Campos opcionales default-None.
    assert leg.fecha_nacimiento is None
    assert leg.edad_anios is None


def test_legislador_nombre_completo() -> None:
    leg = _legislador()
    assert leg.nombre_completo == "Aguirre, Hilda"


def test_legislador_slug_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="slug"):
        Legislador(
            slug="  ",
            apellido="X",
            nombre="Y",
            camara=Camara.HCDN,
            distrito="D",
            bloque=_bloque(),
            periodo_mandato="2023-2027",
            fecha_inicio_mandato=date(2023, 12, 10),
            fecha_fin_mandato=date(2027, 12, 9),
        )


def test_legislador_apellido_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="apellido"):
        Legislador(
            slug="x",
            apellido=" ",
            nombre="Y",
            camara=Camara.HCDN,
            distrito="D",
            bloque=_bloque(),
            periodo_mandato="2023-2027",
            fecha_inicio_mandato=date(2023, 12, 10),
            fecha_fin_mandato=date(2027, 12, 9),
        )


def test_legislador_fechas_invertidas_lanzan() -> None:
    with pytest.raises(ValueError, match="fecha_fin_mandato"):
        Legislador(
            slug="x",
            apellido="X",
            nombre="Y",
            camara=Camara.HCDN,
            distrito="D",
            bloque=_bloque(),
            periodo_mandato="2023-2027",
            fecha_inicio_mandato=date(2027, 1, 1),
            fecha_fin_mandato=date(2023, 1, 1),
        )


def test_legislador_camara_y_bloque_camara_deben_coincidir() -> None:
    """Si el bloque es de HSN y el legislador es HCDN (o viceversa), error."""
    with pytest.raises(ValueError, match="camara"):
        Legislador(
            slug="x",
            apellido="X",
            nombre="Y",
            camara=Camara.HCDN,
            distrito="D",
            bloque=Bloque(nombre="X", camara=Camara.HSN),
            periodo_mandato="2023-2027",
            fecha_inicio_mandato=date(2023, 12, 10),
            fecha_fin_mandato=date(2027, 12, 9),
        )


def test_legislador_es_inmutable() -> None:
    leg = _legislador()
    with pytest.raises((AttributeError, TypeError)):
        leg.slug = "otro"  # type: ignore[misc]
