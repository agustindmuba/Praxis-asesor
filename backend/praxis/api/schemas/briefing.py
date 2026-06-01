"""DTOs Pydantic del briefing pre-sesión + OrdenDelDia."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import (
    AreaTematica,
    Camara,
    EstadoExpediente,
    PrioridadAlerta,
    RecomendacionVoto,
    RolEnDespacho,
    TipoExpediente,
)
from praxis.domain.orden_del_dia import FuenteOd

# ---------------------------------------------------------------------------
# OrdenDelDia
# ---------------------------------------------------------------------------


class OrdenDelDiaCrear(BaseModel):
    """Request body: el asesor pega/sube los expedientes del OD.

    `expedientes_ids` puede venir vacío en el wire — el server hace
    validación adicional (existencia de los IDs).
    """

    camara: Camara
    fecha_sesion: date
    expedientes_ids: list[UUID] = Field(default_factory=list, min_length=1)
    hora_sesion: time | None = None
    titulo: str | None = None


class OrdenDelDiaDTO(BaseModel):
    """OrdenDelDia hidratado."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    camara: Camara
    fecha_sesion: date
    hora_sesion: time | None
    titulo: str | None
    fuente: FuenteOd
    expedientes_ids: list[UUID]
    creado_en: datetime | None


# ---------------------------------------------------------------------------
# NumeroExpediente (re-export para briefing)
# ---------------------------------------------------------------------------


class NumeroExpedienteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    numero: int
    origen: str
    anio: int
    camara: Camara


# ---------------------------------------------------------------------------
# Value objects del briefing
# ---------------------------------------------------------------------------


class AlertaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    prioridad: PrioridadAlerta
    titulo: str
    detalle: str
    expediente_id: UUID | None


class CofirmanteSugeridoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nombre: str
    bloque: str | None
    distrito: str | None
    proyectos_similares_firmados: int
    razon: str


class AntecedenteParecidoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    numero: NumeroExpedienteDTO
    titulo: str
    estado_terminal: EstadoExpediente
    similitud: float


class SeccionProyectoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    expediente_id: UUID
    numero: NumeroExpedienteDTO
    titulo: str
    estado: EstadoExpediente
    tipo: TipoExpediente
    rol_despacho: RolEnDespacho
    area: AreaTematica
    dias_en_etapa: int | None
    argumentos: list[str]
    contraargumentos: list[str]
    cofirmantes_naturales: list[CofirmanteSugeridoDTO]
    antecedente: AntecedenteParecidoDTO | None


class ProyectoEnAreaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    expediente_id: UUID
    numero: NumeroExpedienteDTO
    titulo: str
    autor_principal: str | None
    bloque_autor: str | None
    recomendacion: RecomendacionVoto
    razon: str


class SeccionAreaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    area: AreaTematica
    proyectos: list[ProyectoEnAreaDTO]


# ---------------------------------------------------------------------------
# Briefing (response del endpoint)
# ---------------------------------------------------------------------------


class BriefingCrear(BaseModel):
    """Request body: pedido de generar/recuperar el briefing."""

    orden_del_dia_id: UUID
    regenerar: bool = False


class BriefingDTO(BaseModel):
    """Briefing completo. Es lo que el frontend renderiza a PDF."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    despacho_id: UUID
    orden_del_dia_id: UUID
    modelo_llm: str
    prompt_version: str
    generado_en: datetime | None

    proyectos_del_despacho_total: int
    proyectos_como_autor: int
    proyectos_como_cofirmante: int

    alertas: list[AlertaDTO]
    secciones_proyectos: list[SeccionProyectoDTO]
    secciones_areas: list[SeccionAreaDTO]
