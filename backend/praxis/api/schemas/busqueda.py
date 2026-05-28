"""Filtros de query string para GET /expedientes + DTO del resultado."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from praxis.api.schemas.expediente import ExpedienteResumen
from praxis.domain import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    Camara,
    EstadoExpediente,
    ExpedienteQuery,
    OrigenExpediente,
    ResultadoBusqueda,
    TipoExpediente,
)


class FiltrosExpediente(BaseModel):
    """Filtros que el cliente pasa por query string.

    Mapea 1:1 a `domain.ExpedienteQuery`. La conversión vive en `to_domain()`
    para que el handler quede limpio.
    """

    model_config = ConfigDict(extra="forbid")

    texto: str | None = None
    anio: int | None = None
    tipo: TipoExpediente | None = None
    camara: Camara | None = None
    origen: OrigenExpediente | None = None
    estado: EstadoExpediente | None = None
    autor_nombre: str | None = None
    comision: str | None = None
    fecha_ingreso_desde: date | None = None
    fecha_ingreso_hasta: date | None = None
    limit: int = Field(default=LIMIT_DEFAULT, ge=1, le=LIMIT_MAX)
    offset: int = Field(default=0, ge=0)

    def to_domain(self) -> ExpedienteQuery:
        """Convierte a `ExpedienteQuery` del dominio (que vuelve a validar
        en su __post_init__, defensa en profundidad).
        """
        return ExpedienteQuery(
            texto=self.texto,
            anio=self.anio,
            tipo=self.tipo,
            camara=self.camara,
            origen=self.origen,
            estado=self.estado,
            autor_nombre=self.autor_nombre,
            comision=self.comision,
            fecha_ingreso_desde=self.fecha_ingreso_desde,
            fecha_ingreso_hasta=self.fecha_ingreso_hasta,
            limit=self.limit,
            offset=self.offset,
        )


class ResultadoBusquedaDTO(BaseModel):
    """Resultado paginado expuesto por GET /expedientes."""

    model_config = ConfigDict(from_attributes=True)

    items: list[ExpedienteResumen]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_domain(cls, r: ResultadoBusqueda) -> ResultadoBusquedaDTO:
        return cls(
            items=[ExpedienteResumen.from_domain(e) for e in r.items],
            total=r.total,
            limit=r.limit,
            offset=r.offset,
        )


__all__ = ["FiltrosExpediente", "ResultadoBusquedaDTO"]
