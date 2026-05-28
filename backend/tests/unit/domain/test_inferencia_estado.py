"""Tests unitarios de la heurística de inferencia de estado + caducidad.

Aprobada por Agustín 2026-05-28. Ver `docs/specs/07-inferencia-estado.md`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    NumeroExpediente,
    TipoExpediente,
    TramiteEvento,
)
from praxis.domain.inferencia_estado import (
    inferir_caducidad,
    inferir_estado,
    inferir_estado_y_caducidad,
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
) -> TramiteEvento:
    return TramiteEvento(
        fecha=fecha,
        camara=camara,
        evento=evento,
        detalle=detalle,
        fuente="test",
    )


def _exp(
    *,
    fecha_ingreso: date | None = None,
    tramite: list[TramiteEvento] | None = None,
) -> Expediente:
    return Expediente(
        numero=NumeroExpediente.parse_hcdn("1-D-2024"),
        tipo=TipoExpediente.PROYECTO_LEY,
        titulo="Test",
        fecha_ingreso=fecha_ingreso,
        tramite=tramite or [],
    )


HOY = date(2026, 6, 1)


# ---------------------------------------------------------------------------
# inferir_estado: cada rama de la heurística
# ---------------------------------------------------------------------------


def test_archivado_gana_aunque_haya_sancion() -> None:
    tramite = [
        _ev(date(2024, 3, 1), "SANCION DEFINITIVA", camara=Camara.HCDN),
        _ev(date(2024, 3, 1), "SANCION DEFINITIVA", camara=Camara.HSN),
        _ev(date(2024, 6, 1), "ARCHIVADO POR ART 1 LEY 13640"),
    ]
    estado = inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
    assert estado == EstadoExpediente.ARCHIVADO


def test_caduco_por_evento_explicito() -> None:
    tramite = [_ev(date(2024, 3, 1), "CADUCIDAD ART 1 LEY 13640")]
    assert inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY) == EstadoExpediente.CADUCO


def test_caduco_por_fecha_vencida() -> None:
    """Sin evento de caducidad pero fecha_caducidad < hoy → CADUCO."""
    tramite = [_ev(date(2022, 3, 1), "GIRO A COMISION")]
    fecha_caducidad = date(2024, 3, 1)  # < HOY
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=fecha_caducidad, hoy=HOY)
        == EstadoExpediente.CADUCO
    )


def test_sancionado_requiere_ambas_camaras() -> None:
    tramite = [
        _ev(date(2024, 3, 1), "SANCION", camara=Camara.HCDN),
        _ev(date(2024, 5, 1), "SANCION", camara=Camara.HSN),
    ]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.SANCIONADO
    )


def test_media_sancion_hcdn() -> None:
    tramite = [_ev(date(2024, 3, 1), "SANCION", camara=Camara.HCDN)]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.MEDIA_SANCION_HCDN
    )


def test_media_sancion_hsn() -> None:
    tramite = [_ev(date(2024, 3, 1), "SANCION", camara=Camara.HSN)]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.MEDIA_SANCION_HSN
    )


def test_con_dictamen() -> None:
    tramite = [_ev(date(2024, 3, 1), "DICTAMEN DE MAYORIA")]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.CON_DICTAMEN
    )


def test_en_comision_por_giro() -> None:
    tramite = [_ev(date(2024, 3, 1), "GIRO A COMISION DE SALUD")]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.EN_COMISION
    )


def test_en_comision_por_texto_en_comision() -> None:
    tramite = [_ev(date(2024, 3, 1), "EN COMISION DE LABOR")]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.EN_COMISION
    )


def test_ingresado() -> None:
    tramite = [_ev(date(2024, 3, 1), "INGRESO A MESA DE ENTRADAS")]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY) == EstadoExpediente.INGRESADO
    )


def test_desconocido_si_no_hay_eventos() -> None:
    assert inferir_estado(tramite=[], fecha_caducidad=None, hoy=HOY) == EstadoExpediente.DESCONOCIDO


def test_desconocido_si_eventos_no_matchean_nada() -> None:
    tramite = [_ev(date(2024, 3, 1), "EVENTO RARO DESCONOCIDO")]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.DESCONOCIDO
    )


# ---------------------------------------------------------------------------
# inferir_estado: matching considera detalle también
# ---------------------------------------------------------------------------


def test_match_considera_detalle() -> None:
    """Si la palabra clave está en el detalle (no en el evento), también matchea."""
    tramite = [
        _ev(
            date(2024, 3, 1),
            "MOVIMIENTO",
            detalle="SE PRODUJO LA SANCION DEFINITIVA",
            camara=Camara.HSN,
        )
    ]
    assert (
        inferir_estado(tramite=tramite, fecha_caducidad=None, hoy=HOY)
        == EstadoExpediente.MEDIA_SANCION_HSN
    )


# ---------------------------------------------------------------------------
# inferir_caducidad
# ---------------------------------------------------------------------------


def test_caducidad_sin_fecha_ingreso() -> None:
    cad_orig, cad, prorr = inferir_caducidad(None, [])
    assert (cad_orig, cad, prorr) == (None, None, False)


def test_caducidad_sin_prorroga() -> None:
    """Caducidad original a 730 días, sin prórroga → caducidad = original."""
    fecha_ingreso = date(2024, 1, 1)
    cad_orig, cad, prorr = inferir_caducidad(fecha_ingreso, [])
    assert cad_orig == date(2024, 1, 1) + timedelta(days=730)
    assert cad == cad_orig
    assert prorr is False


def test_caducidad_con_prorroga_explicita() -> None:
    fecha_ingreso = date(2024, 1, 1)
    tramite = [_ev(date(2025, 12, 1), "PRORROGA DEL PROYECTO POR LEY 13640")]
    cad_orig, cad, prorr = inferir_caducidad(fecha_ingreso, tramite)
    assert prorr is True
    assert cad_orig == fecha_ingreso + timedelta(days=730)
    assert cad == fecha_ingreso + timedelta(days=730 * 2)


def test_caducidad_prorrogado_detecta_en_detalle() -> None:
    fecha_ingreso = date(2024, 1, 1)
    tramite = [_ev(date(2025, 12, 1), "MOVIMIENTO", detalle="se prorroga por dos años más")]
    _, _, prorr = inferir_caducidad(fecha_ingreso, tramite)
    assert prorr is True


def test_caducidad_no_confunde_otras_palabras() -> None:
    """Evento sin 'prorroga' no debe disparar prorrogado=True."""
    fecha_ingreso = date(2024, 1, 1)
    tramite = [_ev(date(2024, 5, 1), "GIRO A COMISION DE INTERIOR")]
    _, _, prorr = inferir_caducidad(fecha_ingreso, tramite)
    assert prorr is False


# ---------------------------------------------------------------------------
# inferir_estado_y_caducidad: integración
# ---------------------------------------------------------------------------


def test_inferir_integrado_caso_completo() -> None:
    """Expediente con dictamen + ingreso → estado=CON_DICTAMEN, caducidad calculada.

    Uso `hoy` cercano al ingreso para que caducidad NO haya vencido (sino
    la regla "fecha_caducidad < hoy → CADUCO" ganaría sobre CON_DICTAMEN).
    """
    expediente = _exp(
        fecha_ingreso=date(2024, 1, 1),
        tramite=[
            _ev(date(2024, 1, 1), "INGRESO A MESA DE ENTRADAS"),
            _ev(date(2024, 3, 1), "GIRO A COMISION"),
            _ev(date(2024, 5, 1), "DICTAMEN DE MAYORIA"),
        ],
    )
    inf = inferir_estado_y_caducidad(expediente, hoy=date(2024, 12, 1))
    assert inf.estado == EstadoExpediente.CON_DICTAMEN
    assert inf.fecha_caducidad_original == date(2024, 1, 1) + timedelta(days=730)
    assert inf.fecha_caducidad == inf.fecha_caducidad_original
    assert inf.prorrogado is False


def test_inferir_integrado_caduco_por_fecha_aunque_haya_dictamen() -> None:
    """Si la fecha_caducidad calculada ya pasó, gana CADUCO sobre CON_DICTAMEN."""
    expediente = _exp(
        fecha_ingreso=date(2022, 1, 1),  # caduca en 2024-01-01 + 730d ≈ 2024-01
        tramite=[
            _ev(date(2022, 3, 1), "DICTAMEN DE MAYORIA"),
        ],
    )
    inf = inferir_estado_y_caducidad(expediente, hoy=HOY)
    assert inf.estado == EstadoExpediente.CADUCO


def test_inferir_integrado_sin_fecha_ingreso_no_caduca() -> None:
    """Sin fecha_ingreso, los campos de caducidad son None y el estado no debería ser CADUCO."""
    expediente = _exp(
        fecha_ingreso=None,
        tramite=[_ev(date(2024, 1, 1), "INGRESO A MESA")],
    )
    inf = inferir_estado_y_caducidad(expediente, hoy=HOY)
    assert inf.fecha_caducidad is None
    assert inf.fecha_caducidad_original is None
    assert inf.prorrogado is False
    assert inf.estado == EstadoExpediente.INGRESADO


def test_inferir_no_muta_expediente() -> None:
    """`inferir_estado_y_caducidad` es función pura."""
    expediente = _exp(
        fecha_ingreso=date(2024, 1, 1),
        tramite=[_ev(date(2024, 5, 1), "DICTAMEN DE MAYORIA")],
    )
    estado_original = expediente.estado
    fecha_cad_original = expediente.fecha_caducidad
    inferir_estado_y_caducidad(expediente, hoy=HOY)
    # El expediente NO debería haber cambiado.
    assert expediente.estado == estado_original
    assert expediente.fecha_caducidad == fecha_cad_original
