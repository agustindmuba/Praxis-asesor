"""Entidades de dominio: Legislador y Bloque.

Padrón vigente del Congreso. Frozen dataclasses con slots — los datos del
padrón son snapshots inmutables (cuando cambia el padrón, se reemplaza el
snapshot, no se muta).

Ver `docs/specs/05-catalogo-legisladores.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from praxis.domain.value_objects import Camara


@dataclass(frozen=True, slots=True)
class Bloque:
    """Bloque político en una cámara.

    Por simplicidad inicial: solo nombre + cámara. Atributos adicionales
    (presidente, secretario, integrantes) son feature aparte.
    """

    nombre: str
    camara: Camara

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("Bloque.nombre no puede ser vacío")


@dataclass(frozen=True, slots=True)
class Legislador:
    """Diputado o senador vigente.

    `slug` es el identificador natural usado por el portal oficial
    (ej. HCDN: `haguirre`; HSN: `s546`). Único dentro de su cámara.
    """

    slug: str
    apellido: str
    nombre: str
    camara: Camara
    distrito: str
    bloque: Bloque
    periodo_mandato: str  # ej. "2023-2027"
    fecha_inicio_mandato: date
    fecha_fin_mandato: date
    fecha_nacimiento: date | None = None
    edad_anios: int | None = None
    genero: str | None = None  # "F" | "M" | None
    profesion: str | None = None
    profesion_categoria: str | None = None
    foto_url: str | None = None
    padron_snapshot_fecha: date | None = None

    def __post_init__(self) -> None:
        if not self.slug.strip():
            raise ValueError("Legislador.slug no puede ser vacío")
        if not self.apellido.strip():
            raise ValueError("Legislador.apellido no puede ser vacío")
        if self.fecha_fin_mandato < self.fecha_inicio_mandato:
            raise ValueError(
                f"Legislador.fecha_fin_mandato ({self.fecha_fin_mandato}) < "
                f"fecha_inicio_mandato ({self.fecha_inicio_mandato})"
            )
        if self.bloque.camara != self.camara:
            raise ValueError(
                f"Legislador.bloque.camara ({self.bloque.camara}) "
                f"debe coincidir con Legislador.camara ({self.camara})"
            )

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}".strip(", ")
