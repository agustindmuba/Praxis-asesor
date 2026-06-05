"""Schemas Pydantic para /proyectos-redaccion (feat-42.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import EstadoProyecto, TipoProyecto


class ProyectoRedaccionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    despacho_id: UUID
    tipo: TipoProyecto
    titulo: str
    sumario: str
    articulado: list[str]
    fundamentos: str
    cofirmantes_sugeridos: list[str]
    estado: EstadoProyecto
    autor_legislador: str
    creado_en: datetime | None
    actualizado_en: datetime | None
    modelo_asistente: str | None
    prompt_version: str


class CrearProyectoBody(BaseModel):
    tipo: TipoProyecto
    titulo: Annotated[str, Field(min_length=3, max_length=400)]
    sumario: Annotated[str, Field(min_length=10, max_length=2000)]
    autor_legislador: Annotated[str, Field(min_length=3, max_length=120)] = ""


class ActualizarProyectoBody(BaseModel):
    tipo: TipoProyecto | None = None
    titulo: Annotated[str, Field(min_length=3, max_length=400)] | None = None
    sumario: Annotated[str, Field(min_length=10, max_length=2000)] | None = None
    articulado: list[str] | None = None
    fundamentos: str | None = None
    cofirmantes_sugeridos: list[str] | None = None
    estado: EstadoProyecto | None = None
    autor_legislador: str | None = None


class GenerarArticuladoBody(BaseModel):
    """Body para POST /proyectos-redaccion/{id}/asistir/articulado.

    Si se pasa `tema_override`, ignora el sumario actual del proyecto.
    Útil para generar variaciones."""

    tema_override: str | None = None


class GenerarFundamentosBody(BaseModel):
    """Body para POST /proyectos-redaccion/{id}/asistir/fundamentos."""

    pass  # no body — usa el articulado + sumario actual


class RefinarTextoBody(BaseModel):
    """Body para POST /proyectos-redaccion/asistir/refinar."""

    texto: Annotated[str, Field(min_length=1, max_length=5000)]
    instruccion: Annotated[str, Field(min_length=3, max_length=500)]


class TextoRefinadoDTO(BaseModel):
    texto_refinado: str
    modelo: str
