"""Entidades de dominio para el canal WhatsApp (spec 17, feat-41).

Tres unidades:

- `Destinatario`: persona del despacho con teléfono E.164 + flags de
  suscripción por canal (briefing diario / alertas de menciones /
  otras alertas). Tracks opt-in/opt-out (compliance Meta).
- `PlantillaWhatsApp`: catálogo de plantillas pre-aprobadas por Meta.
  Identidad natural por `name + idioma`. Estado de aprobación
  reflejado del API de Meta.
- `EnvioWhatsApp`: registro auditable de cada envío. `despacho_id`
  desnormalizado para tenant-scoping sin JOIN (ADR 0006).
  `message_id_meta` UNIQUE para correlacionar webhooks.

Convenciones (alineadas con ADR 0006):

- `frozen=True, slots=True`.
- Teléfonos en E.164 (`+5491155551234`), validación regex.
- Idiomas como Literal (`es_AR` por default).
- Estados como StrEnum: `EstadoEnvio` (pendiente/enviado/entregado/
  leido/fallido/rechazado) y `EstadoMetaPlantilla` (pendiente/aprobada/
  rechazada/pausada).
- Opt-in obligatorio para envío real (compliance Meta WhatsApp
  Business — no se puede mandar sin consentimiento).

Ver `docs/specs/17-whatsapp-canal.md` (a redactar en 41.0).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

# E.164: `+` + dígito-leading (1-9) + 7-14 dígitos. Total 8-15 chars
# incluyendo el `+`. Acepta hasta 20 para tolerar buffers en formatos
# raros del input (la fila ORM tiene 20 chars max).
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class EstadoEnvio(StrEnum):
    """Estado del envío. Refleja el ciclo de vida de Meta WhatsApp.

    - `PENDIENTE`: aún no se intentó enviar (creado en DB pero antes
      del HTTP a Meta).
    - `ENVIADO`: Meta aceptó la request (HTTP 200 + message_id).
    - `ENTREGADO`: Meta confirmó delivery al device (webhook `status:
      delivered`).
    - `LEIDO`: el usuario leyó el mensaje (webhook `status: read`).
    - `FALLIDO`: error del lado del provider (red, timeout, sintaxis).
    - `RECHAZADO`: Meta rechazó el envío (opt-out, plantilla no
      aprobada, número inválido).
    """

    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    ENTREGADO = "entregado"
    LEIDO = "leido"
    FALLIDO = "fallido"
    RECHAZADO = "rechazado"


class EstadoMetaPlantilla(StrEnum):
    """Estado de aprobación de la plantilla en Meta WhatsApp Manager."""

    PENDIENTE_APROBACION = "pendiente_aprobacion"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    PAUSADA = "pausada"  # Meta puede pausar plantillas con baja calidad
    DESCONOCIDA = "desconocida"  # fallback si Meta devuelve algo nuevo


class CategoriaPlantilla(StrEnum):
    """Categoría de plantilla (define las reglas de Meta).

    - `UTILITY`: notificaciones operativas (briefings, alertas).
    - `MARKETING`: requiere opt-in explícito + cobra por mensaje.
    - `AUTHENTICATION`: códigos OTP. NO aplica a Praxis v1.
    """

    UTILITY = "utility"
    MARKETING = "marketing"
    AUTHENTICATION = "authentication"


class RolDestinatario(StrEnum):
    """Rol del destinatario dentro del despacho.

    Identificadores internos. NO se mandan a Meta.
    """

    LEGISLADOR = "legislador"
    JEFE_ASESORES = "jefe_asesores"
    ASESOR = "asesor"
    OTRO = "otro"


class TipoEnvio(StrEnum):
    """Categoría del envío para reporting y filtros del histórico."""

    BRIEFING_DIARIO = "briefing_diario"
    ALERTA_MENCION = "alerta_mencion"
    ALERTA_BO = "alerta_bo"
    OTRO = "otro"


IdiomaLiteral = Literal["es_AR", "es_ES", "en_US"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validar_e164(telefono: str) -> str:
    """Normaliza + valida un teléfono E.164. Lanza ValueError si no
    cumple."""
    limpio = telefono.strip().replace(" ", "").replace("-", "")
    if not _E164_RE.match(limpio):
        raise ValueError(
            f"Teléfono '{telefono}' no es E.164 válido "
            "(formato esperado: +5491155551234)",
        )
    return limpio


# ---------------------------------------------------------------------------
# Destinatario
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Destinatario:
    """Persona del despacho que recibe mensajes Praxis por WhatsApp.

    Reglas:
    - Único por `(despacho_id, telefono_e164)`.
    - `activo` requiere `opt_in_en is not None` + `opt_out_en is None`.
      El método `puede_recibir(canal)` chequea ambos.
    - `usuario_id` es opcional: un destinatario puede ser un legislador
      o asesor que no tiene cuenta en la app (solo recibe WhatsApp).
    """

    id: UUID | None
    despacho_id: UUID
    nombre: str
    rol_interno: RolDestinatario
    telefono_e164: str
    usuario_id: UUID | None = None
    recibe_briefing_diario: bool = True
    recibe_alertas_menciones: bool = True
    recibe_alertas_otras: bool = False
    opt_in_en: datetime | None = None
    opt_out_en: datetime | None = None
    activo: bool = False

    def __post_init__(self) -> None:
        nombre_strip = self.nombre.strip()
        if not nombre_strip:
            raise ValueError("Destinatario.nombre no puede ser vacío")
        # Normalizar nombre + teléfono (frozen → object.__setattr__).
        object.__setattr__(self, "nombre", nombre_strip)
        object.__setattr__(
            self, "telefono_e164", validar_e164(self.telefono_e164),
        )
        # Si opt_in y opt_out coexisten, opt_out debe ser posterior.
        if (
            self.opt_in_en is not None
            and self.opt_out_en is not None
            and self.opt_out_en < self.opt_in_en
        ):
            raise ValueError(
                "Destinatario.opt_out_en no puede ser anterior a opt_in_en",
            )
        # `activo` solo tiene sentido con opt-in vigente.
        if self.activo and (
            self.opt_in_en is None or self.opt_out_en is not None
        ):
            raise ValueError(
                "Destinatario.activo=True requiere opt_in vigente "
                "(opt_in_en set + opt_out_en None)",
            )

    @property
    def opt_in_vigente(self) -> bool:
        return self.opt_in_en is not None and self.opt_out_en is None

    def puede_recibir(self, tipo: TipoEnvio) -> bool:
        """True si el destinatario está activo + opt-in vigente + tiene
        el flag del canal correspondiente."""
        if not self.activo or not self.opt_in_vigente:
            return False
        if tipo == TipoEnvio.BRIEFING_DIARIO:
            return self.recibe_briefing_diario
        if tipo == TipoEnvio.ALERTA_MENCION:
            return self.recibe_alertas_menciones
        if tipo == TipoEnvio.ALERTA_BO:
            return self.recibe_alertas_otras
        return self.recibe_alertas_otras


# ---------------------------------------------------------------------------
# PlantillaWhatsApp
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlantillaWhatsApp:
    """Plantilla pre-aprobada por Meta. Identidad: `name + idioma`.

    `body_params` declara los placeholders del cuerpo en orden
    (`{{1}}`, `{{2}}`, ...). El sender valida que el envío provea
    valores para todos los params antes de hacer la request.

    `contenido_referencia` guarda el texto exacto para auditoría
    (Meta puede cambiar la versión y queremos saber qué mandamos).
    """

    name: str
    categoria: CategoriaPlantilla
    body_params: list[str]
    contenido_referencia: str
    idioma: IdiomaLiteral = "es_AR"
    estado_meta: EstadoMetaPlantilla = EstadoMetaPlantilla.PENDIENTE_APROBACION
    aprobada_en: datetime | None = None

    def __post_init__(self) -> None:
        name_strip = self.name.strip()
        if not name_strip:
            raise ValueError("PlantillaWhatsApp.name no puede ser vacío")
        if not re.match(r"^[a-z0-9_]+$", name_strip):
            raise ValueError(
                "PlantillaWhatsApp.name debe ser snake_case minúsculas "
                f"(recibido '{name_strip}')",
            )
        object.__setattr__(self, "name", name_strip)
        if not self.contenido_referencia.strip():
            raise ValueError(
                "PlantillaWhatsApp.contenido_referencia no puede ser vacío",
            )
        # Validar que body_params describa todos los placeholders del
        # contenido_referencia.
        placeholders_en_contenido = sorted(
            int(m) for m in re.findall(r"\{\{(\d+)\}\}", self.contenido_referencia)
        )
        if placeholders_en_contenido:
            esperados = list(range(1, len(self.body_params) + 1))
            unicos = sorted(set(placeholders_en_contenido))
            if unicos != esperados:
                raise ValueError(
                    "PlantillaWhatsApp.body_params no cuadra con los "
                    f"placeholders del contenido. Esperados {esperados}, "
                    f"contenido tiene {unicos}.",
                )

    @property
    def aprobada(self) -> bool:
        return self.estado_meta == EstadoMetaPlantilla.APROBADA


# ---------------------------------------------------------------------------
# EnvioWhatsApp
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EnvioWhatsApp:
    """Registro auditable de un envío (spec 17 §"Auditoría").

    `despacho_id` desnormalizado para tenant-scoping sin JOIN
    (ADR 0006). Aunque el destinatario ya tiene `despacho_id`, lo
    repetimos acá para que queries del histórico tenant-scoped no
    requieran JOIN — y porque el destinatario puede borrarse a futuro
    (purga) pero el envío queda como auditoría.

    `message_id_meta` se setea al recibir HTTP 200 de Meta. UNIQUE
    para correlacionar webhooks de status.

    `correlativo_id` agrupa múltiples envíos del mismo lote
    (ej. mismo briefing diario a 3 destinatarios del despacho).
    """

    id: UUID | None
    destinatario_id: UUID
    despacho_id: UUID
    plantilla_name: str
    tipo: TipoEnvio
    payload_params: dict[str, Any] = field(default_factory=dict)
    correlativo_id: UUID | None = None
    enviado_en: datetime | None = None
    estado: EstadoEnvio = EstadoEnvio.PENDIENTE
    message_id_meta: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.plantilla_name.strip():
            raise ValueError("EnvioWhatsApp.plantilla_name no puede ser vacío")
        # Consistencia estado ↔ campos.
        if self.estado == EstadoEnvio.ENVIADO and not self.message_id_meta:
            raise ValueError(
                "EnvioWhatsApp.estado=ENVIADO requiere message_id_meta",
            )
        if self.estado in (EstadoEnvio.FALLIDO, EstadoEnvio.RECHAZADO) and (
            not self.error
        ):
            raise ValueError(
                f"EnvioWhatsApp.estado={self.estado.value} requiere "
                "campo error",
            )

    @property
    def fue_exitoso(self) -> bool:
        return self.estado in (
            EstadoEnvio.ENVIADO,
            EstadoEnvio.ENTREGADO,
            EstadoEnvio.LEIDO,
        )

    @property
    def es_terminal(self) -> bool:
        """True si el envío llegó a un estado final (no se va a
        actualizar más)."""
        return self.estado in (
            EstadoEnvio.LEIDO,
            EstadoEnvio.FALLIDO,
            EstadoEnvio.RECHAZADO,
        )
