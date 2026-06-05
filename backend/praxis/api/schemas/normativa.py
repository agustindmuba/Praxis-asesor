"""Schemas Pydantic para /normativa y conflictos (feat-42.6)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ChunkSimilarDTO(BaseModel):
    fuente: str
    articulo_label: str
    texto: str
    distancia: float


class BuscarNormativaBody(BaseModel):
    query: Annotated[str, Field(min_length=3, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=30)] = 10


class ConflictoDetectadoDTO(BaseModel):
    indice_articulo_proyecto: int
    fuente: str
    articulo_label: str
    severidad: Literal["conflicto", "modificacion", "complementa", "ninguno"]
    explicacion: str
    texto_norma_referida: str


class ResultadoValidacionDTO(BaseModel):
    proyecto_id: str
    n_articulos_evaluados: int
    conflictos: list[ConflictoDetectadoDTO]
    sin_conflictos: bool
