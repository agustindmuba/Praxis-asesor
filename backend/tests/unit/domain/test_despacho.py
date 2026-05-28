"""Tests unitarios de la entidad Despacho."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from praxis.domain import Despacho

pytestmark = pytest.mark.unit


def test_despacho_minimo() -> None:
    d = Despacho(id=uuid4(), nombre="Despacho de prueba")
    assert d.nombre == "Despacho de prueba"
    assert d.legislador_titular_slug is None
    assert d.configuracion == {}


def test_despacho_con_legislador_titular() -> None:
    d = Despacho(
        id=uuid4(),
        nombre="Despacho X",
        legislador_titular_slug="haguirre",
        configuracion={"tema": "salud"},
    )
    assert d.legislador_titular_slug == "haguirre"
    assert d.configuracion["tema"] == "salud"


def test_despacho_nombre_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="nombre"):
        Despacho(id=uuid4(), nombre=" ")


def test_despacho_es_mutable() -> None:
    """A diferencia de Comision/Legislador/Bloque, Despacho es mutable
    porque configuración y legislador titular cambian."""
    d = Despacho(id=uuid4(), nombre="X")
    d.legislador_titular_slug = "haguirre"
    assert d.legislador_titular_slug == "haguirre"


def test_despacho_configuraciones_independientes() -> None:
    """Regression guard: cada instancia tiene su propio dict de configuración."""
    d1 = Despacho(id=uuid4(), nombre="A")
    d2 = Despacho(id=uuid4(), nombre="B")
    d1.configuracion["x"] = 1
    assert "x" not in d2.configuracion


def test_despacho_con_timestamps() -> None:
    now = datetime.now(UTC)
    d = Despacho(id=uuid4(), nombre="X", creado_en=now, actualizado_en=now)
    assert d.creado_en == now
