"""Routers /ordenes-del-dia y /briefings.

Endpoints REST que exponen el motor del Briefing (feat/29) al frontend.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.briefing import (
    BriefingCrear,
    BriefingDTO,
    OrdenDelDiaCrear,
    OrdenDelDiaDTO,
)
from praxis.application import GenerarBriefing
from praxis.domain import OrdenDelDia
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyBriefingRepository,
    SqlAlchemyExpedienteAreaTematicaRepository,
    SqlAlchemyExpedienteRepository,
    SqlAlchemyOrdenDelDiaRepository,
    SqlAlchemySeguimientoExpedienteRepository,
)

router_ordenes = APIRouter(prefix="/ordenes-del-dia", tags=["briefings"])
router_briefings = APIRouter(prefix="/briefings", tags=["briefings"])


# ---------------------------------------------------------------------------
# /ordenes-del-dia
# ---------------------------------------------------------------------------


@router_ordenes.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=OrdenDelDiaDTO,
    summary="Crear un OrdenDelDia para el despacho actual",
)
async def crear_orden_del_dia(
    body: OrdenDelDiaCrear,
    session: SessionDep,
    ctx: CurrentContext,
) -> OrdenDelDiaDTO:
    """El asesor pega la lista de expedientes que se van a tratar.

    Tenant-scoped: el OD queda asignado al despacho del request.
    """
    repo = SqlAlchemyOrdenDelDiaRepository(session, despacho_id=ctx.despacho.id)
    od = OrdenDelDia(
        camara=body.camara,
        fecha_sesion=body.fecha_sesion,
        hora_sesion=body.hora_sesion,
        titulo=body.titulo,
        expedientes_ids=list(body.expedientes_ids),
    )
    creado = await repo.crear(od)
    await session.commit()
    return OrdenDelDiaDTO.model_validate(creado, from_attributes=True)


@router_ordenes.get(
    "/{od_id}",
    response_model=OrdenDelDiaDTO,
    summary="Recupera un OrdenDelDia del despacho",
)
async def obtener_orden_del_dia(
    od_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> OrdenDelDiaDTO:
    repo = SqlAlchemyOrdenDelDiaRepository(session, despacho_id=ctx.despacho.id)
    od = await repo.buscar_por_id(od_id)
    if od is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return OrdenDelDiaDTO.model_validate(od, from_attributes=True)


@router_ordenes.get(
    "",
    response_model=list[OrdenDelDiaDTO],
    summary="Lista los OD del despacho ordenados por fecha desc",
)
async def listar_ordenes_del_dia(
    session: SessionDep,
    ctx: CurrentContext,
    limit: int = 20,
) -> list[OrdenDelDiaDTO]:
    repo = SqlAlchemyOrdenDelDiaRepository(session, despacho_id=ctx.despacho.id)
    ods = await repo.listar_por_despacho(ctx.despacho.id, limit=limit)
    return [OrdenDelDiaDTO.model_validate(od, from_attributes=True) for od in ods]


# ---------------------------------------------------------------------------
# /briefings
# ---------------------------------------------------------------------------


@router_briefings.post(
    "",
    response_model=BriefingDTO,
    summary="Genera o devuelve el briefing del despacho para un OD",
)
async def crear_briefing(
    body: BriefingCrear,
    session: SessionDep,
    ctx: CurrentContext,
    llm: LlmProviderDep,
) -> BriefingDTO:
    """Cache-aware. Si `regenerar=true`, borra el viejo y regenera."""
    uc = GenerarBriefing(
        session=session,
        expedientes=SqlAlchemyExpedienteRepository(session),
        seguimientos=SqlAlchemySeguimientoExpedienteRepository(session),
        clasificaciones=SqlAlchemyExpedienteAreaTematicaRepository(session),
        ordenes_del_dia=SqlAlchemyOrdenDelDiaRepository(
            session, despacho_id=ctx.despacho.id,
        ),
        briefings=SqlAlchemyBriefingRepository(session),
        llm=llm,
    )
    try:
        briefing = await uc.execute(
            despacho_id=ctx.despacho.id,
            orden_del_dia_id=body.orden_del_dia_id,
            regenerar=body.regenerar,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
        ) from exc
    await session.commit()
    return BriefingDTO.model_validate(briefing, from_attributes=True)


@router_briefings.get(
    "/{briefing_id}",
    response_model=BriefingDTO,
    summary="Recupera un briefing por id",
)
async def obtener_briefing(
    briefing_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> BriefingDTO:
    from sqlalchemy import select

    from praxis.infrastructure.persistence.models import BriefingOrm

    stmt = select(BriefingOrm).where(
        BriefingOrm.id == briefing_id,
        BriefingOrm.despacho_id == ctx.despacho.id,
    )
    result = await session.execute(stmt)
    orm = result.scalar_one_or_none()
    if orm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    from praxis.infrastructure.persistence.mappers import to_briefing

    return BriefingDTO.model_validate(to_briefing(orm), from_attributes=True)
