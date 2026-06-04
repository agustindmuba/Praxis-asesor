"""Entidad de dominio para el perfil opositor de un despacho
(feat-42.1).

El **perfil opositor** es distinto del **perfil de interés**:

- `PerfilInteresDespacho` = qué áreas/distritos/alias filtran (matching técnico)
- `PerfilOpositorDespacho` = qué milita, contra qué, con qué tono (matching narrativo)

Se persiste como JSON en una tabla con UNIQUE en `despacho_id` (1 perfil
por despacho). Lo genera el bot de perfilamiento (Sonnet 4.5 sobre la
huella parlamentaria) y el asesor lo edita en `/configuracion/perfil-opositor`.

Cuando se edita manualmente, `editado_en` se actualiza; cuando se
re-infiere con el bot, `inferido_en` se actualiza. Los campos viven
intercambiados — el asesor puede tocar todos.

Este perfil se inyecta en los prompts de A+B+F (accionables BO,
accionables noticias, generación de tweets) para que el LLM hable
con la voz política del despacho.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


PERFIL_OPOSITOR_PROMPT_VERSION = "v1"


class TonoComunicacional(StrEnum):
    """Catálogo cerrado del tono. Si el LLM devuelve otra cosa, cae a MIXTO."""

    TECNICO_JURIDICO = "tecnico-juridico"
    MILITANTE_BLOQUE = "militante-bloque"
    DIALOGAL_CONCILIADOR = "dialogal-conciliador"
    FRONTAL_CONFRONTATIVO = "frontal-confrontativo"
    IRONICO = "ironico"
    MIXTO = "mixto"


class ConfianzaGlobal(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


@dataclass(frozen=True, slots=True)
class FiguraReferida:
    """Aliado o adversario inferido — nombre + razón evidencial."""

    nombre: str
    razon: str


@dataclass(slots=True)
class PerfilOpositorDespacho:
    """Perfil opositor declarado del despacho. 1 fila por despacho.

    No frozen: el asesor lo edita en UI y los campos cambian.
    """

    despacho_id: UUID
    bandera_principal: str
    banderas_secundarias: list[str] = field(default_factory=list)
    temas_de_cuidado: list[str] = field(default_factory=list)
    tono_comunicacional: TonoComunicacional = TonoComunicacional.MIXTO
    adversarios: list[FiguraReferida] = field(default_factory=list)
    aliados: list[FiguraReferida] = field(default_factory=list)
    linea_de_bloque: str = ""
    justificacion_evidencia: str = ""
    advertencias: list[str] = field(default_factory=list)
    confianza_global: ConfianzaGlobal = ConfianzaGlobal.MEDIA
    inferido_en: datetime | None = None      # última corrida del bot
    editado_en: datetime | None = None       # última edición manual
    modelo_inferencia: str | None = None
    prompt_version: str = PERFIL_OPOSITOR_PROMPT_VERSION

    def __post_init__(self) -> None:
        if not self.bandera_principal.strip():
            raise ValueError("PerfilOpositorDespacho.bandera_principal no puede ser vacío")
