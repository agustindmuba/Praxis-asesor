"""Schemas del Panel de Inteligencia."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from praxis.domain import EtapaPipeline


class EtapaProgresoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    etapa: EtapaPipeline
    label: str
    alcanzada: bool
    fecha: date | None = None


class ProgresoTramiteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    etapa_actual: EtapaPipeline | None
    etapas: list[EtapaProgresoDTO]
    dias_en_etapa_actual: int | None
    terminado: bool
    motivo_terminacion: str | None


class ComparacionPeersDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    peer_count: int
    mediana_dias: int | None
    diferencia_porcentual: float | None
    criterio: str


class InteligenciaExpedienteDTO(BaseModel):
    """Bundle de inteligencia que devuelve el endpoint."""

    model_config = ConfigDict(from_attributes=True)
    progreso: ProgresoTramiteDTO
    peers: ComparacionPeersDTO
