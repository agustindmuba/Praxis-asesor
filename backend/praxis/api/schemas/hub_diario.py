"""Schemas Pydantic para /hub-diario (feat-42.5).

Consolida lo que el asesor necesita ver al abrir Praxis Asesor cada
mañana:
- Accionables que requieren acción hoy (BO + Noticias, accion ≠ silencio).
- Items a silenciar (accion = silencio_estratégico).
- Próxima sesión parlamentaria con su briefing si existe.
- Stats rápidas del día.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from praxis.domain import (
    AccionSugerida,
    Camara,
    ConfianzaAccionable,
    TipoEvento,
)


class TweetSugeridoBreveDTO(BaseModel):
    tono: str
    texto: str
    caracteres: int


class HubItemDTO(BaseModel):
    """Una entrada en el hub. Polimórfica por tipo_evento."""

    tipo_evento: TipoEvento
    evento_id: UUID
    titulo: str
    url_detalle: str                 # path frontend, ej /bo/{id} o /noticias/{id}
    fuente_o_organismo: str           # "ANMAT" o "Infobae" o "—"
    accion: AccionSugerida
    confianza: ConfianzaAccionable
    razon_breve: str
    tweets: list[TweetSugeridoBreveDTO]


class ProximaSesionDTO(BaseModel):
    id: UUID
    titulo: str | None
    camara: Camara
    fecha_sesion: date
    expedientes_count: int
    briefing_id: UUID | None          # si ya se generó


class HubStatsDTO(BaseModel):
    bo_total_hoy: int
    bo_accionables: int
    noticias_relevantes_24h: int
    menciones_24h: int


class HubDiarioDTO(BaseModel):
    fecha: date
    perfil_opositor_cargado: bool
    accion_requerida: list[HubItemDTO]
    silenciar: list[HubItemDTO]
    proxima_sesion: ProximaSesionDTO | None
    stats: HubStatsDTO
