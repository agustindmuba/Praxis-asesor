"""Schemas de Expediente: resumen (lista), ficha (detalle), hijos."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from praxis.api.schemas.seguimiento import SeguimientoDTO
from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    NumeroExpediente,
    OrigenExpediente,
    SeguimientoExpediente,
    TipoExpediente,
)


class NumeroExpedienteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    numero: int
    origen: OrigenExpediente
    anio: int
    camara: Camara

    @classmethod
    def from_domain(cls, n: NumeroExpediente) -> NumeroExpedienteDTO:
        return cls(numero=n.numero, origen=n.origen, anio=n.anio, camara=n.camara)


class FirmanteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nombre: str
    distrito: str | None = None
    bloque: str | None = None
    orden: int = 1


class GiroDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    comision: str
    fecha_ingreso: date | None = None
    fecha_egreso: date | None = None
    orden: int | None = None


class TramiteEventoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fecha: date | None = None
    camara: Camara
    evento: str
    detalle: str | None = None
    fuente: str | None = None


class _BaseExpedienteDTO(BaseModel):
    """Campos comunes entre resumen y ficha."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: NumeroExpedienteDTO
    tipo: TipoExpediente
    titulo: str
    sumario: str | None = None
    fecha_ingreso: date | None = None
    estado: EstadoExpediente
    fecha_caducidad: date | None = None
    fecha_caducidad_original: date | None = None
    prorrogado: bool = False
    texto_url: str | None = None
    fuente_url: str | None = None


class ExpedienteResumen(_BaseExpedienteDTO):
    """Versión liviana para listados: sin firmantes/giros/tramite."""

    @classmethod
    def from_domain(cls, e: Expediente) -> ExpedienteResumen:
        assert e.id is not None, "Expediente debe tener id persistido"
        return cls(
            id=e.id,
            numero=NumeroExpedienteDTO.from_domain(e.numero),
            tipo=e.tipo,
            titulo=e.titulo,
            sumario=e.sumario,
            fecha_ingreso=e.fecha_ingreso,
            estado=e.estado,
            fecha_caducidad=e.fecha_caducidad,
            fecha_caducidad_original=e.fecha_caducidad_original,
            prorrogado=e.prorrogado,
            texto_url=e.texto_url,
            fuente_url=e.fuente_url,
        )


class ExpedienteFicha(_BaseExpedienteDTO):
    """Ficha completa con hijos + seguimiento del despacho activo (si existe)."""

    firmantes: list[FirmanteDTO]
    giros: list[GiroDTO]
    tramite: list[TramiteEventoDTO]
    seguimiento: SeguimientoDTO | None = None

    @classmethod
    def from_domain(
        cls,
        e: Expediente,
        *,
        seguimiento: SeguimientoExpediente | None = None,
    ) -> ExpedienteFicha:
        assert e.id is not None, "Expediente debe tener id persistido"
        # Firmantes ordenados por `orden` para presentación consistente.
        firmantes = [
            FirmanteDTO.model_validate(f) for f in sorted(e.firmantes, key=lambda f: f.orden)
        ]
        # Trámite cronológico ascendente (NULLs al final, ya hace `tramite_ordenado`).
        tramite = [TramiteEventoDTO.model_validate(t) for t in e.tramite_ordenado()]
        return cls(
            id=e.id,
            numero=NumeroExpedienteDTO.from_domain(e.numero),
            tipo=e.tipo,
            titulo=e.titulo,
            sumario=e.sumario,
            fecha_ingreso=e.fecha_ingreso,
            estado=e.estado,
            fecha_caducidad=e.fecha_caducidad,
            fecha_caducidad_original=e.fecha_caducidad_original,
            prorrogado=e.prorrogado,
            texto_url=e.texto_url,
            fuente_url=e.fuente_url,
            firmantes=firmantes,
            giros=[GiroDTO.model_validate(g) for g in e.giros],
            tramite=tramite,
            seguimiento=SeguimientoDTO.model_validate(seguimiento) if seguimiento else None,
        )


__all__ = [
    "ExpedienteFicha",
    "ExpedienteResumen",
    "FirmanteDTO",
    "GiroDTO",
    "NumeroExpedienteDTO",
    "TramiteEventoDTO",
]
