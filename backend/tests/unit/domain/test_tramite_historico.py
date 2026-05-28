"""Tests unitarios de `praxis.domain.tramite_historico`.

Funciones puras: cada test arma una lista sintética de TramiteEvento y
verifica el output de la función bajo prueba. Sin I/O.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from praxis.domain import (
    Camara,
    TramiteEvento,
    eventos_recientes,
    filter_by_camara,
    filter_by_rango,
    merge_tramite,
    validar_consistencia,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(
    fecha: date | None,
    evento: str,
    *,
    detalle: str | None = None,
    camara: Camara = Camara.HCDN,
    fuente: str | None = None,
) -> TramiteEvento:
    return TramiteEvento(
        fecha=fecha,
        camara=camara,
        evento=evento,
        detalle=detalle,
        fuente=fuente,
    )


# ---------------------------------------------------------------------------
# merge_tramite
# ---------------------------------------------------------------------------


def test_merge_listas_disjuntas_concatena_y_ordena() -> None:
    a = [_ev(date(2024, 5, 1), "A")]
    b = [_ev(date(2024, 3, 1), "B")]
    resultado = merge_tramite(a, b)
    assert [e.evento for e in resultado] == ["B", "A"]


def test_merge_no_duplica_eventos_identicos() -> None:
    ev = _ev(date(2024, 3, 1), "GIRO", detalle="A LA COMISION X")
    resultado = merge_tramite([ev], [ev])
    assert len(resultado) == 1


def test_merge_preserva_version_existente_cuando_hay_duplicado() -> None:
    """Si un evento aparece en ambas listas, se preserva la versión de la
    primera (criterio: fuente más temprana gana)."""
    ev_hcdn = _ev(date(2024, 3, 1), "GIRO", fuente="scraper:hcdn")
    ev_hsn = _ev(date(2024, 3, 1), "GIRO", fuente="derived:hsn-stages")
    # Mismas claves (fecha, evento, detalle, camara), distinta fuente.
    resultado = merge_tramite([ev_hcdn], [ev_hsn])
    assert len(resultado) == 1
    assert resultado[0].fuente == "scraper:hcdn"


def test_merge_distintos_detalles_no_son_duplicados() -> None:
    """Dos giros con misma fecha pero distinta comisión son eventos distintos."""
    e1 = _ev(date(2024, 3, 1), "GIRO", detalle="A LA COMISION X")
    e2 = _ev(date(2024, 3, 1), "GIRO", detalle="A LA COMISION Y")
    resultado = merge_tramite([e1], [e2])
    assert len(resultado) == 2


def test_merge_distintas_camaras_no_son_duplicados() -> None:
    e1 = _ev(date(2024, 3, 1), "INGRESO", camara=Camara.HCDN)
    e2 = _ev(date(2024, 3, 1), "INGRESO", camara=Camara.HSN)
    resultado = merge_tramite([e1], [e2])
    assert len(resultado) == 2


def test_merge_no_muta_inputs() -> None:
    a = [_ev(date(2024, 3, 1), "A")]
    b = [_ev(date(2024, 4, 1), "B")]
    a_orig = a[:]
    b_orig = b[:]
    merge_tramite(a, b)
    assert a == a_orig
    assert b == b_orig


def test_merge_eventos_sin_fecha_al_final() -> None:
    a = [_ev(None, "SIN FECHA")]
    b = [_ev(date(2024, 3, 1), "CON FECHA")]
    resultado = merge_tramite(a, b)
    assert resultado[0].evento == "CON FECHA"
    assert resultado[-1].evento == "SIN FECHA"


# ---------------------------------------------------------------------------
# filter_by_camara
# ---------------------------------------------------------------------------


def test_filter_by_camara_devuelve_solo_la_camara_pedida() -> None:
    eventos = [
        _ev(date(2024, 3, 1), "A", camara=Camara.HCDN),
        _ev(date(2024, 4, 1), "B", camara=Camara.HSN),
        _ev(date(2024, 5, 1), "C", camara=Camara.HCDN),
    ]
    resultado = filter_by_camara(eventos, Camara.HCDN)
    assert [e.evento for e in resultado] == ["A", "C"]


def test_filter_by_camara_vacio_si_no_hay_matches() -> None:
    eventos = [_ev(date(2024, 3, 1), "A", camara=Camara.HCDN)]
    assert filter_by_camara(eventos, Camara.HSN) == []


# ---------------------------------------------------------------------------
# filter_by_rango
# ---------------------------------------------------------------------------


def test_filter_by_rango_incluye_bordes() -> None:
    eventos = [
        _ev(date(2024, 1, 1), "A"),
        _ev(date(2024, 6, 1), "B"),
        _ev(date(2024, 12, 31), "C"),
    ]
    resultado = filter_by_rango(eventos, date(2024, 1, 1), date(2024, 6, 1))
    assert [e.evento for e in resultado] == ["A", "B"]


def test_filter_by_rango_solo_desde() -> None:
    eventos = [
        _ev(date(2024, 1, 1), "A"),
        _ev(date(2024, 6, 1), "B"),
    ]
    resultado = filter_by_rango(eventos, desde=date(2024, 3, 1))
    assert [e.evento for e in resultado] == ["B"]


def test_filter_by_rango_solo_hasta() -> None:
    eventos = [
        _ev(date(2024, 1, 1), "A"),
        _ev(date(2024, 6, 1), "B"),
    ]
    resultado = filter_by_rango(eventos, hasta=date(2024, 3, 1))
    assert [e.evento for e in resultado] == ["A"]


def test_filter_by_rango_sin_filtros_incluye_sin_fecha() -> None:
    eventos = [_ev(None, "SIN_FECHA"), _ev(date(2024, 1, 1), "CON_FECHA")]
    resultado = filter_by_rango(eventos)
    assert len(resultado) == 2


def test_filter_by_rango_con_filtros_excluye_sin_fecha() -> None:
    eventos = [_ev(None, "SIN_FECHA"), _ev(date(2024, 1, 1), "CON_FECHA")]
    resultado = filter_by_rango(eventos, desde=date(2024, 1, 1))
    assert [e.evento for e in resultado] == ["CON_FECHA"]


# ---------------------------------------------------------------------------
# eventos_recientes
# ---------------------------------------------------------------------------


def test_eventos_recientes_devuelve_top_n_ordenado() -> None:
    eventos = [
        _ev(date(2024, 1, 1), "A"),
        _ev(date(2024, 5, 1), "B"),
        _ev(date(2024, 3, 1), "C"),
    ]
    resultado = eventos_recientes(eventos, 2)
    assert [e.evento for e in resultado] == ["C", "B"]


def test_eventos_recientes_excluye_sin_fecha() -> None:
    eventos = [_ev(None, "SIN_FECHA"), _ev(date(2024, 1, 1), "CON_FECHA")]
    resultado = eventos_recientes(eventos, 5)
    assert [e.evento for e in resultado] == ["CON_FECHA"]


def test_eventos_recientes_n_mayor_que_lista_devuelve_todo() -> None:
    eventos = [_ev(date(2024, 1, 1), "A"), _ev(date(2024, 2, 1), "B")]
    resultado = eventos_recientes(eventos, 10)
    assert len(resultado) == 2


def test_eventos_recientes_n_cero_o_negativo_devuelve_vacio() -> None:
    eventos = [_ev(date(2024, 1, 1), "A")]
    assert eventos_recientes(eventos, 0) == []
    assert eventos_recientes(eventos, -3) == []


# ---------------------------------------------------------------------------
# validar_consistencia
# ---------------------------------------------------------------------------


def test_validar_lista_vacia_es_consistente() -> None:
    assert validar_consistencia([]) == []


def test_validar_lista_sin_problemas() -> None:
    eventos = [
        _ev(date(2024, 1, 1), "A"),
        _ev(date(2024, 2, 1), "B"),
    ]
    assert validar_consistencia(eventos) == []


def test_validar_detecta_duplicados() -> None:
    ev = _ev(date(2024, 1, 1), "DUPE")
    problemas = validar_consistencia([ev, ev])
    assert len(problemas) == 1
    assert "Duplicado" in problemas[0]


def test_validar_detecta_fecha_futura() -> None:
    futuro = date.today() + timedelta(days=365)
    eventos = [_ev(futuro, "TIME TRAVEL")]
    problemas = validar_consistencia(eventos)
    assert any("Fecha futura" in p for p in problemas)


def test_validar_no_se_queja_de_eventos_sin_fecha() -> None:
    """Sin fecha es legítimo (eventos antiguos no fechados) — no es problema."""
    eventos = [_ev(None, "VIEJO")]
    assert validar_consistencia(eventos) == []
