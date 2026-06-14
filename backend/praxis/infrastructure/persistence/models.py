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
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
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
    legislador_foto_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
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
    # Texto completo del PDF parseado por `scripts/bajar_textos_completos`
    # (feat-48.4). Vacío cuando aún no se intentó descargar; el centinela
    # `__NO_DISPONIBLE__` marca PDFs que dieron 404 para evitar reintentos.
    texto_completo: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

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
# ExpedienteAreaTematica (cache de clasificación temática del LLM)
# ---------------------------------------------------------------------------


class ExpedienteAreaTematicaOrm(Base, kw_only=True):
    """Cache de clasificación temática por expediente.

    UNIQUE en `expediente_id`: una sola clasificación por expediente.
    Para reclasificar se borra primero (delete + insert).
    """

    __tablename__ = "expediente_area_tematica"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    expediente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("expediente.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    area: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1",
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return (
            f"ExpedienteAreaTematicaOrm(id={self.id!r}, "
            f"expediente_id={self.expediente_id!r}, area={self.area!r})"
        )


# ---------------------------------------------------------------------------
# OrdenDelDia + Briefing (feat/29 — spec 14)
# ---------------------------------------------------------------------------


class OrdenDelDiaOrm(Base, kw_only=True):
    """Lista de expedientes a tratar en una sesión específica.

    Tenant-scoped: el OD lo carga (manual o automatic) cada despacho para
    su propio briefing. Si en el futuro queremos compartir el OD entre
    despachos del mismo bloque, hay que relajar esta restricción.

    `expedientes_ids` se persiste como JSON (array de UUIDs serializados
    como string). Suficiente para v1 — el OD típico tiene 30-60
    expedientes y no se filtra por contenido.
    """

    __tablename__ = "orden_del_dia"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    despacho_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    camara: Mapped[str] = mapped_column(String(10), nullable=False)
    fecha_sesion: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora_sesion: Mapped[Any] = mapped_column(Time, nullable=True, default=None)
    titulo: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    fuente: Mapped[str] = mapped_column(
        String(30), nullable=False, default="upload_manual",
    )
    expedientes_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    # id_sesion del portal HCDN para idempotencia (feat-45.3).
    id_sesion_externa: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return (
            f"OrdenDelDiaOrm(id={self.id!r}, camara={self.camara!r}, "
            f"fecha={self.fecha_sesion!r}, n={len(self.expedientes_ids)})"
        )


class BriefingOrm(Base, kw_only=True):
    """Snapshot del briefing pre-sesión para un (despacho, OD).

    UNIQUE compuesto (despacho_id, orden_del_dia_id) — un briefing por
    despacho por OD. Regenerar = delete + insert.

    `contenido` guarda como JSON serializado todo el output del use case
    (alertas, secciones de proyectos, secciones de áreas). Pensado para
    inmutabilidad: el briefing es un snapshot temporal.
    """

    __tablename__ = "briefing"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden_del_dia_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("orden_del_dia.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    modelo_llm: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1",
    )
    contenido: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "despacho_id", "orden_del_dia_id", name="uq_briefing_despacho_od",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"BriefingOrm(id={self.id!r}, despacho_id={self.despacho_id!r}, "
            f"od_id={self.orden_del_dia_id!r})"
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


# ---------------------------------------------------------------------------
# Perfil de interés del despacho (compartido entre specs 15, 16, 17).
# ---------------------------------------------------------------------------


class PerfilInteresDespachoOrm(Base, TimestampsMixin, kw_only=True):
    """Perfil declarativo del despacho — D1 sembrado híbrido + editable.

    PK = `despacho_id` (una fila por despacho).
    Listas se serializan a JSON: SQLite-friendly y suficiente para
    perfiles chicos (≤20 áreas/comisiones/aliases típicamente).
    """

    __tablename__ = "perfil_interes_despacho"

    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
    )
    areas_tematicas: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    comisiones_legislador: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    distritos_observados: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    aliases_legislador: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    sembrado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    editado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )

    def __repr__(self) -> str:
        return f"PerfilInteresDespachoOrm(despacho_id={self.despacho_id!r})"


# ---------------------------------------------------------------------------
# Perfil OPOSITOR del despacho (feat-42.1 — distinto del de interés).
# ---------------------------------------------------------------------------


class PerfilOpositorDespachoOrm(Base, TimestampsMixin, kw_only=True):
    """Perfil narrativo del despacho — qué milita, contra qué, con qué tono.

    Generado por bot (Sonnet sobre huella parlamentaria) y editado por
    asesor. 1 fila por despacho. Listas + figuras como JSON.
    """

    __tablename__ = "perfil_opositor_despacho"

    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bandera_principal: Mapped[str] = mapped_column(Text, nullable=False)
    banderas_secundarias: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    temas_de_cuidado: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    tono_comunicacional: Mapped[str] = mapped_column(
        String(40), nullable=False, default="mixto",
    )
    adversarios: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    aliados: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    linea_de_bloque: Mapped[str] = mapped_column(Text, nullable=False, default="")
    justificacion_evidencia: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    advertencias: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    confianza_global: Mapped[str] = mapped_column(
        String(10), nullable=False, default="media",
    )
    inferido_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    editado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    modelo_inferencia: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="v1",
    )

    def __repr__(self) -> str:
        return f"PerfilOpositorDespachoOrm(despacho_id={self.despacho_id!r})"


# ---------------------------------------------------------------------------
# Accionable enriquecido con perfil opositor (feat-42.2 — A+B+F).
# ---------------------------------------------------------------------------


class AccionableEventoOrm(Base, kw_only=True):
    """Accionable generado por LLM sobre un evento (norma BO o artículo).

    Polimórfico por `(tipo_evento, evento_id)`. UNIQUE en
    `(despacho_id, tipo_evento, evento_id)` → 1 por evento por despacho.
    Regeneración = upsert.
    """

    __tablename__ = "accionable_evento"
    __table_args__ = (
        UniqueConstraint(
            "despacho_id", "tipo_evento", "evento_id",
            name="uq_accionable_evento_despacho_evento",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo_evento: Mapped[str] = mapped_column(String(20), nullable=False)
    evento_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)

    razon_para_despacho: Mapped[str] = mapped_column(Text, nullable=False)
    accion_sugerida: Mapped[str] = mapped_column(String(40), nullable=False)
    explicacion_accion: Mapped[str] = mapped_column(Text, nullable=False)
    tweets_sugeridos: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    confianza: Mapped[str] = mapped_column(
        String(10), nullable=False, default="media",
    )

    generado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    editado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    modelo: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="v1",
    )
    # Feedback del asesor (feat-43.2)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente",
    )
    nota_asesor: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None,
    )
    marcado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_func_now(),
        init=False,
    )

    def __repr__(self) -> str:
        return (
            f"AccionableEventoOrm(id={self.id!r}, despacho_id={self.despacho_id!r}, "
            f"tipo={self.tipo_evento!r}, evento={self.evento_id!r})"
        )


# ---------------------------------------------------------------------------
# Proyecto en redacción (feat-42.3 — asistente de redacción).
# ---------------------------------------------------------------------------


class ProyectoRedaccionOrm(Base, kw_only=True):
    """Borrador interno de un proyecto parlamentario en redacción.

    Articulado y cofirmantes_sugeridos van como JSON arrays.
    """

    __tablename__ = "proyecto_redaccion"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    sumario: Mapped[str] = mapped_column(Text, nullable=False)
    articulado: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    fundamentos: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cofirmantes_sugeridos: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    estado: Mapped[str] = mapped_column(
        String(15), nullable=False, default="borrador",
    )
    autor_legislador: Mapped[str] = mapped_column(
        String(120), nullable=False, default="",
    )
    modelo_asistente: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None,
    )
    prompt_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="v1",
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_func_now(),
        init=False,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_func_now(),
        onupdate=sa_func_now(),
        init=False,
    )

    def __repr__(self) -> str:
        return (
            f"ProyectoRedaccionOrm(id={self.id!r}, tipo={self.tipo!r}, "
            f"titulo={self.titulo[:30]!r})"
        )


# ---------------------------------------------------------------------------
# Boletín Oficial (spec 15)
# ---------------------------------------------------------------------------


class NormaBOOrm(Base, kw_only=True):
    """Snapshot de una norma publicada en el BO."""

    __tablename__ = "norma_bo"
    __table_args__ = (
        Index(
            "uq_norma_bo_identidad_natural",
            "fecha_publicacion", "seccion", "tipo_norma", "numero_norma",
            unique=True,
        ),
        Index("ix_norma_bo_fecha_seccion", "fecha_publicacion", "seccion"),
        # NO unique: 2 normas distintas (números distintos) pueden tener
        # el mismo sumario corto (ej. "Recházase recurso" en 5 decretos
        # de un mismo día). El hash sigue siendo útil como índice de
        # búsqueda y cache de clasificación.
        Index("ix_norma_bo_hash_sumario", "hash_sumario"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    fecha_publicacion: Mapped[date] = mapped_column(Date, nullable=False)
    seccion: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo_norma: Mapped[str] = mapped_column(String(80), nullable=False)
    numero_norma: Mapped[str] = mapped_column(String(80), nullable=False)
    organismo_emisor: Mapped[str] = mapped_column(String(400), nullable=False)
    sumario: Mapped[str] = mapped_column(Text, nullable=False)
    url_oficial: Mapped[str] = mapped_column(String(1000), nullable=False)
    hash_sumario: Mapped[str] = mapped_column(String(64), nullable=False)
    capturado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return (
            f"NormaBOOrm(id={self.id!r}, "
            f"fecha={self.fecha_publicacion!r}, "
            f"seccion={self.seccion!r}, numero={self.numero_norma!r})"
        )


class NormaBOTextoOrm(Base, kw_only=True):
    """Cuerpo completo del texto. Tabla aparte (ADR 0006 §D2)."""

    __tablename__ = "norma_bo_texto"

    norma_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("norma_bo.id", ondelete="CASCADE"),
        primary_key=True,
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    capturado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )

    def __repr__(self) -> str:
        return f"NormaBOTextoOrm(norma_id={self.norma_id!r})"


class ClasificacionNormaBOOrm(Base, kw_only=True):
    """Cache de clasificación general de una norma BO."""

    __tablename__ = "clasificacion_norma_bo"
    __table_args__ = (
        UniqueConstraint("norma_id", name="uq_clasif_norma_bo_norma_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    norma_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("norma_bo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    area_tematica: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    palabras_clave: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    afecta_expedientes_hcdn: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    referencias_legales: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="v1",
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


class NormaBOAccionableOrm(Base, kw_only=True):
    """Vista por despacho del scoring. PK compuesta tenant-scoped."""

    __tablename__ = "norma_bo_accionable"
    __table_args__ = (
        Index(
            "ix_accionable_despacho_fecha",
            "despacho_id",
        ),
    )

    norma_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("norma_bo.id", ondelete="CASCADE"),
        primary_key=True,
    )
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False)
    razon: Mapped[str] = mapped_column(String(200), nullable=False)
    expedientes_tocados: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


# ---------------------------------------------------------------------------
# Noticias + Menciones (spec 16)
# ---------------------------------------------------------------------------


class FuenteNoticiaOrm(Base, TimestampsMixin, kw_only=True):
    """Un medio monitoreado. Catálogo global + extensión por despacho."""

    __tablename__ = "fuente_noticia"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    dominio: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    alcance: Mapped[str] = mapped_column(String(20), nullable=False)
    modo_acceso: Mapped[str] = mapped_column(String(20), nullable=False)
    feed_url: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
    distrito: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    robots_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ultima_revision: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"FuenteNoticiaOrm(id={self.id!r}, dominio={self.dominio!r})"


class FuenteNoticiaDespachoOrm(Base, kw_only=True):
    """Puente: fuentes distritales agregadas por un despacho."""

    __tablename__ = "fuente_noticia_despacho"

    fuente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("fuente_noticia.id", ondelete="CASCADE"),
        primary_key=True,
    )
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    agregada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


class ArticuloOrm(Base, kw_only=True):
    """Snapshot mínimo de un artículo.

    Sin columna texto_completo (restricción legal, ADR 0006).
    """

    __tablename__ = "articulo"
    __table_args__ = (
        Index("uq_articulo_hash", "hash_dedup", unique=True),
        Index("ix_articulo_fuente_capturado", "fuente_id", "capturado_en"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    fuente_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("fuente_noticia.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    titulo: Mapped[str] = mapped_column(String(1000), nullable=False)
    bajada_propia: Mapped[str | None] = mapped_column(
        String(400), nullable=True, default=None,
    )
    publicado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    capturado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )
    hash_dedup: Mapped[str] = mapped_column(String(64), nullable=False)


class ArticuloHashOrm(Base, kw_only=True):
    """Dedup forever: la URL ya se vio aunque el artículo se purgue.

    Retención: forever. La tabla `articulo` purga a los 12 meses (D10).
    Este hash queda para evitar reprocesar URLs vistas previamente.
    """

    __tablename__ = "articulo_hash"

    hash_dedup: Mapped[str] = mapped_column(String(64), primary_key=True)
    visto_por_primera_vez: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


class ClasificacionArticuloOrm(Base, kw_only=True):
    """Cache de clasificación general de un artículo."""

    __tablename__ = "clasificacion_articulo"
    __table_args__ = (
        UniqueConstraint("articulo_id", name="uq_clasif_articulo_articulo_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    articulo_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("articulo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    area_tematica: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    palabras_clave: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="v1",
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


class ArticuloRelevanteOrm(Base, kw_only=True):
    """Vista por despacho. Análoga a NormaBOAccionable."""

    __tablename__ = "articulo_relevante"

    articulo_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("articulo.id", ondelete="CASCADE"),
        primary_key=True,
    )
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    razon: Mapped[str] = mapped_column(String(200), nullable=False)
    expedientes_tocados: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


class MencionOrm(Base, kw_only=True):
    """Mención de un legislador en un artículo."""

    __tablename__ = "mencion"
    __table_args__ = (
        Index("ix_mencion_despacho_detectado", "despacho_id", "detectado_en"),
        Index("ix_mencion_legislador_detectado", "legislador_id", "detectado_en"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    articulo_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("articulo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # legislador_id no tiene FK estricta v1 — el catálogo de legisladores
    # vive en CSV vendored (`feat/05`), no en DB. Sigue el patrón de
    # `voto_legislador.legislador_nombre` (ADR 0005 §"Por qué no FK
    # estricta").
    legislador_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
    )
    snippet_contexto: Mapped[str] = mapped_column(String(400), nullable=False)
    tono: Mapped[str] = mapped_column(String(15), nullable=False)
    confianza_tono: Mapped[float] = mapped_column(Float, nullable=False)
    alcance_medio: Mapped[str] = mapped_column(String(20), nullable=False)
    detectado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )
    notificada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------------------
# WhatsApp (spec 17)
# ---------------------------------------------------------------------------


class DestinatarioOrm(Base, TimestampsMixin, kw_only=True):
    """Persona del despacho que recibe mensajes Praxis por WhatsApp."""

    __tablename__ = "destinatario"
    __table_args__ = (
        UniqueConstraint(
            "despacho_id", "telefono_e164",
            name="uq_destinatario_despacho_telefono",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    rol_interno: Mapped[str] = mapped_column(String(40), nullable=False)
    telefono_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    recibe_briefing_diario: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    recibe_alertas_menciones: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    recibe_alertas_otras: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    opt_in_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    opt_out_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PlantillaWhatsAppOrm(Base, kw_only=True):
    """Plantilla pre-aprobada por Meta. Catálogo interno."""

    __tablename__ = "plantilla_whatsapp"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    idioma: Mapped[str] = mapped_column(String(10), nullable=False, default="es_AR")
    categoria: Mapped[str] = mapped_column(String(20), nullable=False)
    body_params: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    estado_meta: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pendiente_aprobacion",
    )
    aprobada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    contenido_referencia: Mapped[str] = mapped_column(Text, nullable=False)


class EnvioWhatsAppOrm(Base, kw_only=True):
    """Registro auditable de envíos. despacho_id desnormalizado (ADR 0006)."""

    __tablename__ = "envio_whatsapp"
    __table_args__ = (
        Index(
            "ix_envio_whatsapp_message_id_meta",
            "message_id_meta",
            unique=True,
        ),
        Index(
            "ix_envio_whatsapp_despacho_enviado",
            "despacho_id", "enviado_en",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    destinatario_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("destinatario.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Desnormalizado para queries tenant-scoped sin JOIN (ADR 0006).
    despacho_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("despacho.id", ondelete="CASCADE"),
        nullable=False,
    )
    plantilla_name: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("plantilla_whatsapp.name", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_params: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default_factory=dict,
    )
    correlativo_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, default=None,
    )
    enviado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
    estado: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pendiente",
    )
    message_id_meta: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class AlertaMencionEnviadaOrm(Base, kw_only=True):
    """Auditoría de alertas de mención efectivamente enviadas.

    Para alertas individuales, `menciones_ids` tiene 1 elemento. Para
    agrupadas, N. La FK al destinatario es cascade; las menciones se
    referencian por UUID en JSON (no FK estricta — la mención puede
    purgarse a los 24 meses, D10).
    """

    __tablename__ = "alerta_mencion_enviada"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    destinatario_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("destinatario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    menciones_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    plantilla_meta: Mapped[str] = mapped_column(String(100), nullable=False)
    enviado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class EfemerideOrm(Base, kw_only=True):
    """Efemérides — fechas conmemorativas (feat-53.1).

    Únicas por (mes, dia, titulo) — dos efemérides el mismo día son
    posibles. `anio_unico` distingue las recurrentes (NULL) de los
    aniversarios puntuales (ej. 50° del Golpe en 2026).
    """

    __tablename__ = "efemeride"
    __table_args__ = (
        Index(
            "uq_efemeride_fecha_titulo",
            "mes",
            "dia",
            "titulo",
            unique=True,
        ),
        Index("ix_efemeride_mes_dia", "mes", "dia"),
        Index("ix_efemeride_tipo", "tipo"),
        Index("ix_efemeride_relevancia", "relevancia"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default_factory=uuid7)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dia: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    relevancia: Mapped[str] = mapped_column(String(10), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    fuente: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    # Lista de strings (áreas temáticas). JSON evita una M:N que no
    # aporta — el set de áreas es chico y estable.
    areas_tematicas: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default_factory=list,
    )
    # NULL = se repite todos los años. Año específico = aniversario puntual.
    anio_unico: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default=sa_func_now(),
    )


# Marker para que mypy/ruff entiendan que estos imports son legítimos.
_ = datetime  # type: ignore[unused-ignore]
