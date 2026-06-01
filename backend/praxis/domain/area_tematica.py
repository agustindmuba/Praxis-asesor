"""Clasificación temática de expedientes.

Spec 14 §"Algoritmos · Clasificación temática": el briefing pre-sesión
necesita agrupar los proyectos del orden del día por área temática para
poder presentar la página 3 ("resto del OD por área") y para alimentar
los algoritmos de cofirmantes naturales y antecedente más parecido.

Decisión:
- 12 áreas fijas predefinidas. No es ideal (los proyectos transversales
  pierden información), pero es suficiente para v1 y permite UI estable.
- La inferencia se cachea por expediente. Una sola clasificación por
  expediente, regenerable solo borrando el cache.
- El `LlmProvider` decide cómo clasificar — `FakeLlmProvider` usa
  keywords; el real puede usar Sonnet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AreaTematica(StrEnum):
    """Las 12 áreas temáticas del MVP del briefing.

    Cualquier proyecto que no calza en una específica se etiqueta `OTROS`.
    Esa decisión es responsabilidad del clasificador.
    """

    EDUCACION = "educacion"
    SALUD = "salud"
    TRABAJO = "trabajo"
    SEGURIDAD = "seguridad"
    JUSTICIA = "justicia"
    ECONOMIA = "economia"
    AMBIENTE = "ambiente"
    DERECHOS_HUMANOS = "derechos_humanos"
    INFRAESTRUCTURA = "infraestructura"
    TRANSPORTE = "transporte"
    RELACIONES_EXTERIORES = "relaciones_exteriores"
    OTROS = "otros"


# Etiquetas legibles para UI / PDF.
AREA_LABELS: dict[AreaTematica, str] = {
    AreaTematica.EDUCACION: "Educación",
    AreaTematica.SALUD: "Salud",
    AreaTematica.TRABAJO: "Trabajo",
    AreaTematica.SEGURIDAD: "Seguridad",
    AreaTematica.JUSTICIA: "Justicia",
    AreaTematica.ECONOMIA: "Economía",
    AreaTematica.AMBIENTE: "Ambiente",
    AreaTematica.DERECHOS_HUMANOS: "Derechos humanos",
    AreaTematica.INFRAESTRUCTURA: "Infraestructura",
    AreaTematica.TRANSPORTE: "Transporte",
    AreaTematica.RELACIONES_EXTERIORES: "Relaciones exteriores",
    AreaTematica.OTROS: "Otros",
}


# Versión del prompt/heurística de clasificación. Bump cuando cambie
# materialmente el comportamiento — los caches viejos siguen siendo
# válidos hasta que se invaliden manualmente.
CLASIFICACION_PROMPT_VERSION = "v1"


@dataclass(slots=True)
class ExpedienteAreaTematica:
    """Cache de la clasificación temática de un expediente.

    A lo sumo una fila por expediente (UNIQUE en `expediente_id`). Para
    regenerar se borra y se vuelve a clasificar.

    No frozen para alinear con `ResumenEjecutivo`: el ORM rellena
    `generado_en` con server_default y lo refresca tras INSERT. Hasta
    ese momento puede ser `None`.
    """

    id: UUID
    expediente_id: UUID
    area: AreaTematica
    modelo: str                       # "fake-keywords" | "claude-sonnet-4-5-..."
    prompt_version: str = CLASIFICACION_PROMPT_VERSION
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.modelo.strip():
            raise ValueError("ExpedienteAreaTematica.modelo no puede estar vacío")
