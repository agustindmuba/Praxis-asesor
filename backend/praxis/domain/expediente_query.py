"""Value objects para búsqueda de expedientes.

Ver `docs/specs/08-busqueda-expedientes.md` para diseño y alcance.

`ExpedienteQuery` es el criterio de búsqueda (todos los filtros AND, opcionales).
`ResultadoBusqueda` es el retorno paginado, con `total` separado del `len(items)`
para que la UI pueda mostrar "1-50 de 234".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from praxis.domain.area_tematica import AreaTematica
from praxis.domain.expediente import Expediente
from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    OrigenExpediente,
    TipoExpediente,
)

# Límites de paginación. Defaults pensados para UI tipo tabla.
LIMIT_DEFAULT = 50
LIMIT_MAX = 200


@dataclass(frozen=True, slots=True)
class ExpedienteQuery:
    """Criterio de búsqueda sobre el catálogo de expedientes.

    Todos los filtros son opcionales y se combinan con AND. Los strings de
    texto libre (`texto`, `autor_nombre`, `comision`) se aplican con
    `ILIKE %...%` case-insensitive.

    `texto` matchea sobre `titulo` y `sumario` (cualquiera de los dos).
    `autor_nombre` matchea sobre `firmante.nombre` vía EXISTS — no infla
    el resultado por expedientes con múltiples firmantes.
    `comision` matchea sobre `giro.comision` con la misma lógica.
    """

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
    # Filtros derivados del despacho actual (feat-43.1).
    area_tematica: AreaTematica | None = None
    con_dictamen: bool = False              # estado IN dictamen / media sanción / sancionado
    por_caducar_dias: int | None = None     # caduca en ≤ N días por Ley 13.640
    con_seguimiento_del_despacho: UUID | None = None
                                            # EXISTS seguimiento por este despacho
    firmados_por_titular_slug: str | None = None
                                            # slug del legislador titular del despacho
    limit: int = LIMIT_DEFAULT
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > LIMIT_MAX:
            raise ValueError(
                f"ExpedienteQuery.limit debe estar en [1, {LIMIT_MAX}], fue {self.limit}"
            )
        if self.offset < 0:
            raise ValueError(f"ExpedienteQuery.offset debe ser >= 0, fue {self.offset}")
        if (
            self.fecha_ingreso_desde is not None
            and self.fecha_ingreso_hasta is not None
            and self.fecha_ingreso_desde > self.fecha_ingreso_hasta
        ):
            raise ValueError(
                "ExpedienteQuery: fecha_ingreso_desde "
                f"({self.fecha_ingreso_desde}) > fecha_ingreso_hasta "
                f"({self.fecha_ingreso_hasta})"
            )
        # Strings de texto libre: no pueden ser whitespace-only si están seteados.
        for name in ("texto", "autor_nombre", "comision"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"ExpedienteQuery.{name} no puede ser solo whitespace si se setea")


@dataclass(frozen=True, slots=True)
class ResultadoBusqueda:
    """Resultado paginado de una búsqueda.

    `total` es el conteo de filas que matchearon el filtro, **independiente**
    del `limit/offset`. Permite a la UI mostrar "mostrando X-Y de Z".
    """

    items: list[Expediente] = field(default_factory=list)
    total: int = 0
    limit: int = LIMIT_DEFAULT
    offset: int = 0
