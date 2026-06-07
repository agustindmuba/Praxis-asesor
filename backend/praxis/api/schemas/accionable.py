"""Schemas Pydantic para /accionables (feat-42.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from praxis.domain import (
    AccionSugerida,
    ConfianzaAccionable,
    EstadoAccionable,
    TipoEvento,
)


class TweetSugeridoDTO(BaseModel):
    tono: str
    texto: str
    caracteres: int


class AccionableDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None
    despacho_id: UUID
    tipo_evento: TipoEvento
    evento_id: UUID
    razon_para_despacho: str
    accion_sugerida: AccionSugerida
    explicacion_accion: str
    tweets_sugeridos: list[TweetSugeridoDTO]
    confianza: ConfianzaAccionable
    generado_en: datetime | None
    editado_en: datetime | None
    modelo: str | None
    prompt_version: str
    # Feedback del asesor (feat-43.2).
    estado: EstadoAccionable = EstadoAccionable.PENDIENTE
    nota_asesor: str | None = None
    marcado_en: datetime | None = None


class EstadoAccionableUpdate(BaseModel):
    """Body de POST /accionables/{id}/estado (feat-43.2)."""

    model_config = ConfigDict(extra="forbid")

    estado: EstadoAccionable
    nota: str | None = None      # obligatoria si estado == ADAPTADO

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        if self.estado == EstadoAccionable.ADAPTADO and not (self.nota or "").strip():
            raise ValueError(
                "nota es obligatoria cuando estado=adaptado (explicá qué hiciste diferente)",
            )
