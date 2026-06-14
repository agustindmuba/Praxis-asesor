"""Efemérides — fechas conmemorativas con valor parlamentario.

Una efeméride es una fecha que se conmemora año tras año (recurrente) o
puntualmente un año específico (aniversario). El despacho la usa para:

1. Generar proyectos de declaración (~90% de las declaraciones
   parlamentarias conmemoran una efeméride).
2. Tweets y posts en redes sociales con tono temático.
3. Visibilidad pública: visitas, actos, conferencias.
4. Planificación de agenda del bloque.

Fuentes habituales: leyes nacionales declaratorias, decretos del PE,
ONU (días internacionales), costumbre académica/cultural.

Decisiones de modelado:
- `fecha` es MM-DD (recurrente) para la mayoría — ej. 8 de marzo no
  pertenece a 2024 sino a TODOS los años.
- `anio_unico` se usa solo para conmemoraciones puntuales (50° aniversario
  del Golpe del '76, 100 años del Grito de Alcorta, etc.). Si está, la
  efeméride solo aplica ese año.
- `relevancia` permite ordenar el dashboard sin perder las menos
  importantes — el asesor las ve si filtra "todas".
- `areas_tematicas` se almacenan como lista de strings (no FK al enum)
  porque una efeméride puede tocar varias áreas y la flexibilidad
  pesa más que la integridad referencial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TipoEfemeride(StrEnum):
    """Origen / naturaleza de la efeméride.

    Se usa para filtros en UI y para priorización: las nacionales suelen
    pesar más que las internacionales para un despacho argentino, pero
    los días internacionales tienen alcance comunicacional.
    """

    INTERNACIONAL = "internacional"     # ONU, OMS, días mundiales
    NACIONAL = "nacional"               # leyes / decretos argentinos
    PROVINCIAL = "provincial"           # provincias argentinas
    TEMATICA = "tematica"               # costumbre cultural, religiosa, popular
    ANIVERSARIO = "aniversario"         # eventos históricos (independencia, gestas)
    CONMEMORATIVA = "conmemorativa"     # fallecimientos, natalicios destacados


class RelevanciaEfemeride(StrEnum):
    """Cuánto destaca la efeméride en dashboard / briefing.

    `ALTA` aparece destacada en el dashboard y en el WhatsApp del día.
    `MEDIA` aparece en briefing si hay espacio.
    `BAJA` solo en la vista /efemerides cuando el asesor consulta
    activamente.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


# Etiquetas legibles para UI. Prefijo `EFEMERIDE_` para no colisionar
# con TIPO_LABELS de proyecto_redaccion (que ya existe en el dominio).
EFEMERIDE_TIPO_LABELS: dict[TipoEfemeride, str] = {
    TipoEfemeride.INTERNACIONAL: "Internacional",
    TipoEfemeride.NACIONAL: "Nacional",
    TipoEfemeride.PROVINCIAL: "Provincial",
    TipoEfemeride.TEMATICA: "Temática",
    TipoEfemeride.ANIVERSARIO: "Aniversario",
    TipoEfemeride.CONMEMORATIVA: "Conmemorativa",
}

EFEMERIDE_RELEVANCIA_LABELS: dict[RelevanciaEfemeride, str] = {
    RelevanciaEfemeride.ALTA: "Alta",
    RelevanciaEfemeride.MEDIA: "Media",
    RelevanciaEfemeride.BAJA: "Baja",
}


@dataclass(slots=True)
class Efemeride:
    """Una fecha conmemorativa.

    Identidad natural: (mes, dia, titulo) — dos efemérides el mismo día
    son posibles (ej. 8/3 es Día Internacional de la Mujer + otras).

    `anio_unico=None` (default) significa que la efeméride se repite
    todos los años. Si `anio_unico=2026`, solo aplica ese año (útil para
    conmemoraciones de aniversarios redondos).
    """

    id: UUID
    mes: int                                            # 1..12
    dia: int                                            # 1..31
    titulo: str
    tipo: TipoEfemeride
    relevancia: RelevanciaEfemeride
    descripcion: str | None = None                      # contexto histórico breve
    fuente: str | None = None                           # ley / decreto / ONU / costumbre
    areas_tematicas: list[str] = field(default_factory=list)
    anio_unico: int | None = None                       # None = recurrente todos los años
    creado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.mes <= 12:
            raise ValueError(f"mes inválido: {self.mes}")
        if not 1 <= self.dia <= 31:
            raise ValueError(f"dia inválido: {self.dia}")
        if not self.titulo.strip():
            raise ValueError("Efemeride.titulo no puede estar vacío")
        if self.anio_unico is not None and not (1800 <= self.anio_unico <= 2100):
            raise ValueError(
                f"anio_unico fuera de rango razonable: {self.anio_unico}"
            )

    @property
    def es_recurrente(self) -> bool:
        """True si la efeméride se conmemora todos los años."""
        return self.anio_unico is None

    @property
    def fecha_corta(self) -> str:
        """Representación corta MM-DD para display."""
        return f"{self.mes:02d}-{self.dia:02d}"
