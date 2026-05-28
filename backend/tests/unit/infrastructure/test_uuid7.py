"""Tests de la generación de UUID v7."""

from __future__ import annotations

import time
from uuid import UUID

import pytest

from praxis.infrastructure.persistence.base import uuid7

pytestmark = pytest.mark.unit


def test_uuid7_devuelve_uuid_valido() -> None:
    u = uuid7()
    assert isinstance(u, UUID)


def test_uuid7_version_es_7() -> None:
    u = uuid7()
    # El nibble de versión está en los 4 bits del medio del 7mo octet.
    assert u.version == 7


def test_uuid7_variant_correcto() -> None:
    """UUID v7 usa RFC 4122 variant (0b10..)."""
    u = uuid7()
    # `variant` debería ser "specified in RFC 4122" → bits son 10..
    assert u.variant == "specified in RFC 4122"


def test_uuid7_es_time_ordered() -> None:
    """Dos UUIDs generados en momentos diferentes deben ser ordenables
    por timestamp (con suficiente diferencia temporal entre ellos)."""
    u1 = uuid7()
    time.sleep(0.01)  # 10ms para garantizar timestamp distinto
    u2 = uuid7()
    # Como hex strings deben ser comparables lexicográficamente.
    assert str(u1) < str(u2)


def test_uuid7_es_unico() -> None:
    """100 generaciones consecutivas deben dar 100 UUIDs distintos."""
    uuids = {uuid7() for _ in range(100)}
    assert len(uuids) == 100
