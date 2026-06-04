"""Schemas Pydantic para /perfil-opositor (feat-42.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import ConfianzaGlobal, TonoComunicacional


class FiguraReferidaDTO(BaseModel):
    nombre: str
    razon: str


class PerfilOpositorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    despacho_id: UUID
    bandera_principal: str
    banderas_secundarias: list[str]
    temas_de_cuidado: list[str]
    tono_comunicacional: TonoComunicacional
    adversarios: list[FiguraReferidaDTO]
    aliados: list[FiguraReferidaDTO]
    linea_de_bloque: str
    justificacion_evidencia: str
    advertencias: list[str]
    confianza_global: ConfianzaGlobal
    inferido_en: datetime | None
    editado_en: datetime | None
    modelo_inferencia: str | None
    prompt_version: str


class InferirPerfilBody(BaseModel):
    """Body del POST /perfil-opositor/inferir."""

    nombre_legislador: Annotated[str, Field(min_length=3, max_length=120)]
    max_votaciones: Annotated[int, Field(ge=5, le=200)] = 50


class ActualizarPerfilBody(BaseModel):
    """Body del PATCH /perfil-opositor. Todos opcionales — el caller
    manda solo los campos editados desde la UI."""

    bandera_principal: str | None = None
    banderas_secundarias: list[str] | None = None
    temas_de_cuidado: list[str] | None = None
    tono_comunicacional: TonoComunicacional | None = None
    adversarios: list[FiguraReferidaDTO] | None = None
    aliados: list[FiguraReferidaDTO] | None = None
    linea_de_bloque: str | None = None
