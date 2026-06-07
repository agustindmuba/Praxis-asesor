"""Entidad de dominio Despacho.

El Despacho es el **tenant** del sistema. Cada cliente (despacho legislativo)
es un Despacho con sus usuarios, expedientes seguidos, notas, alertas.

Ver `docs/adr/0003-persistencia.md` §"Tenant-scoped" para contexto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Despacho:
    """Despacho legislativo (el tenant de Praxis Asesor).

    Mutable: la configuración y el legislador titular pueden cambiar.
    """

    id: UUID
    nombre: str
    legislador_titular_slug: str | None = None
    legislador_foto_url: str | None = None
    configuracion: dict[str, Any] = field(default_factory=dict)
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("Despacho.nombre no puede ser vacío")
