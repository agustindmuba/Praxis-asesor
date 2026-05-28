"""Schemas de SeguimientoExpediente: respuesta + bodies de POST/PATCH."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from praxis.domain import Prioridad


class SeguimientoDTO(BaseModel):
    """Representación pública del seguimiento. No expone despacho_id (es el
    del request) salvo cuando lo embebemos en la ficha del expediente.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expediente_id: UUID
    responsable_id: UUID | None = None
    prioridad: Prioridad
    archivado: bool


class CrearSeguimientoBody(BaseModel):
    """Body de POST /seguimientos."""

    model_config = ConfigDict(extra="forbid")

    expediente_id: UUID
    prioridad: Prioridad = Prioridad.MEDIA


class ActualizarSeguimientoBody(BaseModel):
    """Body de PATCH /seguimientos/{id}.

    Todos los campos opcionales. El handler interpreta:
    - `responsable_id` presente (incluso `null`) → asigna/desasigna.
    - `archivado=true` → archiva. `archivado=false` con seguimiento ya
      archivado: no soportado en esta vuelta (sin "desarchivar"). Si llega
      falso lo ignoramos.
    """

    model_config = ConfigDict(extra="forbid")

    responsable_id: UUID | None = None
    archivado: bool | None = None
    # Marker para distinguir "no enviado" vs "enviado como null" en responsable_id.
    # FastAPI/Pydantic no exponen esa diferencia natural; usamos
    # `model_fields_set` en el handler.
