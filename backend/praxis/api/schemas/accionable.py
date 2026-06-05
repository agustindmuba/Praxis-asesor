"""Schemas Pydantic para /accionables (feat-42.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from praxis.domain import (
    AccionSugerida,
    ConfianzaAccionable,
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
