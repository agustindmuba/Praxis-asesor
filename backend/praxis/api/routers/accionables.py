"""Router REST /accionables (feat-42.2).

- POST /accionables/bo/{norma_id}/generar : genera (o devuelve cacheado).
- GET  /accionables/bo/{norma_id}         : devuelve cacheado o 404.
- POST /accionables/articulo/{art_id}/generar
- GET  /accionables/articulo/{art_id}

El POST con ?regenerar=true fuerza re-generación.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.accionable import AccionableDTO, TweetSugeridoDTO
from praxis.application.use_cases.generar_accionable_con_perfil import (
    GenerarAccionableConPerfil,
    PayloadEvento,
)
from praxis.domain import AccionableEvento, TipoEvento
from praxis.infrastructure.persistence.models import (
    ArticuloOrm,
    ClasificacionNormaBOOrm,
    NormaBOOrm,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyAccionableEventoRepository,
    SqlAlchemyPerfilOpositorRepository,
)

router = APIRouter(prefix="/accionables", tags=["accionables"])


def _to_dto(acc: AccionableEvento) -> AccionableDTO:
    """Construye el DTO desde la entidad. Same pattern que perfil_opositor."""
    return AccionableDTO(
        id=acc.id,
        despacho_id=acc.despacho_id,
        tipo_evento=acc.tipo_evento,
        evento_id=acc.evento_id,
        razon_para_despacho=acc.razon_para_despacho,
        accion_sugerida=acc.accion_sugerida,
        explicacion_accion=acc.explicacion_accion,
        tweets_sugeridos=[
            TweetSugeridoDTO(
                tono=t.tono, texto=t.texto, caracteres=t.caracteres,
            )
            for t in acc.tweets_sugeridos
        ],
        confianza=acc.confianza,
        generado_en=acc.generado_en,
        editado_en=acc.editado_en,
        modelo=acc.modelo,
        prompt_version=acc.prompt_version,
    )


# ---------------------------------------------------------------------------
# BO
# ---------------------------------------------------------------------------


@router.get(
    "/bo/{norma_id}",
    response_model=AccionableDTO | None,
    summary="Trae el accionable cacheado para una norma BO (puede ser None).",
)
async def get_accionable_bo(
    norma_id: UUID, ctx: CurrentContext, session: SessionDep,
) -> AccionableDTO | None:
    repo = SqlAlchemyAccionableEventoRepository(session)
    acc = await repo.buscar_por_evento(
        despacho_id=ctx.despacho.id,
        tipo_evento=TipoEvento.NORMA_BO,
        evento_id=norma_id,
    )
    return _to_dto(acc) if acc else None


@router.post(
    "/bo/{norma_id}/generar",
    response_model=AccionableDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Genera (o devuelve cacheado) accionable para una norma BO.",
)
async def generar_accionable_bo(
    norma_id: UUID,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
    regenerar: Annotated[bool, Query()] = False,
) -> AccionableDTO:
    # Cargar la norma + clasificación para armar el payload
    stmt = (
        select(NormaBOOrm, ClasificacionNormaBOOrm)
        .outerjoin(
            ClasificacionNormaBOOrm,
            ClasificacionNormaBOOrm.norma_id == NormaBOOrm.id,
        )
        .where(NormaBOOrm.id == norma_id)
    )
    result = (await session.execute(stmt)).first()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Norma BO {norma_id} no encontrada",
        )
    norma, clasif = result
    payload = PayloadEvento(
        titulo=f"{norma.tipo_norma} {norma.numero_norma}",
        resumen=norma.sumario or "",
        tipo=TipoEvento.NORMA_BO,
        evento_id=norma.id,
        metadata_extra={
            "fecha_publicacion": str(norma.fecha_publicacion),
            "area_tematica": clasif.area_tematica if clasif else None,
            "referencias_legales": (clasif.referencias_legales or [])[:8] if clasif else [],
        },
    )
    uc = GenerarAccionableConPerfil(
        accionables=SqlAlchemyAccionableEventoRepository(session),
        perfiles=SqlAlchemyPerfilOpositorRepository(session),
        llm=llm,
    )
    try:
        acc = await uc.ejecutar(
            despacho_id=ctx.despacho.id, payload=payload, regenerar=regenerar,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        ) from e
    await session.commit()
    return _to_dto(acc)


# ---------------------------------------------------------------------------
# Artículo
# ---------------------------------------------------------------------------


@router.get(
    "/articulo/{articulo_id}",
    response_model=AccionableDTO | None,
)
async def get_accionable_articulo(
    articulo_id: UUID, ctx: CurrentContext, session: SessionDep,
) -> AccionableDTO | None:
    repo = SqlAlchemyAccionableEventoRepository(session)
    acc = await repo.buscar_por_evento(
        despacho_id=ctx.despacho.id,
        tipo_evento=TipoEvento.ARTICULO,
        evento_id=articulo_id,
    )
    return _to_dto(acc) if acc else None


@router.post(
    "/articulo/{articulo_id}/generar",
    response_model=AccionableDTO,
    status_code=status.HTTP_201_CREATED,
)
async def generar_accionable_articulo(
    articulo_id: UUID,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
    regenerar: Annotated[bool, Query()] = False,
) -> AccionableDTO:
    art = (await session.execute(
        select(ArticuloOrm).where(ArticuloOrm.id == articulo_id),
    )).scalar_one_or_none()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artículo {articulo_id} no encontrado",
        )
    payload = PayloadEvento(
        titulo=art.titulo,
        resumen=art.bajada_propia or "",
        tipo=TipoEvento.ARTICULO,
        evento_id=art.id,
        metadata_extra={
            "url": art.url,
            "fuente_id": str(art.fuente_id),
            "publicado_en": str(art.publicado_en) if art.publicado_en else None,
        },
    )
    uc = GenerarAccionableConPerfil(
        accionables=SqlAlchemyAccionableEventoRepository(session),
        perfiles=SqlAlchemyPerfilOpositorRepository(session),
        llm=llm,
    )
    try:
        acc = await uc.ejecutar(
            despacho_id=ctx.despacho.id, payload=payload, regenerar=regenerar,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        ) from e
    await session.commit()
    return _to_dto(acc)

