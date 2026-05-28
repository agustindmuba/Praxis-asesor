"""Tests unitarios de `_inferir_tipo` del parser HCDN.

Aunque `_inferir_tipo` es función "privada" (prefijo underscore), es una
unidad pura sin I/O: testearla directamente con strings sintéticos cubre
cada rama de la heurística del Amendment 1 §6 del ADR 0002 sin depender
del contenido específico de los fixtures HTML.

Esto complementa los tests de contrato en
`tests/integration/scrapers/test_hcdn_parser.py`.
"""

from __future__ import annotations

import pytest

from praxis.domain.value_objects import OrigenExpediente, TipoExpediente
from praxis.infrastructure.scrapers.hcdn.parser import _inferir_tipo

pytestmark = pytest.mark.unit


# --- Rama PE/JGM: branch 1 (mensaje match) -----------------------------------


def test_inferir_tipo_pe_con_palabra_mensaje_devuelve_mensaje_pe() -> None:
    """Origen=EJECUTIVO + texto con 'Mensaje' como palabra completa → MENSAJE_PE."""
    tipo = _inferir_tipo("Mensaje del PE...", "", OrigenExpediente.EJECUTIVO)
    assert tipo == TipoExpediente.MENSAJE_PE


def test_inferir_tipo_jgm_con_palabra_mensaje_devuelve_mensaje_pe() -> None:
    """JEFATURA_GABINETE comparte la misma rama PE."""
    tipo = _inferir_tipo("MENSAJE N° 0015/24 sobre Y", "", OrigenExpediente.JEFATURA_GABINETE)
    assert tipo == TipoExpediente.MENSAJE_PE


# --- Rama PE/JGM: branch 2 (proyecto de ley match) ---------------------------


def test_inferir_tipo_pe_con_proyecto_de_ley_devuelve_proyecto_ley() -> None:
    """Origen=EJECUTIVO + texto con 'proyecto de ley' (sin 'mensaje') → PROYECTO_LEY."""
    tipo = _inferir_tipo("Proyecto de ley sobre X", "", OrigenExpediente.EJECUTIVO)
    assert tipo == TipoExpediente.PROYECTO_LEY


# --- Rama PE/JGM: branch 3 (default conservador) -----------------------------


def test_inferir_tipo_pe_ambiguo_cae_al_default_mensaje_pe() -> None:
    """Origen=EJECUTIVO sin marcadores reconocibles → MENSAJE_PE (default conservador).

    Espejo del caso real del fixture 0001-PE-2024: el extracto y sumario
    no mencionan 'mensaje' ni 'proyecto de ley' (esas menciones existen
    en otras partes del HTML que el parser no lee).
    """
    tipo = _inferir_tipo(
        "Algo neutro", "Texto sin marcadores conocidos", OrigenExpediente.EJECUTIVO
    )
    assert tipo == TipoExpediente.MENSAJE_PE


# --- Rama legacy: origen no-PE/JGM ignora la palabra "mensaje" ---------------


def test_inferir_tipo_diputado_con_palabra_mensaje_no_devuelve_mensaje_pe() -> None:
    """Si origen es DIPUTADO (u otro distinto de PE/JGM), la palabra 'mensaje'
    en el sumario no debe disparar MENSAJE_PE: el filtro por origen está antes
    de la regex. Resultado esperado: rama legacy con marcadores en primeros
    80 chars; sin 'declaraci/resoluci/comunicaci' → default PROYECTO_LEY."""
    tipo = _inferir_tipo("X mensaje Y", "", OrigenExpediente.DIPUTADO)
    assert tipo == TipoExpediente.PROYECTO_LEY


# --- Robustez extra: orígenes "otros" tampoco entran al PE branch -----------


def test_inferir_tipo_revision_diputados_no_entra_al_pe_branch() -> None:
    """REVISION_DIPUTADOS (CD) no es PE: debe seguir la rama legacy."""
    tipo = _inferir_tipo("Proyecto de declaración sobre X", "", OrigenExpediente.REVISION_DIPUTADOS)
    assert tipo == TipoExpediente.PROYECTO_DECLARACION


def test_inferir_tipo_diputado_con_proyecto_de_resolucion() -> None:
    """Sanity: la rama legacy detecta 'resoluci' en los primeros 80 chars."""
    tipo = _inferir_tipo("Proyecto de resolución sobre Y", "", OrigenExpediente.DIPUTADO)
    assert tipo == TipoExpediente.PROYECTO_RESOLUCION
