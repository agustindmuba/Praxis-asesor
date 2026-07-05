"""Entidades de dominio: Comision (catálogo) + ComisionHcdn (persistida).

- `Comision` (sin ID): catálogo plano vendoreado (CSV). Lectura sola.
- `ComisionHcdn` + `IntegranteComision` + `ReunionComision` (con UUID):
  entidades persistidas, alimentadas por el scraper del portal HCDN.

Las dos cosas coexisten porque tienen casos de uso distintos: el catálogo
es para clasificar tipo de comisión, el persistido es para mostrar
agenda real del despacho.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID

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


# ---------------------------------------------------------------------------
# Persistidas (feat-61): vienen del scraper HCDN, tienen UUID, integrantes
# y agenda de reuniones.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntegranteComision:
    """Diputado/a integrante de una comisión.

    `legislador_id` puede ser None si el scraper trajo un nombre que no
    matchea contra el padrón (legislador nuevo, error de tipeo, etc.).
    """

    id: UUID | None
    comision_id: UUID
    nombre_diputado: str
    cargo: str  # PRESIDENTE / VICEPRESIDENTE / SECRETARIO / VOCAL
    partido: str | None = None
    distrito: str | None = None
    legislador_id: UUID | None = None
    capturado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.nombre_diputado.strip():
            raise ValueError("IntegranteComision.nombre_diputado vacío")
        if not self.cargo.strip():
            raise ValueError("IntegranteComision.cargo vacío")


@dataclass(frozen=True, slots=True)
class ReunionComision:
    """Reunión convocada por una comisión.

    Campos básicos parseados del HTML del portal:
    - `titulo`: texto crudo (se conserva como respaldo).
    - `hora`, `sala`, `descripcion`, `comisiones_invitadas`: parseados.

    Campos enriquecidos por LLM (todos opcionales, se llenan a demanda):
    - `tema_corto`, `tipo_reunion`, `convocada_por`,
      `expedientes_citados`, `oportunidad_politica`, `accion_sugerida`,
      `huella_historica`.
    - `enriquecida_en`: timestamp del enriquecimiento (None = pendiente).
    """

    id: UUID | None
    comision_id: UUID
    fecha: date
    titulo: str
    hora: time | None = None
    sala: str | None = None
    citacion_pdf_url: str | None = None
    descripcion: str | None = None
    comisiones_invitadas: list[str] = field(default_factory=list)

    # Enriquecimiento LLM
    tema_corto: str | None = None
    tipo_reunion: str | None = None
    convocada_por: str | None = None
    expedientes_citados: list[str] = field(default_factory=list)
    oportunidad_politica: str | None = None
    accion_sugerida: str | None = None
    huella_historica: str | None = None
    enriquecida_en: datetime | None = None

    capturado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.titulo.strip():
            raise ValueError("ReunionComision.titulo vacío")


@dataclass(frozen=True, slots=True)
class ComisionHcdn:
    """Comisión del portal HCDN, persistida con integrantes + agenda.

    Identidad natural: `(camara, slug)`. `id` se asigna al insertar.
    Los integrantes y reuniones son listas opcionales para hidratar
    "todo junto" cuando el caller los necesita.
    """

    id: UUID | None
    camara: Camara
    slug: str
    nombre: str
    tipo: TipoComision
    url_oficial: str
    descripcion: str | None = None
    capturado_en: datetime | None = None
    integrantes: list[IntegranteComision] = field(default_factory=list)
    reuniones: list[ReunionComision] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("ComisionHcdn.nombre vacío")
        if not self.slug.strip():
            raise ValueError("ComisionHcdn.slug vacío")
        if not self.url_oficial.strip():
            raise ValueError("ComisionHcdn.url_oficial vacío")
