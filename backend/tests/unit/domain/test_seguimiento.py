"""Tests unitarios de SeguimientoExpediente y Prioridad."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from praxis.domain import Prioridad, SeguimientoExpediente

pytestmark = pytest.mark.unit


def test_prioridad_valores() -> None:
    assert Prioridad.ALTA.value == "alta"
    assert Prioridad.MEDIA.value == "media"
    assert Prioridad.BAJA.value == "baja"


def test_seguimiento_minimo() -> None:
    s = SeguimientoExpediente(
        id=uuid4(),
        despacho_id=uuid4(),
        expediente_id=uuid4(),
    )
    assert s.responsable_id is None
    assert s.prioridad == Prioridad.MEDIA
    assert s.archivado is False


def test_seguimiento_completo() -> None:
    now = datetime.now(UTC)
    s = SeguimientoExpediente(
        id=uuid4(),
        despacho_id=uuid4(),
        expediente_id=uuid4(),
        responsable_id=uuid4(),
        prioridad=Prioridad.ALTA,
        archivado=False,
        creado_en=now,
    )
    assert s.prioridad == Prioridad.ALTA
    assert s.creado_en == now


def test_seguimiento_es_mutable() -> None:
    s = SeguimientoExpediente(id=uuid4(), despacho_id=uuid4(), expediente_id=uuid4())
    s.archivado = True
    assert s.archivado is True
