"""ORM models SQLAlchemy 2.0.

Cada model vive acá; los mappers de/al dominio están en `mappers.py`.
Regla hexagonal: el dominio (`praxis.domain`) NUNCA importa de este módulo.

Ver `docs/adr/0003-persistencia.md`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy import func as sa_func_now_module
from sqlalchemy.orm import Mapped, mapped_column, relationship

from praxis.infrastructure.persistence.base import Base, TimestampsMixin, uuid7

# Alias para legibilidad en server_default.
sa_func_now = sa_func_now_module.now

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
# Usuario y MembresiaDespacho
# ---------------------------------------------------------------------------


class UsuarioOrm(Base, TimestampsMixin, kw_only=True):
    """Usuario humano del sistema."""

    __tablename__ = "usuario"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    auth_provider_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True, unique=True, default=None, index=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"UsuarioOrm(id={self.id!r}, email={self.email!r})"


class MembresiaDespachoOrm(Base, kw_only=True):
    """Pertenencia Usuario ↔ Despacho con rol.

    PK compuesto (usuario_id, despacho_id). Un usuario pertenece a múltiples
    despachos, cada uno con rol propio.
    """

    __tablename__ = "membresia_despacho"

    usuario_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("usuario.id", ondelete="CASCADE"),
        primary_key=True,
    )
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    rol: Mapped[str] = mapped_column(String(30), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return (
            f"MembresiaDespachoOrm(usuario_id={self.usuario_id!r}, "
            f"despacho_id={self.despacho_id!r}, rol={self.rol!r})"
        )


# ---------------------------------------------------------------------------
# SeguimientoExpediente (tenant-scoped)
# ---------------------------------------------------------------------------


class SeguimientoExpedienteOrm(Base, TimestampsMixin, kw_only=True):
    """Seguimiento de un expediente por un despacho.

    Tenant-scoped: tiene `despacho_id` no-opcional. UNIQUE en
    (despacho_id, expediente_id) — un despacho no puede marcar el mismo
    expediente dos veces.
    """

    __tablename__ = "seguimiento_expediente"
    __table_args__ = (
        Index(
            "uq_seguimiento_despacho_expediente",
            "despacho_id",
            "expediente_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    responsable_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False, default="media")
    archivado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (
            f"SeguimientoExpedienteOrm(id={self.id!r}, "
            f"despacho_id={self.despacho_id!r}, expediente_id={self.expediente_id!r})"
        )


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


# ---------------------------------------------------------------------------
# ResumenEjecutivo (cache de output de LLM por expediente)
# ---------------------------------------------------------------------------


class ResumenEjecutivoOrm(Base, kw_only=True):
    """Resumen generado por un LLM sobre un Expediente.

    UNIQUE en `expediente_id`: a lo sumo un resumen por expediente; para
    regenerar se borra el viejo primero. No tiene `actualizado_en` porque
    es inmutable (cada cambio es un delete+insert).
    """

    __tablename__ = "resumen_ejecutivo"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    contenido_md: Mapped[str] = mapped_column(Text, nullable=False)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return (
            f"ResumenEjecutivoOrm(id={self.id!r}, "
            f"expediente_id={self.expediente_id!r}, modelo={self.modelo!r})"
        )


# ---------------------------------------------------------------------------
# Votacion + VotoLegislador (ADR 0005)
# ---------------------------------------------------------------------------


class VotacionOrm(Base, kw_only=True):
    """Una votación nominal del recinto.

    Inmutable: los conteos del portal son históricos. Para "actualizar"
    se borra y se vuelve a insertar.

    `acta_id_hcdn` es UNIQUE — es la llave natural del portal y evita
    duplicados. `expediente_id` queda NULL si no se pudo cruzar (el
    cruce es vía `titulo_od` → `OrdenDelDia`, diferido).
    """

    __tablename__ = "votacion"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    camara: Mapped[str] = mapped_column(String(10), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    sesion: Mapped[str] = mapped_column(String(200), nullable=False)
    asunto: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    resultado_afirmativos: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado_negativos: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado_abstenciones: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado_sin_votar: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado_ausentes: Mapped[int] = mapped_column(Integer, nullable=False)
    aprobada: Mapped[bool] = mapped_column(Boolean, nullable=False)
    presidida_por: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    expediente_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    titulo_od: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None, index=True,
    )
    acta_id_hcdn: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, unique=True
    )
    acta_pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    fuente_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    votos: Mapped[list[VotoLegisladorOrm]] = relationship(
        "VotoLegisladorOrm",
        back_populates="votacion",
        cascade="all, delete-orphan",
        default_factory=list,
    )

    __table_args__ = (
        Index("ix_votacion_camara_fecha", "camara", "fecha"),
    )

    def __repr__(self) -> str:
        return (
            f"VotacionOrm(id={self.id!r}, camara={self.camara!r}, "
            f"fecha={self.fecha!r}, acta_id_hcdn={self.acta_id_hcdn!r})"
        )


class VotoLegisladorOrm(Base, kw_only=True):
    """Cómo votó UN legislador en UNA votación.

    PK compuesta: (votacion_id, legislador_nombre). Sin FK a `Legislador`
    canónico todavía — deuda asumida en ADR 0005.
    """

    __tablename__ = "voto_legislador"

    votacion_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("votacion.id", ondelete="CASCADE"),
        primary_key=True,
        init=False,
    )
    legislador_nombre: Mapped[str] = mapped_column(String(200), primary_key=True)
    voto: Mapped[str] = mapped_column(String(20), nullable=False)
    bloque: Mapped[str | None] = mapped_column(String(150), nullable=True, default=None, index=True)
    distrito: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    que_dijo: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    legislador_hcdn_id: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)

    votacion: Mapped[VotacionOrm] = relationship(
        "VotacionOrm",
        back_populates="votos",
        default=None,
    )


# Marker para que mypy/ruff entiendan que estos imports son legítimos.
_ = datetime  # type: ignore[unused-ignore]
