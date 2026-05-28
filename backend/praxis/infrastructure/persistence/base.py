"""Base SQLAlchemy + helpers compartidos por todos los ORM models.

Ver `docs/adr/0003-persistencia.md`:
- §1 ID strategy: UUID v7 generado en aplicación.
- §4 Tenancy enforcement: `TenantScopedMixin` para entidades que pertenecen
  a un despacho.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, declared_attr, mapped_column

# ---------------------------------------------------------------------------
# UUID v7 (RFC 9562 draft)
# ---------------------------------------------------------------------------


def uuid7() -> UUID:
    """Genera un UUID v7 (time-ordered) en Python puro.

    Layout (128 bits):
        bits 80-127: unix timestamp en milisegundos (48 bits)
        bits 76-79:  version (= 7, 4 bits)
        bits 64-75:  rand_a (12 bits aleatorios)
        bits 62-63:  variant (= 0b10, 2 bits)
        bits 0-61:   rand_b (62 bits aleatorios)

    Property garantizada: dos UUIDs generados en milisegundos distintos
    son ordenables por timestamp con comparación entera/lexicográfica
    sobre su representación hex.

    Cuando Python 3.13+ esté en uso stable, reemplazar por `uuid.uuid7()`
    de stdlib.
    """
    ts_ms = (time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    rand_bits = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand_bits >> 62) & 0x0FFF
    rand_b = rand_bits & ((1 << 62) - 1)
    value = (
        (ts_ms << 80)  # timestamp en top
        | (0x7 << 76)  # version
        | (rand_a << 64)
        | (0x2 << 62)  # variant
        | rand_b
    )
    return UUID(int=value)


# ---------------------------------------------------------------------------
# Base SQLAlchemy
# ---------------------------------------------------------------------------


class Base(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """Base para todos los ORM models.

    `MappedAsDataclass` hace que cada model sea también un dataclass —
    permite inicialización con keyword args y `__repr__` automático,
    similar al estilo del dominio.

    `kw_only=True` evita el problema de "non-default field after default field"
    cuando los mixins aportan columnas con `default_factory` (timestamps, id).
    """


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TimestampsMixin(MappedAsDataclass):
    """Aporta `creado_en` y `actualizado_en` automáticos (server-side)."""

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenantScopedMixin(MappedAsDataclass):
    """Aporta `despacho_id` no-opcional. Para usar en TODA entidad que
    pertenezca a un despacho (seguimiento, nota, alerta, audit_log, etc.).

    El filter `WHERE despacho_id = :despacho_id` es responsabilidad explícita
    del repositorio (ver ADR 0003 §4). El mixin solo garantiza que la columna
    existe y es no-nullable.
    """

    @declared_attr
    @classmethod
    def despacho_id(cls) -> Mapped[UUID]:
        return mapped_column(Uuid, nullable=False, index=True)
