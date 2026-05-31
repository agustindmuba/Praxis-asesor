"""Entidad de dominio: ResumenEjecutivo.

Resumen generado por un LLM (o por el FakeLlmProvider en dev) sobre un
Expediente. Se cachea: una sola corrida por expediente.

Ver `docs/specs/13-resumen-ejecutivo-ia.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

PROMPT_VERSION = "v1"


@dataclass(slots=True)
class ResumenEjecutivo:
    """Resumen ejecutivo de un expediente, generado por un LLM.

    `contenido_md` es markdown con la estructura:

        **Qué propone:** ...
        **Quién lo impulsa:** ...
        **Probabilidad de avance:** ...

    `modelo` identifica qué provider lo generó (`fake`, `claude-sonnet-4-5-...`)
    para que la UI pueda mostrarlo y para invalidar caches viejos si cambiamos
    de prompt.
    """

    id: UUID
    expediente_id: UUID
    contenido_md: str
    modelo: str
    prompt_version: str = PROMPT_VERSION
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.contenido_md.strip():
            raise ValueError("ResumenEjecutivo.contenido_md no puede estar vacío")
        if not self.modelo.strip():
            raise ValueError("ResumenEjecutivo.modelo no puede estar vacío")
