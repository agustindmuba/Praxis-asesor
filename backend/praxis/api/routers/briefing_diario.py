"""Router REST /briefing-diario (feat-42.4 + feat-41.7).

- GET  /briefing-diario/preview?fecha=YYYY-MM-DD
- POST /briefing-diario/enviar-ahora
  Dispara EnviarBriefingDiario con el sender REAL (Meta WhatsApp si
  hay creds, sino Fake) para todos los destinatarios elegibles del
  despacho. Útil cuando uno no quiere esperar al cron 7am.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from praxis.api.deps import CurrentContext, SessionDep, WhatsAppSenderDep
from praxis.application.use_cases.enviar_briefing_diario import (
    EnviarBriefingDiario,
)
from praxis.domain import AccionSugerida
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyAccionableEventoRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyComisionHcdnRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyMencionRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyOrdenDelDiaRepository,
)
from praxis.infrastructure.whatsapp.fake import FakeWhatsAppSender

router = APIRouter(prefix="/briefing-diario", tags=["briefing-diario"])


def _extraer_apellido(slug: str | None) -> str | None:
    """Heurística MVP, igual que la del router de comisiones."""
    if not slug:
        return None
    s = slug.strip()
    if "," in s:
        return s.split(",", 1)[0].strip().split()[-1]
    palabras = s.replace("_", " ").split()
    if len(palabras) >= 2:
        return palabras[-1]
    if len(s) >= 4 and s[1:].isalpha():
        return s[1:]
    return s


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
        menciones=SqlAlchemyMencionRepository(session),
        ordenes_del_dia=SqlAlchemyOrdenDelDiaRepository(session),
        comisiones=SqlAlchemyComisionHcdnRepository(session),
        legislador_titular_apellido=_extraer_apellido(
            ctx.despacho.legislador_titular_slug,
        ),
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


# ---------------------------------------------------------------------------
# Enviar AHORA (feat-41.7)
# ---------------------------------------------------------------------------


class ResultadoEnvioAhoraDTO(BaseModel):
    despacho_id: str
    destinatarios_objetivo: int
    enviados_ok: int
    fallidos_transitorios: int
    rechazados: int
    sin_contenido: bool
    sender_real: bool                     # True si fue WhatsAppCloudApiSender
    errores: list[str]


@router.post(
    "/enviar-ahora",
    response_model=ResultadoEnvioAhoraDTO,
    summary=(
        "Dispara el briefing diario para todos los destinatarios elegibles "
        "del despacho. Si hay creds Meta, usa el sender real (cuesta plata)."
    ),
)
async def enviar_briefing_ahora(
    ctx: CurrentContext,
    session: SessionDep,
    sender: WhatsAppSenderDep,
) -> ResultadoEnvioAhoraDTO:
    from praxis.infrastructure.whatsapp.cloud_api import WhatsAppCloudApiSender
    es_real = isinstance(sender, WhatsAppCloudApiSender)

    uc = EnviarBriefingDiario(
        destinatarios=SqlAlchemyDestinatarioRepository(session),
        envios=SqlAlchemyEnvioWhatsAppRepository(session),
        accionables_bo=SqlAlchemyNormaBOAccionableRepository(session),
        relevantes_noticias=SqlAlchemyArticuloRelevanteRepository(session),
        sender=sender,
        normas_bo=SqlAlchemyNormaBORepository(session),
        articulos=SqlAlchemyArticuloRepository(session),
        accionables_enriquecidos=SqlAlchemyAccionableEventoRepository(session),
        menciones=SqlAlchemyMencionRepository(session),
        ordenes_del_dia=SqlAlchemyOrdenDelDiaRepository(session),
        comisiones=SqlAlchemyComisionHcdnRepository(session),
        legislador_titular_apellido=_extraer_apellido(
            ctx.despacho.legislador_titular_slug,
        ),
    )

    ahora = datetime.now(UTC)
    resultado = await uc.ejecutar(
        despacho_id=ctx.despacho.id,
        fecha=ahora.date(),
        ahora=ahora,
    )
    await session.commit()

    if resultado.destinatarios_objetivo == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No hay destinatarios activos con `recibe_briefing_diario=True` "
                "y opt-in confirmado. Cargá uno en /configuracion y verificá "
                "que tenga opt_in_en seteado."
            ),
        )

    return ResultadoEnvioAhoraDTO(
        despacho_id=str(ctx.despacho.id),
        destinatarios_objetivo=resultado.destinatarios_objetivo,
        enviados_ok=resultado.enviados_ok,
        fallidos_transitorios=resultado.fallidos_transitorios,
        rechazados=resultado.rechazados,
        sin_contenido=resultado.sin_contenido,
        sender_real=es_real,
        errores=list(resultado.errores),
    )
