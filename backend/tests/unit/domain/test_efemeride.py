"""Tests del dominio Efemeride (feat-53.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from praxis.domain import (
    EFEMERIDE_RELEVANCIA_LABELS,
    EFEMERIDE_TIPO_LABELS,
    Efemeride,
    RelevanciaEfemeride,
    TipoEfemeride,
)

pytestmark = pytest.mark.unit


def _make(
    *,
    mes: int = 3,
    dia: int = 8,
    titulo: str = "Día Internacional de la Mujer",
    tipo: TipoEfemeride = TipoEfemeride.INTERNACIONAL,
    relevancia: RelevanciaEfemeride = RelevanciaEfemeride.ALTA,
    **kw,
) -> Efemeride:
    return Efemeride(
        id=uuid4(),
        mes=mes,
        dia=dia,
        titulo=titulo,
        tipo=tipo,
        relevancia=relevancia,
        **kw,
    )


# ---------------------------------------------------------------------------
# Construcción válida
# ---------------------------------------------------------------------------


def test_efemeride_recurrente_se_construye_ok() -> None:
    ef = _make()
    assert ef.mes == 3
    assert ef.dia == 8
    assert ef.titulo == "Día Internacional de la Mujer"
    assert ef.anio_unico is None
    assert ef.es_recurrente is True
    assert ef.fecha_corta == "03-08"


def test_efemeride_con_anio_unico_no_es_recurrente() -> None:
    ef = _make(mes=3, dia=24, titulo="50° aniversario del Golpe", anio_unico=2026)
    assert ef.es_recurrente is False
    assert ef.anio_unico == 2026


def test_efemeride_acepta_metadata_completa() -> None:
    ef = _make(
        descripcion="Conmemoración de las luchas por la igualdad de género.",
        fuente="ONU — Asamblea General resolución 32/142 (1977)",
        areas_tematicas=["derechos_humanos", "trabajo"],
    )
    assert ef.descripcion is not None
    assert ef.fuente is not None
    assert "derechos_humanos" in ef.areas_tematicas


def test_fecha_corta_zero_pad() -> None:
    ef = _make(mes=1, dia=5)
    assert ef.fecha_corta == "01-05"


# ---------------------------------------------------------------------------
# Validaciones del __post_init__
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mes", [0, 13, -1, 100])
def test_mes_invalido_lanza(mes: int) -> None:
    with pytest.raises(ValueError, match="mes inválido"):
        _make(mes=mes)


@pytest.mark.parametrize("dia", [0, 32, -1, 100])
def test_dia_invalido_lanza(dia: int) -> None:
    with pytest.raises(ValueError, match="dia inválido"):
        _make(dia=dia)


def test_titulo_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="titulo"):
        _make(titulo="")


def test_titulo_solo_espacios_lanza() -> None:
    with pytest.raises(ValueError, match="titulo"):
        _make(titulo="   ")


@pytest.mark.parametrize("anio", [1500, 2200, -1])
def test_anio_unico_fuera_de_rango_lanza(anio: int) -> None:
    with pytest.raises(ValueError, match="anio_unico fuera de rango"):
        _make(anio_unico=anio)


def test_anio_unico_dentro_de_rango_ok() -> None:
    ef = _make(anio_unico=1983)
    assert ef.anio_unico == 1983


# ---------------------------------------------------------------------------
# Enums + labels
# ---------------------------------------------------------------------------


def test_todos_los_tipos_tienen_label() -> None:
    for tipo in TipoEfemeride:
        assert tipo in EFEMERIDE_TIPO_LABELS
        assert EFEMERIDE_TIPO_LABELS[tipo].strip()


def test_todas_las_relevancias_tienen_label() -> None:
    for rel in RelevanciaEfemeride:
        assert rel in EFEMERIDE_RELEVANCIA_LABELS
        assert EFEMERIDE_RELEVANCIA_LABELS[rel].strip()


def test_tipos_son_seis() -> None:
    """Mantiene el set chico — si crece, revisar UI de filtros."""
    assert len(list(TipoEfemeride)) == 6


# ---------------------------------------------------------------------------
# Casos de uso realistas (sanity check del modelado)
# ---------------------------------------------------------------------------


def test_caso_dia_de_la_memoria_24_marzo() -> None:
    """24/03 — Día Nacional de la Memoria. Ley 26.085."""
    ef = _make(
        mes=3,
        dia=24,
        titulo="Día Nacional de la Memoria por la Verdad y la Justicia",
        tipo=TipoEfemeride.NACIONAL,
        relevancia=RelevanciaEfemeride.ALTA,
        descripcion="Conmemoración del Golpe de Estado de 1976.",
        fuente="Ley 26.085",
        areas_tematicas=["derechos_humanos", "justicia"],
    )
    assert ef.tipo == TipoEfemeride.NACIONAL
    assert ef.fecha_corta == "03-24"


def test_caso_aniversario_unico_bicentenario() -> None:
    """200 años de la Independencia: 2016 fue año único."""
    ef = _make(
        mes=7,
        dia=9,
        titulo="Bicentenario de la Independencia argentina",
        tipo=TipoEfemeride.ANIVERSARIO,
        relevancia=RelevanciaEfemeride.ALTA,
        anio_unico=2016,
    )
    assert ef.es_recurrente is False


def test_caso_dia_internacional_baja_relevancia() -> None:
    """Día Internacional del Lavavajillas — baja relevancia política."""
    ef = _make(
        mes=10,
        dia=14,
        titulo="Día Internacional del Lavaplatos",
        tipo=TipoEfemeride.TEMATICA,
        relevancia=RelevanciaEfemeride.BAJA,
    )
    assert ef.relevancia == RelevanciaEfemeride.BAJA
