"""Schemas Pydantic para los endpoints `/bo`."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import (
    AreaTematica,
    PrioridadAccionabilidad,
    SeccionBO,
)


class NormaBODTO(BaseModel):
    """Snapshot de una norma BO. Sin cuerpo completo (ADR 0006)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fecha_publicacion: date
    seccion: SeccionBO
    tipo_norma: str
    numero_norma: str
    organismo_emisor: str
    sumario: str
    url_oficial: str
    capturado_en: datetime


class ClasificacionNormaBODTO(BaseModel):
    """Clasificación general de la norma — no depende del despacho."""

    model_config = ConfigDict(from_attributes=True)

    area_tematica: AreaTematica
    palabras_clave: list[str]
    afecta_expedientes_hcdn: bool
    referencias_legales: list[str]


class NormaBODetalleDTO(BaseModel):
    """Detalle estructurado de una norma. Incluye la clasificación
    cacheada si está. No incluye texto del cuerpo."""

    norma: NormaBODTO
    clasificacion: ClasificacionNormaBODTO | None


class NormaBOAccionableDTO(BaseModel):
    """Vista por despacho del scoring de accionabilidad. Tenant-scoped."""

    model_config = ConfigDict(from_attributes=True)

    norma_id: UUID
    despacho_id: UUID
    score: int = Field(ge=0, le=100)
    prioridad: PrioridadAccionabilidad
    razon: str
    expedientes_tocados: list[UUID]
    generado_en: datetime | None


class NormaBOAccionableConNormaDTO(BaseModel):
    """Pareo de accionable + norma para el GET /bo/accionables.

    Evita que el frontend tenga que hacer N+1 lookups para mostrar
    el listado del briefing."""

    accionable: NormaBOAccionableDTO
    norma: NormaBODTO


class ReclasificarPerfilResponse(BaseModel):
    """Resultado del POST /bo/normas/reclasificar-perfil."""

    fecha: date
    accionables_recalculadas: int
