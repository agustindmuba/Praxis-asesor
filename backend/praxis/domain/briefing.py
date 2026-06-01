"""Briefing pre-sesión — el output principal del MVP.

Spec 14. Un `Briefing` es el snapshot de inteligencia para una sesión
específica de un despacho. Se cachea: regenerar implica delete + insert.

Value objects internos:
- `AlertaBriefing`: una línea de la página 1 (resumen ejecutivo).
- `SeccionProyectoBriefing`: una sección de la página 2 (proyectos del
  despacho con argumentos, contraargumentos, cofirmantes, antecedente).
- `SeccionAreaBriefing`: una sección de la página 3 (resto del OD por
  área temática).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from praxis.domain.area_tematica import AreaTematica
from praxis.domain.briefing_similitud import (
    AntecedenteParecido,
    CofirmanteSugerido,
)
from praxis.domain.value_objects import (
    EstadoExpediente,
    NumeroExpediente,
    TipoExpediente,
)

BRIEFING_PROMPT_VERSION = "v1"


PrioridadAlerta = Literal["alta", "media", "baja"]
RolEnDespacho = Literal["autor", "cofirmante"]
RecomendacionVoto = Literal["a_favor", "abstencion", "en_contra", "sin_recomendacion"]


@dataclass(frozen=True, slots=True)
class AlertaBriefing:
    """Una línea destacada que aparece en la página 1 del briefing."""

    prioridad: PrioridadAlerta
    titulo: str
    detalle: str
    expediente_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SeccionProyectoBriefing:
    """Una sección de página 2: un proyecto seguido por el despacho."""

    expediente_id: UUID
    numero: NumeroExpediente
    titulo: str
    estado: EstadoExpediente
    tipo: TipoExpediente
    rol_despacho: RolEnDespacho
    area: AreaTematica
    dias_en_etapa: int | None
    argumentos: list[str]
    contraargumentos: list[str]
    cofirmantes_naturales: list[CofirmanteSugerido]
    antecedente: AntecedenteParecido | None


@dataclass(frozen=True, slots=True)
class ProyectoEnAreaBriefing:
    """Una línea de proyecto dentro de una sección de área."""

    expediente_id: UUID
    numero: NumeroExpediente
    titulo: str
    autor_principal: str | None
    bloque_autor: str | None
    recomendacion: RecomendacionVoto
    razon: str


@dataclass(frozen=True, slots=True)
class SeccionAreaBriefing:
    """Una sección de página 3: proyectos del OD agrupados por área."""

    area: AreaTematica
    proyectos: list[ProyectoEnAreaBriefing]


@dataclass(slots=True)
class Briefing:
    """El briefing completo para una sesión, listo para renderizar a PDF.

    No frozen: el ID y `generado_en` los rellena la persistencia.

    Una fila por (despacho, orden_del_dia). UNIQUE en (despacho_id,
    orden_del_dia_id). Regenerar = delete + insert.
    """

    despacho_id: UUID
    orden_del_dia_id: UUID
    modelo_llm: str

    # Página 1
    proyectos_del_despacho_total: int
    proyectos_como_autor: int
    proyectos_como_cofirmante: int
    alertas: list[AlertaBriefing] = field(default_factory=list)

    # Página 2
    secciones_proyectos: list[SeccionProyectoBriefing] = field(default_factory=list)

    # Página 3
    secciones_areas: list[SeccionAreaBriefing] = field(default_factory=list)

    # Persistencia
    id: UUID | None = None
    prompt_version: str = BRIEFING_PROMPT_VERSION
    generado_en: datetime | None = None
