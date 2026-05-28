"""Entidad de dominio: SeguimientoExpediente.

El "marcado" de un expediente por un despacho. Es la unidad tenant-scoped
central: cada despacho tiene su propia lista de expedientes que sigue,
con prioridad, responsable asignado (opcional) y archivado.

Ver `docs/adr/0002-modelo-expediente.md` §"Tenant-scoped" y
`docs/adr/0003-persistencia.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Prioridad(StrEnum):
    """Prioridad del seguimiento dentro del despacho."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


@dataclass(slots=True)
class SeguimientoExpediente:
    """Un despacho marca un expediente como de interés.

    Identidad lógica: (despacho_id, expediente_id) único — un despacho
    no puede marcar el mismo expediente dos veces.

    `responsable_id` es la asignación del expediente a un miembro del
    despacho (feature 13 del PRODUCT.md). Puede quedar None mientras
    nadie haya sido asignado.
    """

    id: UUID
    despacho_id: UUID
    expediente_id: UUID
    responsable_id: UUID | None = None
    prioridad: Prioridad = Prioridad.MEDIA
    archivado: bool = False
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None
