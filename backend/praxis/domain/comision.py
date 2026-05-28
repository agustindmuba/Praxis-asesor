"""Entidades de dominio: Comision y TipoComision.

Catálogo de comisiones legislativas. Frozen dataclasses; los datos vienen
de snapshots (vendored) y son inmutables hasta el próximo refresh.

Ver `docs/specs/06-catalogo-comisiones.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from praxis.domain.value_objects import Camara


class TipoComision(StrEnum):
    """Tipo de comisión legislativa.

    HSN expone esto explícitamente en su JSON oficial. HCDN, en la fuente
    de datos actual del catálogo (CSV del Observatorio), no discrimina —
    por eso `PERMANENTE` es el default para HCDN.
    """

    PERMANENTE = "permanente"  # Unicameral permanente
    ESPECIAL = "especial"  # Unicameral especial / temporal
    BICAMERAL_PERMANENTE = "bicameral_permanente"
    BICAMERAL_ESPECIAL = "bicameral_especial"
    OTRO = "otro"

    @classmethod
    def from_text(cls, text: str) -> TipoComision:
        """Mapea desde el texto libre del portal HSN.

        Inputs esperados: "UNICAMERAL PERMANENTE", "BICAMERAL PERMANENTE",
        "BICAMERAL ESPECIAL", etc.
        """
        t = text.upper().strip()
        if "BICAMERAL" in t and "ESPECIAL" in t:
            return cls.BICAMERAL_ESPECIAL
        if "BICAMERAL" in t and "PERMANENTE" in t:
            return cls.BICAMERAL_PERMANENTE
        if "BICAMERAL" in t:
            return cls.BICAMERAL_PERMANENTE  # default conservador
        if "PERMANENTE" in t:
            return cls.PERMANENTE
        if "ESPECIAL" in t:
            return cls.ESPECIAL
        return cls.OTRO


@dataclass(frozen=True, slots=True)
class Comision:
    """Comisión legislativa.

    Identidad: `(camara, nombre)` o `(camara, slug)` cuando hay slug.
    Para comisiones bicamerales, aparecen como entradas separadas en cada
    cámara (no se dedupean automáticamente).
    """

    nombre: str
    tipo: TipoComision
    camara: Camara
    slug: str | None = None  # solo HCDN tiene slug nativo
    categoria_tematica: str | None = None  # solo HCDN tiene categoría

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("Comision.nombre no puede ser vacío")
