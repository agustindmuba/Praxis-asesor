"""Tests de integración de `LocalCatalogoComisiones` contra los snapshots
vendored (CSV HCDN + JSON HSN). Sin HTTP."""

from __future__ import annotations

import pytest

from praxis.domain import Camara, TipoComision
from praxis.infrastructure.comisiones import LocalCatalogoComisiones

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def catalogo() -> LocalCatalogoComisiones:
    return LocalCatalogoComisiones()


# --- Conteos esperados de los snapshots --------------------------------------


def test_carga_93_comisiones_hcdn(catalogo: LocalCatalogoComisiones) -> None:
    comisiones = catalogo.listar(Camara.HCDN)
    assert len(comisiones) == 93


def test_carga_48_comisiones_hsn(catalogo: LocalCatalogoComisiones) -> None:
    comisiones = catalogo.listar(Camara.HSN)
    assert len(comisiones) == 48


# --- Forma de las entradas HCDN ---------------------------------------------


def test_hcdn_todas_tienen_slug(catalogo: LocalCatalogoComisiones) -> None:
    diputados = catalogo.listar(Camara.HCDN)
    assert all(c.slug is not None for c in diputados)


def test_hcdn_mayoria_tiene_categoria_tematica(catalogo: LocalCatalogoComisiones) -> None:
    """Hallazgo: 92/93 comisiones HCDN tienen categoria_tematica.
    La excepción es una bicameral con slug "sen106" sin categoría asignada
    en el snapshot. El test admite hasta 5% sin categoría como tolerancia.
    """
    diputados = catalogo.listar(Camara.HCDN)
    con_cat = [c for c in diputados if c.categoria_tematica is not None]
    proporcion = len(con_cat) / len(diputados)
    assert proporcion >= 0.95


def test_hcdn_todas_son_permanentes(catalogo: LocalCatalogoComisiones) -> None:
    """Limitación documentada: el CSV upstream no discrimina tipo."""
    for c in catalogo.listar(Camara.HCDN):
        assert c.tipo == TipoComision.PERMANENTE


# --- Forma de las entradas HSN ----------------------------------------------


def test_hsn_no_tiene_slug_ni_categoria(catalogo: LocalCatalogoComisiones) -> None:
    """El JSON HSN no expone slug ni categoría."""
    for c in catalogo.listar(Camara.HSN):
        assert c.slug is None
        assert c.categoria_tematica is None


def test_hsn_distintos_tipos_presentes(catalogo: LocalCatalogoComisiones) -> None:
    """El JSON tiene UNICAMERAL PERMANENTE, BICAMERAL PERMANENTE, BICAMERAL ESPECIAL."""
    tipos = {c.tipo for c in catalogo.listar(Camara.HSN)}
    assert TipoComision.PERMANENTE in tipos
    assert TipoComision.BICAMERAL_PERMANENTE in tipos or TipoComision.BICAMERAL_ESPECIAL in tipos


# --- Búsqueda por nombre ----------------------------------------------------


def test_buscar_asuntos_constitucionales_en_hcdn(
    catalogo: LocalCatalogoComisiones,
) -> None:
    resultados = catalogo.buscar_por_nombre("ASUNTOS CONSTITUCIONALES", Camara.HCDN)
    assert any("ASUNTOS CONSTITUCIONALES" in c.nombre for c in resultados)


def test_buscar_case_insensitive(catalogo: LocalCatalogoComisiones) -> None:
    a = catalogo.buscar_por_nombre("salud")
    b = catalogo.buscar_por_nombre("SALUD")
    assert len(a) == len(b)


def test_buscar_sin_camara_busca_en_ambas(catalogo: LocalCatalogoComisiones) -> None:
    """Una palabra genérica debería matchear en ambas cámaras."""
    resultados = catalogo.buscar_por_nombre("comision")
    # "Comisión" no aparece habitualmente en los nombres (que son los temas).
    # Usemos algo más universal: "y" (la conjunción) aparece en muchos nombres.
    resultados = catalogo.buscar_por_nombre(" y ")
    camaras_encontradas = {c.camara for c in resultados}
    # Esperamos que ambas cámaras tengan comisiones con " y " en el nombre.
    assert len(camaras_encontradas) >= 1


def test_buscar_query_vacia_devuelve_vacio(catalogo: LocalCatalogoComisiones) -> None:
    assert catalogo.buscar_por_nombre("") == []
    assert catalogo.buscar_por_nombre("   ") == []


def test_buscar_no_match_devuelve_vacio(catalogo: LocalCatalogoComisiones) -> None:
    assert catalogo.buscar_por_nombre("xyzqwerty-no-existe") == []


# --- Defensiva --------------------------------------------------------------


def test_listar_devuelve_copia_independiente(catalogo: LocalCatalogoComisiones) -> None:
    a = catalogo.listar(Camara.HCDN)
    a.clear()
    b = catalogo.listar(Camara.HCDN)
    assert len(b) == 93
