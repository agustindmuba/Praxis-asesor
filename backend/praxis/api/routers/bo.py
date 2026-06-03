"""Router `/bo` — endpoints REST del Boletín Oficial accionable (spec 15).

Endpoints:

- `GET /bo/normas?fecha=YYYY-MM-DD&seccion=` — lista todas las normas
  del día. NO tenant-scoped: las normas del BO son públicas.
- `GET /bo/normas/{id}` — detalle estructurado (NO incluye texto del
  cuerpo; el usuario va al BO oficial vía `url_oficial`).
- `GET /bo/accionables?fecha=YYYY-MM-DD&top_n=` — top-N accionables
  para el despacho del request. Tenant-scoped por `current_context`.
- `POST /bo/normas/reclasificar-perfil?fecha=YYYY-MM-DD` — recálculo
  on-demand cuando el despacho cambia su perfil de interés. Tenant-scoped.

El endpoint de reclasificación es el punto donde el frontend dispara
el caso de uso `EvaluarAccionabilidadPorDespacho` para refrescar la
vista del briefing sin esperar al beat nocturno.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.bo import (
    ClasificacionNormaBODTO,
    NormaBOAccionableConNormaDTO,
    NormaBOAccionableDTO,
    NormaBODetalleDTO,
    NormaBODTO,
    ReclasificarPerfilResponse,
)
from praxis.application.use_cases.evaluar_accionabilidad_bo import (
    TOP_N_ACCIONABLES_DEFAULT,
    EvaluarAccionabilidadPorDespacho,
)
from praxis.domain import SeccionBO
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyNormaBOTextoRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)

router = APIRouter(prefix="/bo", tags=["bo"])


# ---------------------------------------------------------------------------
# GET /bo/normas
# ---------------------------------------------------------------------------


@router.get(
    "/normas",
    response_model=list[NormaBODTO],
    summary="Lista las normas del BO de una fecha",
)
async def listar_normas(
    fecha: date,
    session: SessionDep,
    seccion: Annotated[SeccionBO | None, Query()] = None,
) -> list[NormaBODTO]:
    """Listado no-tenant-scoped (las normas del BO son públicas y
    compartidas entre despachos)."""
    repo = SqlAlchemyNormaBORepository(session)
    normas = await repo.listar_por_fecha(fecha, seccion=seccion)
    return [NormaBODTO.model_validate(n, from_attributes=True) for n in normas]


# ---------------------------------------------------------------------------
# GET /bo/normas/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/normas/{norma_id}",
    response_model=NormaBODetalleDTO,
    summary="Detalle estructurado de una norma (sin texto completo)",
)
async def detalle_norma(
    norma_id: UUID, session: SessionDep,
) -> NormaBODetalleDTO:
    normas = SqlAlchemyNormaBORepository(session)
    clasifs = SqlAlchemyClasificacionNormaBORepository(session)

    norma = await normas.buscar_por_id(norma_id)
    if norma is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Norma no existe",
        )
    cl = await clasifs.buscar_por_norma(norma_id)
    return NormaBODetalleDTO(
        norma=NormaBODTO.model_validate(norma, from_attributes=True),
        clasificacion=(
            ClasificacionNormaBODTO.model_validate(cl, from_attributes=True)
            if cl is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# GET /bo/accionables
# ---------------------------------------------------------------------------


@router.get(
    "/accionables",
    response_model=list[NormaBOAccionableConNormaDTO],
    summary="Top-N accionables del despacho para una fecha",
)
async def listar_accionables(
    fecha: date,
    session: SessionDep,
    ctx: CurrentContext,
    top_n: Annotated[int, Query(ge=1, le=50)] = TOP_N_ACCIONABLES_DEFAULT,
) -> list[NormaBOAccionableConNormaDTO]:
    accionables = SqlAlchemyNormaBOAccionableRepository(session)
    normas_repo = SqlAlchemyNormaBORepository(session)

    rows = await accionables.listar_por_despacho_y_fecha(
        despacho_id=ctx.despacho.id, fecha=fecha, top_n=top_n,
    )
    # Hidratamos la norma de cada accionable. N+1 manejable v1
    # (top_n max 50). Optimizable con un JOIN si crece.
    salida: list[NormaBOAccionableConNormaDTO] = []
    for a in rows:
        norma = await normas_repo.buscar_por_id(a.norma_id)
        if norma is None:
            # Edge: norma borrada después del scoring; saltamos.
            continue
        salida.append(
            NormaBOAccionableConNormaDTO(
                accionable=NormaBOAccionableDTO.model_validate(
                    a, from_attributes=True,
                ),
                norma=NormaBODTO.model_validate(norma, from_attributes=True),
            )
        )
    return salida


# ---------------------------------------------------------------------------
# POST /bo/normas/reclasificar-perfil
# ---------------------------------------------------------------------------


@router.post(
    "/normas/reclasificar-perfil",
    response_model=ReclasificarPerfilResponse,
    summary="Recalcula accionables del despacho para una fecha",
)
async def reclasificar_perfil(
    fecha: date,
    session: SessionDep,
    ctx: CurrentContext,
    llm: LlmProviderDep,
) -> ReclasificarPerfilResponse:
    """Dispara recálculo on-demand de accionables. Útil cuando el
    despacho edita su perfil de interés y quiere ver los efectos en
    el briefing del día sin esperar el beat nocturno."""
    uc = EvaluarAccionabilidadPorDespacho(
        perfiles=SqlAlchemyPerfilInteresDespachoRepository(session),
        normas=SqlAlchemyNormaBORepository(session),
        textos=SqlAlchemyNormaBOTextoRepository(session),
        clasificaciones=SqlAlchemyClasificacionNormaBORepository(session),
        accionables=SqlAlchemyNormaBOAccionableRepository(session),
        llm=llm,
    )
    creadas = await uc.execute(
        despacho_id=ctx.despacho.id, fecha=fecha,
    )
    await session.commit()
    return ReclasificarPerfilResponse(
        fecha=fecha,
        accionables_recalculadas=len(creadas),
    )
