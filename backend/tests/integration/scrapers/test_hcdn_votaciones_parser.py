"""Tests del parser de votaciones HCDN.

Usan las fixtures HTML capturadas en el spike feat/26.1
(ver `docs/spikes/26-votaciones-hcdn.md`):

- `votaciones_index_home.html` — listado de las 500 votaciones más recientes.
- `votacion_5937.html` — detalle de "O.D. 84 - Régimen Zona Fría CAP VI"
  (voto en particular).
- `votacion_5931.html` — detalle de "O.D. 84 - Régimen Zona Fría VOT. EN GRAL"
  (voto en general).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from praxis.domain import Camara, TipoVotacion, VotoTipo
from praxis.infrastructure.scrapers.hcdn.votaciones import (
    parse_acta_votacion,
    parse_indice_votaciones,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "hcdn"


def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Índice
# ---------------------------------------------------------------------------


def test_indice_parsea_500_items() -> None:
    """El listado de la home trae 500 votaciones."""
    items = parse_indice_votaciones(_load("votaciones_index_home.html"))
    assert len(items) == 500


def test_indice_primer_item_es_la_votacion_mas_reciente() -> None:
    items = parse_indice_votaciones(_load("votaciones_index_home.html"))
    primero = items[0]
    assert primero.acta_id == 5937
    assert primero.fecha == date(2026, 5, 20)
    assert primero.hora == "22:07"
    assert primero.resultado_agregado == "AFIRMATIVO"
    assert "ZONA FRÍA" in primero.titulo
    assert primero.tipo_portal == "Votación Nominal"


def test_indice_links_pdf_y_html_resueltos() -> None:
    items = parse_indice_votaciones(_load("votaciones_index_home.html"))
    primero = items[0]
    assert primero.pdf_url is not None
    assert "/pdf/acta/5937" in primero.pdf_url
    assert primero.votacion_url is not None
    assert "/votacion/5937" in primero.votacion_url


def test_indice_acepta_html_vacio() -> None:
    """Si no hay tabla, devuelve lista vacía sin fallar."""
    assert parse_indice_votaciones("<html></html>") == []


# ---------------------------------------------------------------------------
# Detalle — votacion_5937 (capítulo, voto particular)
# ---------------------------------------------------------------------------


def test_detalle_5937_encabezado() -> None:
    votacion, _ = parse_acta_votacion(_load("votacion_5937.html"), acta_id=5937)
    assert votacion.camara == Camara.HCDN
    assert votacion.fecha == date(2026, 5, 20)
    assert votacion.sesion == "Período 144 - Reunión 3 - Acta 20"
    assert "ZONA FRÍA" in votacion.asunto
    assert "CAPÍTULO VI" in votacion.asunto
    assert votacion.titulo_od == "O.D. 84"
    assert votacion.presidida_por == "MENEM, MARTIN"
    assert votacion.acta_id_hcdn == 5937
    assert votacion.acta_pdf_url == "/pdf/acta/5937"


def test_detalle_5937_tipo_particular() -> None:
    votacion, _ = parse_acta_votacion(_load("votacion_5937.html"), acta_id=5937)
    # "CAPÍTULO VI" → voto en particular según heurística.
    assert votacion.tipo == TipoVotacion.PARTICULAR


def test_detalle_5937_totales() -> None:
    votacion, _ = parse_acta_votacion(_load("votacion_5937.html"), acta_id=5937)
    assert votacion.resultado_afirmativos == 137
    assert votacion.resultado_negativos == 102
    assert votacion.resultado_abstenciones == 1
    assert votacion.resultado_sin_votar == 1
    assert votacion.resultado_ausentes == 16
    assert votacion.aprobada is True


def test_detalle_5937_257_legisladores() -> None:
    """257 = HCDN. La suma de los conteos debe matchear."""
    votacion, votos = parse_acta_votacion(
        _load("votacion_5937.html"), acta_id=5937
    )
    assert len(votos) == 257
    suma = (
        votacion.resultado_afirmativos
        + votacion.resultado_negativos
        + votacion.resultado_abstenciones
        + votacion.resultado_sin_votar
        + votacion.resultado_ausentes
    )
    assert suma == 257


def test_detalle_5937_distribucion_votos_matchea_conteo() -> None:
    """Cuántos votos individuales por tipo == conteo del encabezado."""
    votacion, votos = parse_acta_votacion(
        _load("votacion_5937.html"), acta_id=5937
    )
    af = sum(1 for v in votos if v.voto == VotoTipo.AFIRMATIVO)
    neg = sum(1 for v in votos if v.voto == VotoTipo.NEGATIVO)
    abs_ = sum(1 for v in votos if v.voto == VotoTipo.ABSTENCION)
    sv = sum(1 for v in votos if v.voto == VotoTipo.SIN_VOTAR)
    aus = sum(1 for v in votos if v.voto == VotoTipo.AUSENTE)
    assert af == votacion.resultado_afirmativos
    assert neg == votacion.resultado_negativos
    assert abs_ == votacion.resultado_abstenciones
    assert sv == votacion.resultado_sin_votar
    assert aus == votacion.resultado_ausentes


def test_detalle_5937_voto_tiene_bloque_y_provincia() -> None:
    _, votos = parse_acta_votacion(_load("votacion_5937.html"), acta_id=5937)
    yedlin = next(v for v in votos if v.legislador_nombre == "YEDLIN, PABLO RAUL")
    assert yedlin.bloque == "Union Por La Patria"
    assert yedlin.distrito == "Tucumán"
    assert yedlin.voto == VotoTipo.NEGATIVO
    assert yedlin.legislador_hcdn_id == "A51126"


def test_detalle_5937_presidente_mapea_a_sin_votar() -> None:
    """Menem (presidente) no vota → SIN_VOTAR."""
    _, votos = parse_acta_votacion(_load("votacion_5937.html"), acta_id=5937)
    menem = next(v for v in votos if v.legislador_nombre.startswith("MENEM"))
    assert menem.voto == VotoTipo.SIN_VOTAR


# ---------------------------------------------------------------------------
# Detalle — votacion_5931 (voto en general)
# ---------------------------------------------------------------------------


def test_detalle_5931_tipo_general() -> None:
    """'VOT. EN GRAL' → voto en general."""
    votacion, _ = parse_acta_votacion(_load("votacion_5931.html"), acta_id=5931)
    assert votacion.tipo == TipoVotacion.GENERAL
    assert "VOT. EN GRAL" in votacion.asunto


def test_detalle_5931_257_legisladores_y_conteos_coinciden() -> None:
    votacion, votos = parse_acta_votacion(
        _load("votacion_5931.html"), acta_id=5931
    )
    assert len(votos) == 257
    suma = (
        votacion.resultado_afirmativos
        + votacion.resultado_negativos
        + votacion.resultado_abstenciones
        + votacion.resultado_sin_votar
        + votacion.resultado_ausentes
    )
    assert suma == 257


def test_detalle_5931_aprobada() -> None:
    votacion, _ = parse_acta_votacion(_load("votacion_5931.html"), acta_id=5931)
    assert votacion.aprobada is True
    # En general fue 132-105-4
    assert votacion.resultado_afirmativos == 132
    assert votacion.resultado_negativos == 105
    assert votacion.resultado_abstenciones == 4


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


def test_detalle_falla_si_html_no_es_votacion() -> None:
    with pytest.raises(ValueError, match="HTML sin"):
        parse_acta_votacion("<html><body></body></html>")


def test_detalle_falla_si_no_hay_fecha_en_titulo() -> None:
    bad = "<html><body><h4>Algun titulo sin fecha</h4></body></html>"
    with pytest.raises(ValueError, match="No pude extraer fecha"):
        parse_acta_votacion(bad)
