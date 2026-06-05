"""Router REST /hub-diario (feat-42.5).

Endpoint consolidado para la pantalla principal del asesor cuando
abre Praxis cada mañana. Una sola llamada que devuelve:

- accion_requerida: items BO + Noticias accionables con tweets sugeridos.
- silenciar: items accionables que el bot recomienda no tocar.
- proxima_sesion: la OD futura más próxima si existe.
- stats: contadores rápidos del día.

Diseño: agrupa accionables por `accion == silencio_estrategico` vs.
el resto. Ordena por confianza desc + score desc.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas.hub_diario import (
    HubDiarioDTO,
    HubItemDTO,
    HubStatsDTO,
    ProximaSesionDTO,
    TweetSugeridoBreveDTO,
)
from praxis.domain import (
    AccionableEvento,
    AccionSugerida,
    Camara,
    TipoEvento,
)
from praxis.infrastructure.persistence.models import (
    ArticuloOrm,
    BriefingOrm,
    FuenteNoticiaOrm,
    MencionOrm,
    NormaBOOrm,
    OrdenDelDiaOrm,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyAccionableEventoRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyPerfilOpositorRepository,
)

router = APIRouter(prefix="/hub-diario", tags=["hub-diario"])

# Cap suave de items por sección. La UI muestra los primeros N
# directos; si querés ver más, vas a /bo o /noticias.
MAX_ACCION_REQUERIDA = 8
MAX_SILENCIAR = 5
MAX_TWEETS_POR_ITEM = 2  # sólo los primeros 2 tonos para no inflar la UI


@router.get("", response_model=HubDiarioDTO)
async def get_hub_diario(
    ctx: CurrentContext, session: SessionDep,
) -> HubDiarioDTO:
    ahora = datetime.now(UTC)
    hoy = ahora.date()
    despacho_id = ctx.despacho.id

    # 1. Perfil opositor cargado?
    perfil = await SqlAlchemyPerfilOpositorRepository(
        session,
    ).buscar_por_despacho(despacho_id)
    perfil_ok = perfil is not None

    # 2. Items: cargar accionables BO + articulos relevantes + sus
    #    AccionableEvento enriquecidos.
    items = await _resolver_items(
        session=session, despacho_id=despacho_id, fecha=hoy, ahora=ahora,
    )
    accion_requerida = [
        i for i in items
        if i.accion != AccionSugerida.SILENCIO_ESTRATEGICO
    ][:MAX_ACCION_REQUERIDA]
    silenciar = [
        i for i in items
        if i.accion == AccionSugerida.SILENCIO_ESTRATEGICO
    ][:MAX_SILENCIAR]

    # 3. Próxima sesión.
    proxima = await _proxima_sesion(
        session=session, despacho_id=despacho_id, desde=hoy,
    )

    # 4. Stats.
    stats = await _stats(
        session=session, despacho_id=despacho_id, fecha=hoy, ahora=ahora,
    )

    return HubDiarioDTO(
        fecha=hoy,
        perfil_opositor_cargado=perfil_ok,
        accion_requerida=accion_requerida,
        silenciar=silenciar,
        proxima_sesion=proxima,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolver_items(
    *,
    session,
    despacho_id: UUID,
    fecha: date,
    ahora: datetime,
) -> list[HubItemDTO]:
    """Trae accionables BO de hoy + artículos relevantes 24h y los
    enriquece con AccionableEvento si existe. Sólo incluye items que
    SÍ tienen AccionableEvento enriquecido — los que no se cubren en
    /bo y /noticias con el CTA "Generar acción"."""
    acc_repo = SqlAlchemyAccionableEventoRepository(session)
    bo_repo = SqlAlchemyNormaBOAccionableRepository(session)
    art_rel_repo = SqlAlchemyArticuloRelevanteRepository(session)

    bo_accionables = await bo_repo.listar_por_despacho_y_fecha(
        despacho_id=despacho_id, fecha=fecha, top_n=12,
    )
    art_relevantes = await art_rel_repo.listar_por_despacho_24h(
        despacho_id=despacho_id, hasta=ahora, top_n=12,
    )

    items: list[HubItemDTO] = []

    # BO items.
    for accionable in bo_accionables:
        enr = await acc_repo.buscar_por_evento(
            despacho_id=despacho_id,
            tipo_evento=TipoEvento.NORMA_BO,
            evento_id=accionable.norma_id,
        )
        if enr is None:
            continue
        norma = (await session.execute(
            select(NormaBOOrm).where(NormaBOOrm.id == accionable.norma_id),
        )).scalar_one_or_none()
        if norma is None:
            continue
        items.append(_item_desde_accionable(
            enr=enr,
            titulo=f"{norma.tipo_norma} {norma.numero_norma}: {(norma.sumario or '')[:80]}",
            url_detalle=f"/bo/{norma.id}",
            fuente_o_organismo=norma.organismo_emisor or "BO",
        ))

    # Noticias.
    for relevante in art_relevantes:
        enr = await acc_repo.buscar_por_evento(
            despacho_id=despacho_id,
            tipo_evento=TipoEvento.ARTICULO,
            evento_id=relevante.articulo_id,
        )
        if enr is None:
            continue
        art_fuente = (await session.execute(
            select(ArticuloOrm, FuenteNoticiaOrm)
            .join(FuenteNoticiaOrm, FuenteNoticiaOrm.id == ArticuloOrm.fuente_id)
            .where(ArticuloOrm.id == relevante.articulo_id),
        )).first()
        if art_fuente is None:
            continue
        art, fuente = art_fuente
        items.append(_item_desde_accionable(
            enr=enr,
            titulo=art.titulo,
            url_detalle=f"/noticias/{art.id}",
            fuente_o_organismo=fuente.nombre,
        ))

    return items


def _item_desde_accionable(
    *,
    enr: AccionableEvento,
    titulo: str,
    url_detalle: str,
    fuente_o_organismo: str,
) -> HubItemDTO:
    return HubItemDTO(
        tipo_evento=enr.tipo_evento,
        evento_id=enr.evento_id,
        titulo=titulo[:180],
        url_detalle=url_detalle,
        fuente_o_organismo=fuente_o_organismo,
        accion=enr.accion_sugerida,
        confianza=enr.confianza,
        razon_breve=enr.razon_para_despacho[:200],
        tweets=[
            TweetSugeridoBreveDTO(
                tono=t.tono, texto=t.texto, caracteres=t.caracteres,
            )
            for t in enr.tweets_sugeridos[:MAX_TWEETS_POR_ITEM]
        ],
    )


async def _proxima_sesion(
    *, session, despacho_id: UUID, desde: date,
) -> ProximaSesionDTO | None:
    """Trae la próxima OrdenDelDia con fecha_sesion >= hoy."""
    od_orm = (await session.execute(
        select(OrdenDelDiaOrm)
        .where(OrdenDelDiaOrm.fecha_sesion >= desde)
        .order_by(OrdenDelDiaOrm.fecha_sesion.asc())
        .limit(1),
    )).scalar_one_or_none()
    if od_orm is None:
        return None

    briefing = (await session.execute(
        select(BriefingOrm).where(
            BriefingOrm.despacho_id == despacho_id,
            BriefingOrm.orden_del_dia_id == od_orm.id,
        ),
    )).scalar_one_or_none()

    return ProximaSesionDTO(
        id=od_orm.id,
        titulo=od_orm.titulo,
        camara=Camara(od_orm.camara),
        fecha_sesion=od_orm.fecha_sesion,
        expedientes_count=len(od_orm.expedientes_ids or []),
        briefing_id=briefing.id if briefing else None,
    )


async def _stats(
    *, session, despacho_id: UUID, fecha: date, ahora: datetime,
) -> HubStatsDTO:
    bo_total = (await session.execute(
        select(func.count())
        .select_from(NormaBOOrm)
        .where(NormaBOOrm.fecha_publicacion == fecha),
    )).scalar_one()

    acc_repo = SqlAlchemyNormaBOAccionableRepository(session)
    bo_accionables = await acc_repo.listar_por_despacho_y_fecha(
        despacho_id=despacho_id, fecha=fecha, top_n=100,
    )

    art_rel_repo = SqlAlchemyArticuloRelevanteRepository(session)
    noticias_24h = await art_rel_repo.listar_por_despacho_24h(
        despacho_id=despacho_id, hasta=ahora, top_n=100,
    )

    menciones_24h = (await session.execute(
        select(func.count())
        .select_from(MencionOrm)
        .where(
            MencionOrm.despacho_id == despacho_id,
            MencionOrm.detectado_en >= ahora - _TIMEDELTA_24H,
        ),
    )).scalar_one()

    return HubStatsDTO(
        bo_total_hoy=int(bo_total),
        bo_accionables=len(bo_accionables),
        noticias_relevantes_24h=len(noticias_24h),
        menciones_24h=int(menciones_24h),
    )


from datetime import timedelta  # noqa: E402
_TIMEDELTA_24H = timedelta(hours=24)
