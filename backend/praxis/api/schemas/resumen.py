"""Schema de respuesta del POST /expedientes/{id}/resumir."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ResumenEjecutivoDTO(BaseModel):
    """Resumen generado por un LLM sobre un expediente.

    `contenido_md` es markdown con 3 bullets. `modelo` permite a la UI mostrar
    qué provider lo generó (ej. `fake`, `claude-sonnet-4-5-...`).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expediente_id: UUID
    contenido_md: str
    modelo: str
    prompt_version: str
    generado_en: datetime
