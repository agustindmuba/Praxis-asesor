"""Orden del día — lista de expedientes a tratar en una sesión.

Spec 14 §"Estructura del PDF": el briefing se calcula sobre un
`OrdenDelDia` específico, no sobre la base de expedientes en bruto.

v1: el asesor carga manualmente el OD (POST con números de expediente).
v2: scraping automático del portal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from praxis.domain.value_objects import Camara

FuenteOd = Literal["upload_manual", "scraping_hcdn"]


@dataclass(slots=True)
class OrdenDelDia:
    """Lista de expedientes a tratar en una sesión específica.

    No frozen: persistencia puede agregar id/created_at después del
    construct inicial del caso de uso.
    """

    camara: Camara
    fecha_sesion: date
    expedientes_ids: list[UUID] = field(default_factory=list)
    id: UUID | None = None
    hora_sesion: time | None = None
    fuente: FuenteOd = "upload_manual"
    titulo: str | None = None              # ej "Sesión Ordinaria N° 7"
    # id_sesion del portal HCDN para idempotencia (feat-45.3). Solo
    # aplica cuando `fuente="scraping_hcdn"`.
    id_sesion_externa: int | None = None
    creado_en: datetime | None = None

    def __post_init__(self) -> None:
        # Manual: debe tener al menos un expediente. Scraping puede
        # quedar vacío si todos los expedientes del temario aún no
        # están ingestados en la DB local (feat-45.3).
        if self.fuente == "upload_manual" and not self.expedientes_ids:
            raise ValueError(
                "OrdenDelDia (manual).expedientes_ids no puede ser vacío",
            )
        if self.fuente == "scraping_hcdn" and self.id_sesion_externa is None:
            raise ValueError(
                "OrdenDelDia (scraping).id_sesion_externa es obligatorio",
            )
