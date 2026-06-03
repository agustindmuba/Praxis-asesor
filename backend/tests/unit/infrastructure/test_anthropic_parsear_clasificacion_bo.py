"""Tests del helper `_parsear_clasificacion_norma_bo` del
AnthropicLlmProvider — sin red, sin gastar tokens.

El helper tiene que ser defensivo: si el modelo se equivoca con el JSON,
con fences, con un área desconocida, con tipos de listas, etc., el
fallback es devolver una clasificación "otros" vacía, no levantar.
"""

from __future__ import annotations

import pytest

from praxis.domain import AreaTematica, ClasificacionNormaBOResult
from praxis.infrastructure.llm.anthropic_provider import (
    _parsear_clasificacion_norma_bo,
)

pytestmark = pytest.mark.unit


def test_json_valido_simple() -> None:
    raw = (
        '{"area_tematica": "salud", "palabras_clave": ["hospital", "medicacion"],'
        ' "afecta_expedientes_hcdn": true,'
        ' "referencias_legales": ["Ley 27.812"]}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert isinstance(r, ClasificacionNormaBOResult)
    assert r.area_tematica == AreaTematica.SALUD
    assert r.palabras_clave == ["hospital", "medicacion"]
    assert r.afecta_expedientes_hcdn is True
    assert r.referencias_legales == ["Ley 27.812"]


def test_quita_fences_json() -> None:
    raw = (
        "```json\n"
        '{"area_tematica": "justicia", "palabras_clave": [], '
        '"afecta_expedientes_hcdn": false, "referencias_legales": []}'
        "\n```"
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.JUSTICIA


def test_quita_fences_sin_json_lang() -> None:
    body = (
        '{"area_tematica": "ambiente", "palabras_clave": [],'
        ' "afecta_expedientes_hcdn": false, "referencias_legales": []}'
    )
    raw = f"```\n{body}\n```"
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.AMBIENTE


def test_json_malformado_devuelve_default_otros() -> None:
    raw = "esto no es JSON"
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.OTROS
    assert r.palabras_clave == []
    assert r.afecta_expedientes_hcdn is False
    assert r.referencias_legales == []


def test_area_desconocida_cae_a_otros() -> None:
    raw = (
        '{"area_tematica": "cibernetica", "palabras_clave": ["redes"],'
        ' "afecta_expedientes_hcdn": false, "referencias_legales": []}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.OTROS
    # Palabras y demás campos sí se respetan.
    assert r.palabras_clave == ["redes"]


def test_palabras_clave_no_es_lista_se_descarta() -> None:
    raw = (
        '{"area_tematica": "salud", "palabras_clave": "string en vez de lista",'
        ' "afecta_expedientes_hcdn": false, "referencias_legales": []}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.SALUD
    assert r.palabras_clave == []


def test_palabras_clave_normaliza_strings() -> None:
    raw = (
        '{"area_tematica": "trabajo", "palabras_clave": ["  jubilacion  ", "", "docente"],'
        ' "afecta_expedientes_hcdn": false, "referencias_legales": []}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.palabras_clave == ["jubilacion", "docente"]


def test_afecta_hcdn_truthy() -> None:
    raw = (
        '{"area_tematica": "otros", "palabras_clave": [],'
        ' "afecta_expedientes_hcdn": 1, "referencias_legales": []}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.afecta_expedientes_hcdn is True


def test_campos_ausentes_usan_defaults() -> None:
    """Si el modelo se olvida de un campo, no levantamos."""
    raw = '{"area_tematica": "salud"}'
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.area_tematica == AreaTematica.SALUD
    assert r.palabras_clave == []
    assert r.afecta_expedientes_hcdn is False
    assert r.referencias_legales == []


def test_referencias_legales_filtra_vacios() -> None:
    raw = (
        '{"area_tematica": "otros", "palabras_clave": [],'
        ' "afecta_expedientes_hcdn": false,'
        ' "referencias_legales": ["Ley 1", "", "  ", "Decreto 2/2026"]}'
    )
    r = _parsear_clasificacion_norma_bo(raw)
    assert r.referencias_legales == ["Ley 1", "Decreto 2/2026"]
