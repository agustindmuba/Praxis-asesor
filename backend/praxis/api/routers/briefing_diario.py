"""Router REST /briefing-diario/preview (feat-42.4).

Endpoint readonly que muestra cómo va a quedar el briefing diario que
se le va a enviar al destinatario por WhatsApp.

- GET /briefing-diario/preview?fecha=YYYY-MM-DD
  Default: fecha de hoy. Sin destinatarios involucrados — solo
  ejecuta el use case en modo "preview" (con FakeSender stub) y
  devuelve el resumen_corto + body_rich + lista de items.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from praxis.api.deps import CurrentContext, SessionDep
from praxis.application.use_cases.enviar_briefing_diario import (
    EnviarBriefingDiario,
)
from praxis.domain import AccionSugerida
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyAccionableEventoRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
)
from praxis.infrastructure.whatsapp.fake import FakeWhatsAppSender

router = APIRouter(prefix="/briefing-diario", tags=["briefing-diario"])


class ItemPreviewDTO(BaseModel):
    titulo_corto: str
    accion: AccionSugerida | None
    razon_breve: str | None


class BriefingDiarioPreviewDTO(BaseModel):
    fecha: date
    despacho_id: str
    sin_contenido: bool
    resumen_corto: str
    body_rich: str
    items_bo: list[ItemPreviewDTO]
    items_noticias: list[ItemPreviewDTO]


@router.get(
    "/preview",
    response_model=BriefingDiarioPreviewDTO,
    summary="Preview del briefing diario antes del envío (no manda nada).",
)
async def preview_briefing_diario(
    ctx: CurrentContext,
    session: SessionDep,
    fecha: Annotated[date | None, Query()] = None,
) -> BriefingDiarioPreviewDTO:
    fecha_eff = fecha or datetime.now(UTC).date()

    # FakeSender garantiza que NO se manda nada real. Como tampoco
    # listamos destinatarios elegibles (no hay enviados_ok), el use
    # case devuelve solo el preview computado.
    uc = EnviarBriefingDiario(
        destinatarios=SqlAlchemyDestinatarioRepository(session),
        envios=SqlAlchemyEnvioWhatsAppRepository(session),
        accionables_bo=SqlAlchemyNormaBOAccionableRepository(session),
        relevantes_noticias=SqlAlchemyArticuloRelevanteRepository(session),
        sender=FakeWhatsAppSender(),
        normas_bo=SqlAlchemyNormaBORepository(session),
        articulos=SqlAlchemyArticuloRepository(session),
        accionables_enriquecidos=SqlAlchemyAccionableEventoRepository(session),
    )
    # Forzamos preview: ahorramos pasarle destinatarios eliminándolos
    # del resultado. El use case ya distingue "sin destinatarios pero
    # con contenido" devolviendo resumen/body sin enviar nada.
    resultado = await uc.ejecutar(
        despacho_id=ctx.despacho.id,
        fecha=fecha_eff,
        ahora=datetime.now(UTC),
    )

    return BriefingDiarioPreviewDTO(
        fecha=fecha_eff,
        despacho_id=str(ctx.despacho.id),
        sin_contenido=resultado.sin_contenido,
        resumen_corto=resultado.resumen_corto,
        body_rich=resultado.body_rich,
        items_bo=[
            ItemPreviewDTO(
                titulo_corto=it.titulo_corto,
                accion=it.accion,
                razon_breve=it.razon_breve,
            )
            for it in resultado.items_bo
        ],
        items_noticias=[
            ItemPreviewDTO(
                titulo_corto=it.titulo_corto,
                accion=it.accion,
                razon_breve=it.razon_breve,
            )
            for it in resultado.items_noticias
        ],
    )
