"""ORM models SQLAlchemy 2.0.

Cada model vive acá; los mappers de/al dominio están en `mappers.py`.
Regla hexagonal: el dominio (`praxis.domain`) NUNCA importa de este módulo.

Ver `docs/adr/0003-persistencia.md`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from praxis.infrastructure.persistence.base import Base, TimestampsMixin, uuid7


class DespachoOrm(Base, TimestampsMixin, kw_only=True):
    """Despacho legislativo (tenant).

    No usa `TenantScopedMixin` porque el Despacho ES el tenant en sí.
    `kw_only=True` heredado pero re-declarado para que mypy entienda
    que los fields sin default pueden seguir a fields con default.
    """

    __tablename__ = "despacho"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    legislador_titular_slug: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    configuracion: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default_factory=dict
    )

    def __repr__(self) -> str:
        return f"DespachoOrm(id={self.id!r}, nombre={self.nombre!r})"


# Marker para que mypy entienda que existen variables `datetime` y `UUID` referenciadas
# por los mixins (TimestampsMixin aporta creado_en/actualizado_en como `datetime`).
_ = datetime  # type: ignore[unused-ignore]
