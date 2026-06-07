"""Filtros de query string para GET /expedientes + DTO del resultado."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from praxis.api.schemas.expediente import ExpedienteResumen
from praxis.domain import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    AreaTematica,
    Camara,
    Despacho,
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
    # Filtros derivados del despacho activo (feat-43.1). El cliente
    # solo manda toggles; el handler los traduce con `ctx.despacho`.
    area_tematica: AreaTematica | None = None
    con_dictamen: bool = False
    por_caducar: bool = False                 # default 60 días si activo
    por_caducar_dias: int = Field(default=60, ge=1, le=365)
    solo_seguidos: bool = False               # con seguimiento del despacho
    solo_titular: bool = False                # firmados por el legislador titular
    limit: int = Field(default=LIMIT_DEFAULT, ge=1, le=LIMIT_MAX)
    offset: int = Field(default=0, ge=0)

    def to_domain(self, despacho: Despacho | None = None) -> ExpedienteQuery:
        """Convierte a `ExpedienteQuery` del dominio (que vuelve a validar
        en su __post_init__, defensa en profundidad).

        Si `despacho` se pasa, los toggles `solo_seguidos` y `solo_titular`
        se resuelven con `despacho.id` y `despacho.legislador_titular_slug`.
        """
        con_seguimiento = None
        firmados_por_titular = None
        if despacho is not None:
            if self.solo_seguidos:
                con_seguimiento = despacho.id
            if self.solo_titular and despacho.legislador_titular_slug:
                firmados_por_titular = despacho.legislador_titular_slug

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
            area_tematica=self.area_tematica,
            con_dictamen=self.con_dictamen,
            por_caducar_dias=self.por_caducar_dias if self.por_caducar else None,
            con_seguimiento_del_despacho=con_seguimiento,
            firmados_por_titular_slug=firmados_por_titular,
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
