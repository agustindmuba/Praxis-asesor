"""ORM models SQLAlchemy 2.0.

Cada model vive acá; los mappers de/al dominio están en `mappers.py`.
Regla hexagonal: el dominio (`praxis.domain`) NUNCA importa de este módulo.

Ver `docs/adr/0003-persistencia.md`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from praxis.infrastructure.persistence.base import Base, TimestampsMixin, uuid7

# ---------------------------------------------------------------------------
# Despacho (tenant)
# ---------------------------------------------------------------------------


class DespachoOrm(Base, TimestampsMixin, kw_only=True):
    """Despacho legislativo (tenant)."""

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


# ---------------------------------------------------------------------------
# Expediente (catálogo global, no tenant-scoped)
# ---------------------------------------------------------------------------


class ExpedienteOrm(Base, TimestampsMixin, kw_only=True):
    """Expediente parlamentario. UUID PK + UNIQUE en identidad natural."""

    __tablename__ = "expediente"
    __table_args__ = (
        Index(
            "uq_expediente_numero",
            "numero",
            "origen",
            "anio",
            "camara",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)

    # Identidad natural (NumeroExpediente del dominio, explotada en columnas).
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    origen: Mapped[str] = mapped_column(String(10), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    camara: Mapped[str] = mapped_column(String(10), nullable=False)

    # Atributos del expediente.
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    titulo: Mapped[str] = mapped_column(String(2000), nullable=False)
    sumario: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    estado: Mapped[str] = mapped_column(String(40), nullable=False, default="desconocido")
    texto_url: Mapped[str | None] = mapped_column(String(2000), nullable=True, default=None)
    fuente_url: Mapped[str | None] = mapped_column(String(2000), nullable=True, default=None)

    # Caducidad (Amendment 1 del ADR 0002).
    fecha_caducidad: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    fecha_caducidad_original: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    prorrogado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relaciones: hijos del expediente. Cascade para que un INSERT del padre
    # con hijos en memoria se persista en un solo flush.
    firmantes: Mapped[list[FirmanteOrm]] = relationship(
        "FirmanteOrm",
        back_populates="expediente",
        cascade="all, delete-orphan",
        default_factory=list,
    )
    giros: Mapped[list[GiroOrm]] = relationship(
        "GiroOrm",
        back_populates="expediente",
        cascade="all, delete-orphan",
        default_factory=list,
    )
    tramite: Mapped[list[TramiteEventoOrm]] = relationship(
        "TramiteEventoOrm",
        back_populates="expediente",
        cascade="all, delete-orphan",
        default_factory=list,
    )

    def __repr__(self) -> str:
        return (
            f"ExpedienteOrm(id={self.id!r}, "
            f"numero={self.numero!r}, origen={self.origen!r}, anio={self.anio!r})"
        )


class FirmanteOrm(Base, kw_only=True):
    """Firmante de un expediente."""

    __tablename__ = "firmante"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    # init=False: la FK la rellena SQLAlchemy vía la relationship back_populates
    # cuando el padre se persiste. No es parte del constructor de Python.
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        init=False,
    )
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    distrito: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    bloque: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    expediente: Mapped[ExpedienteOrm] = relationship(
        "ExpedienteOrm",
        back_populates="firmantes",
        default=None,
    )


class GiroOrm(Base, kw_only=True):
    """Giro de un expediente a una comisión."""

    __tablename__ = "giro"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    # init=False: la FK la rellena SQLAlchemy vía la relationship back_populates
    # cuando el padre se persiste. No es parte del constructor de Python.
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        init=False,
    )
    comision: Mapped[str] = mapped_column(String(300), nullable=False)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    fecha_egreso: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    orden: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    expediente: Mapped[ExpedienteOrm] = relationship(
        "ExpedienteOrm",
        back_populates="giros",
        default=None,
    )


class TramiteEventoOrm(Base, kw_only=True):
    """Evento en el trámite de un expediente. Append-only por design."""

    __tablename__ = "tramite_evento"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    # init=False: la FK la rellena SQLAlchemy vía la relationship back_populates
    # cuando el padre se persiste. No es parte del constructor de Python.
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        init=False,
    )
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    camara: Mapped[str] = mapped_column(String(10), nullable=False)
    evento: Mapped[str] = mapped_column(String(500), nullable=False)
    detalle: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    fuente: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)

    expediente: Mapped[ExpedienteOrm] = relationship(
        "ExpedienteOrm",
        back_populates="tramite",
        default=None,
    )


# Marker para que mypy/ruff entiendan que estos imports son legítimos.
_ = datetime  # type: ignore[unused-ignore]
