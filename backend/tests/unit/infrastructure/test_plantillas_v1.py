"""Tests del catálogo de plantillas v1 (feat-41.2).

Verifica que las plantillas declaradas en `plantillas_v1.py` están
bien formadas: name snake_case único, body_params cuadran con
placeholders, todas son UTILITY y arrancan PENDIENTE_APROBACION.
"""

from __future__ import annotations

import pytest

from praxis.domain import CategoriaPlantilla, EstadoMetaPlantilla
from praxis.infrastructure.whatsapp.plantillas_v1 import (
    PLANTILLAS_V1,
    plantillas_v1_por_name,
)

pytestmark = pytest.mark.unit


def test_catalogo_no_vacio() -> None:
    assert len(PLANTILLAS_V1) >= 5


def test_names_son_unicos() -> None:
    names = [p.name for p in PLANTILLAS_V1]
    assert len(names) == len(set(names)), "name duplicado en catálogo"


def test_todas_utility() -> None:
    for p in PLANTILLAS_V1:
        assert p.categoria == CategoriaPlantilla.UTILITY, (
            f"Plantilla {p.name} no es UTILITY"
        )


def test_todas_pendientes_inicialmente() -> None:
    for p in PLANTILLAS_V1:
        assert p.estado_meta == EstadoMetaPlantilla.PENDIENTE_APROBACION


def test_idioma_es_AR_por_default() -> None:
    for p in PLANTILLAS_V1:
        # v1 todas en es_AR; si en el futuro hay multi-idioma, ajustar.
        assert p.idioma == "es_AR", f"Plantilla {p.name} no es es_AR"


def test_placeholders_cuadran_con_body_params() -> None:
    """El constructor de `PlantillaWhatsApp` ya valida que los {{N}}
    cuadren con `body_params`. Si alguna definición no cuadra, este
    test al importar habría fallado. Este test reafirma el contrato."""
    import re
    for p in PLANTILLAS_V1:
        encontrados = sorted({
            int(m) for m in re.findall(r"\{\{(\d+)\}\}", p.contenido_referencia)
        })
        if encontrados:
            assert encontrados == list(range(1, len(p.body_params) + 1)), (
                f"{p.name}: placeholders {encontrados} no cuadran con "
                f"{len(p.body_params)} body_params"
            )
        else:
            # Sin placeholders → body_params debe ser vacío.
            assert p.body_params == []


def test_plantillas_v1_por_name() -> None:
    d = plantillas_v1_por_name()
    assert len(d) == len(PLANTILLAS_V1)
    assert "briefing_diario" in d
    assert d["briefing_diario"].name == "briefing_diario"


def test_briefing_diario_presente() -> None:
    """Briefing diario es la plantilla principal de v1 — chequea que
    siga ahí (regression guard si alguien renombra)."""
    names = {p.name for p in PLANTILLAS_V1}
    assert "briefing_diario" in names


def test_alertas_mencion_presentes() -> None:
    names = {p.name for p in PLANTILLAS_V1}
    assert "alerta_mencion_simple" in names
    assert "alerta_mencion_agrupada" in names


def test_opt_in_opt_out_presentes() -> None:
    """Compliance: necesitamos plantillas de opt-in (solicitud) y
    opt-out (confirmación). Ver ADR 0009 §"WhatsApp opt-in"."""
    names = {p.name for p in PLANTILLAS_V1}
    assert "opt_in_solicitud" in names
    assert "opt_out_confirmacion" in names
