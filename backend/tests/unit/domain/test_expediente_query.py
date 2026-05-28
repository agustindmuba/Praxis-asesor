"""Tests unit de ExpedienteQuery (validaciones de __post_init__)."""

from __future__ import annotations

from datetime import date

import pytest

from praxis.domain import (
    LIMIT_MAX,
    Camara,
    EstadoExpediente,
    ExpedienteQuery,
    OrigenExpediente,
    ResultadoBusqueda,
    TipoExpediente,
)


def test_query_default_se_construye_sin_filtros() -> None:
    q = ExpedienteQuery()
    assert q.texto is None
    assert q.anio is None
    assert q.limit == 50
    assert q.offset == 0


def test_query_acepta_todos_los_filtros() -> None:
    q = ExpedienteQuery(
        texto="presupuesto",
        anio=2024,
        tipo=TipoExpediente.PROYECTO_LEY,
        camara=Camara.HCDN,
        origen=OrigenExpediente.DIPUTADO,
        estado=EstadoExpediente.EN_COMISION,
        autor_nombre="Massot",
        comision="Salud",
        fecha_ingreso_desde=date(2024, 1, 1),
        fecha_ingreso_hasta=date(2024, 12, 31),
        limit=100,
        offset=20,
    )
    assert q.texto == "presupuesto"
    assert q.limit == 100


def test_query_rechaza_limit_fuera_de_rango() -> None:
    with pytest.raises(ValueError, match="limit"):
        ExpedienteQuery(limit=0)
    with pytest.raises(ValueError, match="limit"):
        ExpedienteQuery(limit=LIMIT_MAX + 1)


def test_query_rechaza_offset_negativo() -> None:
    with pytest.raises(ValueError, match="offset"):
        ExpedienteQuery(offset=-1)


def test_query_rechaza_rango_de_fechas_invertido() -> None:
    with pytest.raises(ValueError, match="fecha_ingreso"):
        ExpedienteQuery(
            fecha_ingreso_desde=date(2024, 12, 31),
            fecha_ingreso_hasta=date(2024, 1, 1),
        )


def test_query_acepta_fecha_solo_desde_o_solo_hasta() -> None:
    """Si solo está uno, no hay validación que aplicar."""
    ExpedienteQuery(fecha_ingreso_desde=date(2024, 1, 1))
    ExpedienteQuery(fecha_ingreso_hasta=date(2024, 12, 31))


@pytest.mark.parametrize("campo", ["texto", "autor_nombre", "comision"])
def test_query_rechaza_strings_solo_whitespace(campo: str) -> None:
    with pytest.raises(ValueError, match=campo):
        ExpedienteQuery(**{campo: "   "})


def test_resultado_busqueda_default_vacio() -> None:
    r = ResultadoBusqueda()
    assert r.items == []
    assert r.total == 0
    assert r.limit == 50
    assert r.offset == 0
