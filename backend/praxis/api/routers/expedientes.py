"""Router /expedientes — listado/búsqueda + ficha individual."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas import (
    ExpedienteFicha,
    FiltrosExpediente,
    ResultadoBusquedaDTO,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteRepository,
    SqlAlchemySeguimientoExpedienteRepository,
)

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


@router.get(
    "",
    summary="Búsqueda paginada de expedientes",
    response_model=ResultadoBusquedaDTO,
)
async def listar_expedientes(
    session: SessionDep,
    ctx: CurrentContext,
    filtros: Annotated[FiltrosExpediente, Query()],
) -> ResultadoBusquedaDTO:
    """Busca expedientes con los filtros del query string.

    El catálogo de expedientes es **global** (todos los despachos ven los
    mismos datos públicos). Lo tenant-scoped es el seguimiento (ver
    POST /seguimientos), no el expediente en sí.

    Igualmente exigimos auth (`ctx`) para no servir el catálogo a anónimos.
    """
    del ctx  # exige auth pero no se usa en este handler (reservado para autz por rol).
    repo = SqlAlchemyExpedienteRepository(session)
    resultado = await repo.buscar(filtros.to_domain())
    return ResultadoBusquedaDTO.from_domain(resultado)


@router.get(
    "/{expediente_id}",
    summary="Ficha completa de un expediente",
    response_model=ExpedienteFicha,
)
async def ficha_expediente(
    expediente_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> ExpedienteFicha:
    """Devuelve el expediente con firmantes, giros y trámite.

    Si el despacho activo sigue este expediente, embebe el seguimiento
    para que el frontend pueda mostrar prioridad/responsable/estado en
    la misma vista, sin un round trip extra.
    """
    exp_repo = SqlAlchemyExpedienteRepository(session)
    expediente = await exp_repo.buscar_por_id(expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado",
        )

    seg_repo = SqlAlchemySeguimientoExpedienteRepository(session)
    seguimiento = await seg_repo.buscar(
        despacho_id=ctx.despacho.id,
        expediente_id=expediente_id,
    )

    return ExpedienteFicha.from_domain(expediente, seguimiento=seguimiento)
