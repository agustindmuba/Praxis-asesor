"""Tests unitarios del use case `EnriquecerExpediente`."""

from __future__ import annotations

from datetime import date

import pytest

from praxis.application.use_cases import EnriquecerExpediente
from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    NumeroExpediente,
    TipoExpediente,
    TramiteEvento,
)

pytestmark = pytest.mark.unit


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


def test_enriquecer_muta_campos_inferidos() -> None:
    expediente = _exp(
        fecha_ingreso=date(2024, 1, 1),
        tramite=[
            TramiteEvento(
                fecha=date(2024, 5, 1),
                camara=Camara.HCDN,
                evento="DICTAMEN DE MAYORIA",
            )
        ],
    )
    # Pre-condiciones: defaults.
    assert expediente.estado == EstadoExpediente.DESCONOCIDO
    assert expediente.fecha_caducidad is None
    assert expediente.prorrogado is False

    use_case = EnriquecerExpediente()
    # hoy cercano al ingreso para que caducidad no haya vencido (sino
    # ganaría CADUCO sobre CON_DICTAMEN).
    resultado = use_case.execute(expediente, hoy=date(2024, 12, 1))

    # Post-condiciones: campos enriquecidos.
    assert resultado is expediente  # devuelve el mismo objeto (chaining).
    assert expediente.estado == EstadoExpediente.CON_DICTAMEN
    assert expediente.fecha_caducidad is not None
    assert expediente.fecha_caducidad_original is not None
    assert expediente.prorrogado is False


def test_enriquecer_idempotente() -> None:
    """Ejecutar dos veces debe dar el mismo resultado."""
    expediente = _exp(
        fecha_ingreso=date(2024, 1, 1),
        tramite=[TramiteEvento(fecha=date(2024, 1, 1), camara=Camara.HCDN, evento="INGRESO")],
    )
    use_case = EnriquecerExpediente()
    use_case.execute(expediente, hoy=date(2026, 6, 1))
    primer_estado = expediente.estado
    primer_cad = expediente.fecha_caducidad
    use_case.execute(expediente, hoy=date(2026, 6, 1))
    assert expediente.estado == primer_estado
    assert expediente.fecha_caducidad == primer_cad


def test_enriquecer_sin_tramite_deja_estado_desconocido() -> None:
    """Sin trámite y antes de caducidad → DESCONOCIDO (default sin matches)."""
    expediente = _exp(fecha_ingreso=date(2024, 1, 1), tramite=[])
    EnriquecerExpediente().execute(expediente, hoy=date(2024, 12, 1))
    assert expediente.estado == EstadoExpediente.DESCONOCIDO
    # Caducidad sí se calcula porque hay fecha_ingreso.
    assert expediente.fecha_caducidad is not None
