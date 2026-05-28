"""Tests unitarios del derivador de trámite HSN.

`derive_tramite_from_stages` es función pura sin I/O: la testeamos directo
con combinaciones sintéticas de fechas y giros. Cubre cada rama del
mapeo descripto en `docs/specs/02-ingesta-hsn.md` §"Derivación".
"""

from __future__ import annotations

from datetime import date

import pytest

from praxis.domain import Camara, Giro
from praxis.infrastructure.scrapers.hsn.parser import (
    FUENTE_DERIVADO,
    derive_tramite_from_stages,
)

pytestmark = pytest.mark.unit


# --- Vacío y casos básicos ---------------------------------------------------


def test_deriver_sin_datos_devuelve_lista_vacia() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[],
    )
    assert eventos == []


def test_deriver_solo_mesa_entradas() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=date(2024, 3, 12),
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[],
    )
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.fecha == date(2024, 3, 12)
    assert ev.camara == Camara.HSN
    assert ev.evento == "INGRESO A MESA DE ENTRADAS"
    assert ev.fuente == FUENTE_DERIVADO


# --- DAE en detalle ----------------------------------------------------------


def test_deriver_dado_cuenta_incluye_dae_en_detalle() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=date(2024, 4, 18),
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[],
        numero_dae="12/2024",
    )
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.evento == "DADO CUENTA EN SESION"
    assert ev.detalle == "D.A.E. 12/2024"


def test_deriver_dado_cuenta_sin_dae_deja_detalle_none() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=date(2024, 4, 18),
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[],
        numero_dae=None,
    )
    assert eventos[0].detalle is None


# --- Giros ------------------------------------------------------------------


def test_deriver_giro_con_ingreso_y_egreso_genera_dos_eventos() -> None:
    giro = Giro(
        comision="DE SALUD",
        fecha_ingreso=date(2024, 3, 21),
        fecha_egreso=date(2024, 5, 10),
    )
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[giro],
    )
    assert len(eventos) == 2
    assert eventos[0].evento == "GIRO A COMISION"
    assert eventos[0].detalle == "DE SALUD"
    assert eventos[0].fecha == date(2024, 3, 21)
    assert eventos[1].evento == "EGRESO DE COMISION"
    assert eventos[1].detalle == "DE SALUD"
    assert eventos[1].fecha == date(2024, 5, 10)


def test_deriver_giro_solo_ingreso_genera_un_evento() -> None:
    giro = Giro(comision="DE INDUSTRIA Y COMERCIO", fecha_ingreso=date(2024, 3, 21))
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[giro],
    )
    assert len(eventos) == 1
    assert eventos[0].evento == "GIRO A COMISION"


def test_deriver_giro_sin_ingreso_no_genera_eventos() -> None:
    """Sin fecha_ingreso del giro, no hay timestamp para usar."""
    giro = Giro(comision="X")
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=None,
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[giro],
    )
    assert eventos == []


# --- Orden cronológico -------------------------------------------------------


def test_deriver_orden_cronologico_ascendente() -> None:
    """Mismo expediente del spike (239/24/S/PL): mesa 12/3, comisiones 20/3,
    dado cuenta 18/4, giros el 21/3. Orden esperado: mesa → dir-com → giros → dado cuenta."""
    g1 = Giro(comision="DE SALUD", fecha_ingreso=date(2024, 3, 21))
    g2 = Giro(comision="DE INDUSTRIA Y COMERCIO", fecha_ingreso=date(2024, 3, 21))
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=date(2024, 3, 12),
        fecha_dado_cuenta=date(2024, 4, 18),
        fecha_dir_comisiones=date(2024, 3, 20),
        fecha_dictamen_mesa=None,
        giros=[g1, g2],
        numero_dae="12/2024",
    )
    eventos_fechas = [ev.fecha for ev in eventos]
    assert eventos_fechas == sorted(eventos_fechas)  # ascendente
    # Primer evento: mesa de entradas (más temprano).
    assert eventos[0].evento == "INGRESO A MESA DE ENTRADAS"
    # Último: dado cuenta (más tardío).
    assert eventos[-1].evento == "DADO CUENTA EN SESION"


def test_deriver_empate_de_fechas_respeta_orden_semantico() -> None:
    """Si mesa y dir.comisiones caen el mismo día, mesa va primero por
    el sort-key secundario que codifica el orden semántico."""
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=date(2024, 3, 12),
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=date(2024, 3, 12),
        fecha_dictamen_mesa=None,
        giros=[],
    )
    assert len(eventos) == 2
    assert eventos[0].evento == "INGRESO A MESA DE ENTRADAS"
    assert eventos[1].evento == "INGRESO A DIRECCION GENERAL DE COMISIONES"


# --- Cámara y fuente ---------------------------------------------------------


def test_deriver_todos_los_eventos_son_camara_hsn() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=date(2024, 1, 1),
        fecha_dado_cuenta=date(2024, 2, 1),
        fecha_dir_comisiones=date(2024, 3, 1),
        fecha_dictamen_mesa=date(2024, 4, 1),
        giros=[Giro(comision="X", fecha_ingreso=date(2024, 5, 1))],
    )
    for ev in eventos:
        assert ev.camara == Camara.HSN


def test_deriver_todos_los_eventos_tienen_fuente_derived() -> None:
    eventos = derive_tramite_from_stages(
        fecha_mesa_entradas=date(2024, 1, 1),
        fecha_dado_cuenta=None,
        fecha_dir_comisiones=None,
        fecha_dictamen_mesa=None,
        giros=[],
    )
    for ev in eventos:
        assert ev.fuente == FUENTE_DERIVADO
