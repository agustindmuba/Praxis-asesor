"""Tests de integración de `CsvPadronRepository` contra los CSVs reales
vendored del Observatorio.

Estos tests NO hacen HTTP; leen los archivos versionados en `backend/data/padron/`.
"""

from __future__ import annotations

import pytest

from praxis.domain import Camara
from praxis.infrastructure.padron import CsvPadronRepository

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def repo() -> CsvPadronRepository:
    """Una sola instancia para todos los tests del módulo (los CSVs se cargan una vez)."""
    return CsvPadronRepository()


# --- Conteos esperados de los snapshots vendored -----------------------------


def test_carga_257_diputados(repo: CsvPadronRepository) -> None:
    diputados = repo.listar(Camara.HCDN)
    assert len(diputados) == 257


def test_carga_72_senadores(repo: CsvPadronRepository) -> None:
    senadores = repo.listar(Camara.HSN)
    assert len(senadores) == 72


# --- Búsqueda por slug -------------------------------------------------------


def test_buscar_diputada_aguirre_por_slug(repo: CsvPadronRepository) -> None:
    """haguirre es Hilda Aguirre, La Rioja, Unión por la Patria."""
    leg = repo.buscar_por_slug("haguirre", Camara.HCDN)
    assert leg.apellido == "Aguirre"
    assert leg.nombre == "Hilda"
    assert leg.distrito == "LA RIOJA"
    assert leg.bloque.nombre == "UNIÓN POR LA PATRIA"
    assert leg.bloque.camara == Camara.HCDN


def test_buscar_senador_abad_por_slug(repo: CsvPadronRepository) -> None:
    leg = repo.buscar_por_slug("s546", Camara.HSN)
    assert leg.apellido == "Abad"
    assert leg.distrito == "BUENOS AIRES"
    assert "RADICAL" in leg.bloque.nombre  # "UCR - UNIÓN CÍVICA RADICAL"


def test_buscar_slug_inexistente_lanza_keyerror(repo: CsvPadronRepository) -> None:
    with pytest.raises(KeyError):
        repo.buscar_por_slug("no-existe-este-slug", Camara.HCDN)


def test_buscar_slug_en_camara_equivocada_lanza(repo: CsvPadronRepository) -> None:
    """haguirre existe en HCDN, no en HSN."""
    with pytest.raises(KeyError):
        repo.buscar_por_slug("haguirre", Camara.HSN)


# --- Búsqueda por nombre -----------------------------------------------------


def test_buscar_por_nombre_aguirre_devuelve_al_menos_uno(
    repo: CsvPadronRepository,
) -> None:
    resultados = repo.buscar_por_nombre("Aguirre")
    apellidos = {leg.apellido for leg in resultados}
    assert "Aguirre" in apellidos


def test_buscar_por_nombre_case_insensitive(repo: CsvPadronRepository) -> None:
    a = repo.buscar_por_nombre("aguirre")
    b = repo.buscar_por_nombre("AGUIRRE")
    c = repo.buscar_por_nombre("Aguirre")
    assert len(a) == len(b) == len(c)
    assert len(a) >= 1


def test_buscar_por_nombre_query_vacia_devuelve_vacio(
    repo: CsvPadronRepository,
) -> None:
    assert repo.buscar_por_nombre("") == []
    assert repo.buscar_por_nombre("   ") == []


def test_buscar_por_nombre_busca_en_ambas_camaras(repo: CsvPadronRepository) -> None:
    """Si el query matchea apellidos de ambas cámaras, debería devolver de ambas."""
    # "M" como query es muy genérico — debería matchear muchos legisladores.
    resultados = repo.buscar_por_nombre("M")
    camaras = {leg.camara for leg in resultados}
    # Hay legisladores con M tanto en HCDN como HSN.
    assert Camara.HCDN in camaras
    assert Camara.HSN in camaras


# --- Invariantes de los datos cargados ---------------------------------------


def test_todos_los_diputados_tienen_camara_hcdn(repo: CsvPadronRepository) -> None:
    for leg in repo.listar(Camara.HCDN):
        assert leg.camara == Camara.HCDN
        assert leg.bloque.camara == Camara.HCDN


def test_todos_los_senadores_tienen_camara_hsn(repo: CsvPadronRepository) -> None:
    for leg in repo.listar(Camara.HSN):
        assert leg.camara == Camara.HSN
        assert leg.bloque.camara == Camara.HSN


def test_listar_devuelve_copia_independiente(repo: CsvPadronRepository) -> None:
    """El repo no debe ser corrompido si el llamador muta su retorno."""
    diputados = repo.listar(Camara.HCDN)
    diputados.clear()
    # Una segunda llamada debería seguir devolviendo todos.
    diputados_otra_vez = repo.listar(Camara.HCDN)
    assert len(diputados_otra_vez) == 257
