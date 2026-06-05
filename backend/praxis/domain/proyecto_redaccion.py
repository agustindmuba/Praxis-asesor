"""Entidad de dominio para Proyecto en redacción (feat-42.3).

Un `ProyectoEnRedaccion` es el borrador interno que un asesor está
componiendo. Distinto del `Expediente` (que ya existe externamente
en HCDN/HSN) — esto vive solo en el despacho hasta que se firma y
presenta.

Tipos soportados v1 (Diputados):
- LEY: Proyecto de Ley.
- RESOLUCION: Proyecto de Resolución de la Cámara.
- COMUNICACION: Proyecto de Comunicación (pedido de informes al PEN).
- DECLARACION: Proyecto de Declaración (expresar voluntad).

El `articulado` es una lista ordenada de strings, cada uno un artículo
completo. El `fundamentos` es texto Markdown libre (firma del autor
+ exposición).

Cofirmantes se guardan como lista de nombres (no UUIDs) porque
pueden ser legisladores aún no registrados en el padrón. El bot
de feat-28 los sugiere.

Estados:
- BORRADOR: en edición, el LLM puede asistir.
- LISTO: el asesor lo aprobó, queda inmutable salvo que vuelva a borrador.
- PRESENTADO: ya se cargó en HCDN. v2 puede linkear al expediente real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


REDACCION_PROMPT_VERSION = "v1"


class TipoProyecto(StrEnum):
    LEY = "ley"
    RESOLUCION = "resolucion"
    COMUNICACION = "comunicacion"
    DECLARACION = "declaracion"


TIPO_LABELS: dict[TipoProyecto, str] = {
    TipoProyecto.LEY: "Proyecto de Ley",
    TipoProyecto.RESOLUCION: "Proyecto de Resolución",
    TipoProyecto.COMUNICACION: "Proyecto de Comunicación",
    TipoProyecto.DECLARACION: "Proyecto de Declaración",
}


class EstadoProyecto(StrEnum):
    BORRADOR = "borrador"
    LISTO = "listo"
    PRESENTADO = "presentado"


@dataclass(slots=True)
class ProyectoEnRedaccion:
    """Borrador interno de un proyecto parlamentario."""

    despacho_id: UUID
    tipo: TipoProyecto
    titulo: str
    sumario: str                            # 1-2 líneas que resumen el objeto
    articulado: list[str] = field(default_factory=list)
    fundamentos: str = ""
    cofirmantes_sugeridos: list[str] = field(default_factory=list)
    estado: EstadoProyecto = EstadoProyecto.BORRADOR

    id: UUID | None = None
    autor_legislador: str = ""              # ej "JULIANO, PABLO"
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None
    modelo_asistente: str | None = None
    prompt_version: str = REDACCION_PROMPT_VERSION

    def __post_init__(self) -> None:
        if not self.titulo.strip():
            raise ValueError("ProyectoEnRedaccion.titulo no puede estar vacío")
        if not self.sumario.strip():
            raise ValueError("ProyectoEnRedaccion.sumario no puede estar vacío")
