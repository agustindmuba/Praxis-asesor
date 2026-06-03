"""Schemas Pydantic para endpoints /destinatarios y /envios-whatsapp
(feat-41.5).

NUNCA exponemos el body literal de los mensajes, solo metadata +
plantilla + estado. El contenido se reconstruye en el cliente con la
plantilla + payload_params si se quiere mostrar (no v1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from praxis.domain import (
    EstadoEnvio,
    EstadoMetaPlantilla,
    RolDestinatario,
    TipoEnvio,
    validar_e164,
)

# ---------------------------------------------------------------------------
# Destinatario DTOs
# ---------------------------------------------------------------------------


class DestinatarioDTO(BaseModel):
    """Vista completa del destinatario para el frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    despacho_id: UUID
    usuario_id: UUID | None
    nombre: str
    rol_interno: RolDestinatario
    telefono_e164: str
    recibe_briefing_diario: bool
    recibe_alertas_menciones: bool
    recibe_alertas_otras: bool
    opt_in_en: datetime | None
    opt_out_en: datetime | None
    activo: bool


class CrearDestinatarioBody(BaseModel):
    """Body del POST. Se valida E.164 acá para mejor mensaje de error
    al usuario (sino caería al constructor del dominio)."""

    nombre: Annotated[str, Field(min_length=1, max_length=200)]
    rol_interno: RolDestinatario
    telefono_e164: Annotated[str, Field(min_length=8, max_length=20)]
    recibe_briefing_diario: bool = True
    recibe_alertas_menciones: bool = True
    recibe_alertas_otras: bool = False

    def telefono_normalizado(self) -> str:
        # Re-uso el helper del dominio para que la normalización sea
        # exactamente la misma que al persistir.
        return validar_e164(self.telefono_e164)


class ActualizarDestinatarioBody(BaseModel):
    """Body del PATCH. Todos los campos son opcionales — el caller
    manda solo lo que cambió."""

    nombre: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    rol_interno: RolDestinatario | None = None
    telefono_e164: Annotated[str, Field(min_length=8, max_length=20)] | None = None
    recibe_briefing_diario: bool | None = None
    recibe_alertas_menciones: bool | None = None
    recibe_alertas_otras: bool | None = None


# ---------------------------------------------------------------------------
# EnvioWhatsApp DTOs
# ---------------------------------------------------------------------------


class EnvioWhatsAppDTO(BaseModel):
    """Histórico de envíos. payload_params se mantiene como dict
    abierto para que el frontend lo muestre tal cual."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    destinatario_id: UUID
    despacho_id: UUID
    plantilla_name: str
    tipo: TipoEnvio
    payload_params: dict[str, object]
    correlativo_id: UUID | None
    enviado_en: datetime | None
    estado: EstadoEnvio
    message_id_meta: str | None
    error: str | None


# ---------------------------------------------------------------------------
# Plantilla DTOs
# ---------------------------------------------------------------------------


class PlantillaWhatsAppDTO(BaseModel):
    """Catálogo de plantillas. Sólo lectura desde el frontend."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    idioma: str
    categoria: str
    body_params: list[str]
    estado_meta: EstadoMetaPlantilla
    aprobada_en: datetime | None
    contenido_referencia: str
