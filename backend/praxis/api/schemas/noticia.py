"""Schemas Pydantic para los endpoints `/noticias` y `/menciones`.

Reflejan estrictamente lo que vive en DB (ADR 0006): metadata +
`bajada_propia` ≤240 chars + `snippet_contexto` ≤200 chars. **NUNCA**
exponen el cuerpo del artículo (no se persiste).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import (
    AlcanceMedio,
    AreaTematica,
    ModoAccesoFuente,
    TipoFuenteNoticia,
    TonoMencion,
)

# ---------------------------------------------------------------------------
# FuenteNoticia
# ---------------------------------------------------------------------------


class FuenteNoticiaDTO(BaseModel):
    """Catálogo de medios. Visible a todos los despachos (los nacionales
    son globales). Las DISTRITALES viajan también pero ya filtradas por
    el repo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    dominio: str
    tipo: TipoFuenteNoticia
    alcance: AlcanceMedio
    modo_acceso: ModoAccesoFuente
    distrito: str | None = None
    activa: bool


# ---------------------------------------------------------------------------
# Articulo
# ---------------------------------------------------------------------------


class ArticuloDTO(BaseModel):
    """Snapshot mínimo del artículo. `bajada_propia` ≤240 chars
    (puede ser None si todavía no se generó). NUNCA hay campo `texto`
    (regla legal materializada, ADR 0006)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fuente_id: UUID
    url: str
    titulo: str
    bajada_propia: str | None
    publicado_en: datetime | None
    capturado_en: datetime


# ---------------------------------------------------------------------------
# Clasificación de Articulo
# ---------------------------------------------------------------------------


class ClasificacionArticuloDTO(BaseModel):
    """Clasificación general — no depende del despacho."""

    model_config = ConfigDict(from_attributes=True)

    area_tematica: AreaTematica
    palabras_clave: list[str]


# ---------------------------------------------------------------------------
# ArticuloRelevante (tenant-scoped)
# ---------------------------------------------------------------------------


class ArticuloRelevanteDTO(BaseModel):
    """Vista por despacho del scoring de relevancia (0-100)."""

    model_config = ConfigDict(from_attributes=True)

    articulo_id: UUID
    despacho_id: UUID
    score: int = Field(ge=0, le=100)
    razon: str
    expedientes_tocados: list[UUID]
    generado_en: datetime | None


class ArticuloRelevanteConArticuloDTO(BaseModel):
    """Pareo (relevante + artículo + fuente + clasificación opcional)
    para el GET /noticias. Evita N+1 en el frontend."""

    relevante: ArticuloRelevanteDTO
    articulo: ArticuloDTO
    fuente: FuenteNoticiaDTO
    clasificacion: ClasificacionArticuloDTO | None


# ---------------------------------------------------------------------------
# Detalle de artículo
# ---------------------------------------------------------------------------


class ArticuloDetalleDTO(BaseModel):
    """GET /noticias/{id}: articulo + fuente + clasificación + menciones
    de ese despacho relacionadas. Sin cuerpo."""

    articulo: ArticuloDTO
    fuente: FuenteNoticiaDTO
    clasificacion: ClasificacionArticuloDTO | None
    relevante: ArticuloRelevanteDTO | None
    menciones: list[MencionDTO]


# ---------------------------------------------------------------------------
# Mencion (tenant-scoped)
# ---------------------------------------------------------------------------


class MencionDTO(BaseModel):
    """Mención del legislador en un artículo. `snippet_contexto`
    ≤200 chars (D5: se persiste para histórico)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    articulo_id: UUID
    legislador_id: UUID
    despacho_id: UUID
    snippet_contexto: str
    tono: TonoMencion
    confianza_tono: float = Field(ge=0.0, le=1.0)
    alcance_medio: AlcanceMedio
    detectado_en: datetime | None
    notificada: bool


class MencionConArticuloDTO(BaseModel):
    """Pareo mención + artículo + fuente para el GET /menciones.
    Evita N+1."""

    mencion: MencionDTO
    articulo: ArticuloDTO
    fuente: FuenteNoticiaDTO


# Resolver forward refs (`ArticuloDetalleDTO.menciones`).
ArticuloDetalleDTO.model_rebuild()
