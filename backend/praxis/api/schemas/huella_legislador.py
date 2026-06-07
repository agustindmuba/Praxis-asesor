"""Schemas Pydantic para /legislador-titular/huella (feat-46)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CategoriaConPctDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    total: int
    pct: float          # 0-1, formato decimal


class HuellaLegisladorDTO(BaseModel):
    nombre: str | None
    slug: str | None
    bloque_dominante: str | None
    distrito_dominante: str | None
    foto_url: str | None
    total_firmados: int
    por_estado: list[CategoriaConPctDTO]
    por_tipo: list[CategoriaConPctDTO]
    por_area: list[CategoriaConPctDTO]


class ActualizarFotoLegislador(BaseModel):
    """Body de PATCH /legislador-titular/foto."""

    model_config = ConfigDict(extra="forbid")

    foto_url: str | None         # None para borrar la foto
