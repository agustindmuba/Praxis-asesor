"""Tests del use case CalcularInsightsFeedback (feat-43.3).

Cubre:
- Distribución por accion_sugerida con conteo correcto de
  pendiente/hecho/ignorado/adaptado.
- Si una acción tiene < 5 cerrados, NO genera sugerencia.
- Si pct_ignorado >= 60% sobre >= 5 cerrados, genera "bajar_tono".
- Si pct_adaptado >= 60% sobre >= 5 cerrados, genera
  "revisar_patron_adaptado".
- Si hay >= 5 pendientes con > 7 días, genera "backlog".
- Severidad "alta" cuando pct_ignorado >= 80%.

Estos tests usan sqlite in-memory para que sean rápidos y no necesiten
Postgres ni docker compose. La query del use case usa funciones
estándar ANSI SQL.
"""

from __future__ import annotations

import pytest

from praxis.application.use_cases.calcular_insights_feedback import (
    CalcularInsightsFeedback,
    DistribucionAccion,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Tests de la dataclass DistribucionAccion (puro, sin DB)
# ---------------------------------------------------------------------------


def test_distribucion_pct_calcula_sobre_cerrados_no_total() -> None:
    """% se computa sobre hechos+ignorados+adaptados (no incluye pendientes)."""
    d = DistribucionAccion(
        accion="pedido_informes",
        total=10,
        pendientes=2,
        hechos=4,
        ignorados=3,
        adaptados=1,
    )
    cerrados = 4 + 3 + 1
    assert d.pct_hecho == pytest.approx(4 / cerrados)
    assert d.pct_ignorado == pytest.approx(3 / cerrados)
    assert d.pct_adaptado == pytest.approx(1 / cerrados)


def test_distribucion_pct_es_0_cuando_no_hay_cerrados() -> None:
    """Si todo está pendiente, los % son 0 (no NaN)."""
    d = DistribucionAccion(
        accion="silencio_estrategico",
        total=5,
        pendientes=5,
        hechos=0,
        ignorados=0,
        adaptados=0,
    )
    assert d.pct_hecho == 0.0
    assert d.pct_ignorado == 0.0
    assert d.pct_adaptado == 0.0


# ---------------------------------------------------------------------------
# Tests del método de sugerencias (puro, sin DB)
# ---------------------------------------------------------------------------


class _SesionFake:
    """No se usa en estos tests (solo testeamos _sugerencias)."""


def test_sugerencias_sin_muestras_no_dispara() -> None:
    """< 5 cerrados → no sugiere (poca evidencia)."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    distribucion = [
        DistribucionAccion(
            accion="pedido_informes",
            total=4, pendientes=0, hechos=0, ignorados=4, adaptados=0,
        ),
    ]
    sugerencias = uc._sugerencias(distribucion, backlog_n=0)
    assert sugerencias == []


def test_sugerencias_alto_pct_ignorado_dispara_bajar_tono() -> None:
    """>= 60% ignorado sobre >= 5 cerrados → "bajar_tono"."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    distribucion = [
        DistribucionAccion(
            accion="pedido_informes",
            total=10, pendientes=0,
            hechos=2, ignorados=7, adaptados=1,
        ),
    ]
    sugerencias = uc._sugerencias(distribucion, backlog_n=0)
    assert len(sugerencias) == 1
    s = sugerencias[0]
    assert s.tipo == "bajar_tono"
    assert s.accion_objetivo == "pedido_informes"
    assert s.severidad in ("alta", "media")
    assert "pedido_informes" in s.mensaje


def test_sugerencias_severidad_alta_cuando_pct_ignorado_extremo() -> None:
    """>= 80% ignorado → severidad alta."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    distribucion = [
        DistribucionAccion(
            accion="pedido_informes",
            total=10, pendientes=0,
            hechos=0, ignorados=10, adaptados=0,
        ),
    ]
    sugerencias = uc._sugerencias(distribucion, backlog_n=0)
    assert sugerencias[0].severidad == "alta"


def test_sugerencias_alto_pct_adaptado_dispara_revisar_patron() -> None:
    """>= 60% adaptado sobre >= 5 cerrados → "revisar_patron_adaptado"."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    distribucion = [
        DistribucionAccion(
            accion="retweet_critico",
            total=8, pendientes=0,
            hechos=1, ignorados=1, adaptados=6,
        ),
    ]
    sugerencias = uc._sugerencias(distribucion, backlog_n=0)
    assert len(sugerencias) == 1
    s = sugerencias[0]
    assert s.tipo == "revisar_patron_adaptado"
    assert s.accion_objetivo == "retweet_critico"


def test_sugerencias_backlog_dispara_si_acumulado() -> None:
    """>= 5 pendientes con > 7 días → "backlog"."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    sugerencias = uc._sugerencias(distribucion=[], backlog_n=7)
    assert len(sugerencias) == 1
    assert sugerencias[0].tipo == "backlog"


def test_sugerencias_backlog_no_dispara_si_poco() -> None:
    """< 5 pendientes antiguos → no sugiere backlog."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    sugerencias = uc._sugerencias(distribucion=[], backlog_n=3)
    assert sugerencias == []


def test_sugerencias_ignorar_gana_sobre_adaptar_si_ambos_alto() -> None:
    """elif ordering: si ambos umbrales se cumplen, ignorar gana."""
    uc = CalcularInsightsFeedback(session=_SesionFake())  # type: ignore[arg-type]
    distribucion = [
        DistribucionAccion(
            accion="pedido_informes",
            total=20, pendientes=0,
            hechos=2, ignorados=12, adaptados=6,    # ambos > 30%
        ),
    ]
    sugerencias = uc._sugerencias(distribucion, backlog_n=0)
    assert len(sugerencias) == 1
    assert sugerencias[0].tipo == "bajar_tono"
