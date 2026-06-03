"""Routers `/noticias` y `/menciones` — vistas del despacho (spec 16).

Endpoints tenant-scoped via `X-Despacho-Id` + `CurrentContext`:

- GET `/noticias`: top-N artículos relevantes del despacho en las
  últimas 24h (ordenados por score DESC). Paréntesis: solo devuelve
  los que ya pasaron por el scoring del Celery (40.5.B) — los
  artículos sin perfil de interés no aparecen.
- GET `/noticias/{id}`: detalle de un artículo (sin texto del cuerpo)
  con clasificación + menciones del despacho asociadas a ese artículo.
- GET `/menciones`: histórico tenant-scoped con filtros (tono, fuente,
  ventana temporal).
- GET `/menciones/{id}`: detalle de una mención.
- GET `/fuentes`: catálogo de medios visibles al despacho (globales +
  DISTRITALES suscriptos).

Las respuestas NUNCA exponen el cuerpo del artículo (ADR 0006).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas.noticia import (
    ArticuloDetalleDTO,
    ArticuloDTO,
    ArticuloRelevanteConArticuloDTO,
    ArticuloRelevanteDTO,
    ClasificacionArticuloDTO,
    FuenteNoticiaDTO,
    MencionConArticuloDTO,
    MencionDTO,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMencionRepository,
)

router_noticias = APIRouter(prefix="/noticias", tags=["noticias"])
router_menciones = APIRouter(prefix="/menciones", tags=["menciones"])
router_fuentes = APIRouter(prefix="/fuentes", tags=["fuentes"])


DEFAULT_TOP_N = 10
DEFAULT_VENTANA_HISTORICO_DIAS = 30


# ---------------------------------------------------------------------------
# GET /noticias
# ---------------------------------------------------------------------------


@router_noticias.get(
    "",
    response_model=list[ArticuloRelevanteConArticuloDTO],
    summary="Top-N artículos relevantes del despacho en las últimas 24h",
)
async def listar_relevantes(
    session: SessionDep,
    ctx: CurrentContext,
    top_n: Annotated[int, Query(ge=1, le=50)] = DEFAULT_TOP_N,
) -> list[ArticuloRelevanteConArticuloDTO]:
    """Lista los `ArticuloRelevante` del despacho ordenados por score
    DESC en las últimas 24 horas. Hidrata artículo + fuente +
    clasificación para evitar N+1 en el frontend."""
    relevantes_repo = SqlAlchemyArticuloRelevanteRepository(session)
    arts_repo = SqlAlchemyArticuloRepository(session)
    fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)
    clasifs_repo = SqlAlchemyClasificacionArticuloRepository(session)

    ahora = datetime.now(UTC)
    relevantes = await relevantes_repo.listar_por_despacho_24h(
        despacho_id=ctx.despacho.id,
        hasta=ahora,
        top_n=top_n,
    )

    salida: list[ArticuloRelevanteConArticuloDTO] = []
    for r in relevantes:
        art = await arts_repo.buscar_por_id(r.articulo_id)
        if art is None:
            # Edge: artículo purgado después del scoring.
            continue
        fuente = await fuentes_repo.buscar_por_id(art.fuente_id)
        if fuente is None:
            continue
        clasif = await clasifs_repo.buscar_por_articulo(art.id)  # type: ignore[arg-type]
        salida.append(
            ArticuloRelevanteConArticuloDTO(
                relevante=ArticuloRelevanteDTO.model_validate(
                    r, from_attributes=True,
                ),
                articulo=ArticuloDTO.model_validate(art, from_attributes=True),
                fuente=FuenteNoticiaDTO.model_validate(
                    fuente, from_attributes=True,
                ),
                clasificacion=(
                    ClasificacionArticuloDTO.model_validate(
                        clasif, from_attributes=True,
                    )
                    if clasif is not None
                    else None
                ),
            ),
        )
    return salida


# ---------------------------------------------------------------------------
# GET /noticias/{id}
# ---------------------------------------------------------------------------


@router_noticias.get(
    "/{articulo_id}",
    response_model=ArticuloDetalleDTO,
    summary="Detalle del artículo (sin texto del cuerpo)",
)
async def detalle_articulo(
    articulo_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> ArticuloDetalleDTO:
    arts_repo = SqlAlchemyArticuloRepository(session)
    fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)
    clasifs_repo = SqlAlchemyClasificacionArticuloRepository(session)
    relevantes_repo = SqlAlchemyArticuloRelevanteRepository(session)
    menciones_repo = SqlAlchemyMencionRepository(session)

    art = await arts_repo.buscar_por_id(articulo_id)
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo no existe",
        )
    fuente = await fuentes_repo.buscar_por_id(art.fuente_id)
    if fuente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fuente del artículo no existe",
        )
    clasif = await clasifs_repo.buscar_por_articulo(articulo_id)

    # Relevante del despacho actual (tenant-scoped — buscamos en 24h).
    relevantes = await relevantes_repo.listar_por_despacho_24h(
        despacho_id=ctx.despacho.id,
        hasta=datetime.now(UTC),
    )
    relevante = next(
        (r for r in relevantes if r.articulo_id == articulo_id), None,
    )

    # Menciones del despacho asociadas a este artículo.
    menciones_historico = await menciones_repo.listar_historico(
        despacho_id=ctx.despacho.id,
        desde=datetime.now(UTC) - timedelta(days=365),
        hasta=datetime.now(UTC) + timedelta(minutes=1),
    )
    menciones = [m for m in menciones_historico if m.articulo_id == articulo_id]

    return ArticuloDetalleDTO(
        articulo=ArticuloDTO.model_validate(art, from_attributes=True),
        fuente=FuenteNoticiaDTO.model_validate(fuente, from_attributes=True),
        clasificacion=(
            ClasificacionArticuloDTO.model_validate(
                clasif, from_attributes=True,
            )
            if clasif is not None
            else None
        ),
        relevante=(
            ArticuloRelevanteDTO.model_validate(
                relevante, from_attributes=True,
            )
            if relevante is not None
            else None
        ),
        menciones=[
            MencionDTO.model_validate(m, from_attributes=True)
            for m in menciones
        ],
    )


# ---------------------------------------------------------------------------
# GET /menciones
# ---------------------------------------------------------------------------


@router_menciones.get(
    "",
    response_model=list[MencionConArticuloDTO],
    summary="Histórico tenant-scoped de menciones con filtros",
)
async def listar_menciones(
    session: SessionDep,
    ctx: CurrentContext,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
    tono: Annotated[str | None, Query()] = None,
    fuente_id: Annotated[UUID | None, Query()] = None,
) -> list[MencionConArticuloDTO]:
    """Histórico de menciones del despacho. Ventana default: últimos
    30 días si no se pasan `desde`/`hasta`."""
    menciones_repo = SqlAlchemyMencionRepository(session)
    arts_repo = SqlAlchemyArticuloRepository(session)
    fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)

    ahora = datetime.now(UTC)
    desde_efectivo = desde or ahora - timedelta(days=DEFAULT_VENTANA_HISTORICO_DIAS)
    hasta_efectivo = hasta or ahora

    menciones = await menciones_repo.listar_historico(
        despacho_id=ctx.despacho.id,
        desde=desde_efectivo,
        hasta=hasta_efectivo,
        tono=tono,
        fuente_id=fuente_id,
    )

    salida: list[MencionConArticuloDTO] = []
    for m in menciones:
        art = await arts_repo.buscar_por_id(m.articulo_id)
        if art is None:
            continue
        fuente = await fuentes_repo.buscar_por_id(art.fuente_id)
        if fuente is None:
            continue
        salida.append(
            MencionConArticuloDTO(
                mencion=MencionDTO.model_validate(m, from_attributes=True),
                articulo=ArticuloDTO.model_validate(art, from_attributes=True),
                fuente=FuenteNoticiaDTO.model_validate(
                    fuente, from_attributes=True,
                ),
            ),
        )
    return salida


# ---------------------------------------------------------------------------
# GET /menciones/{id}
# ---------------------------------------------------------------------------


@router_menciones.get(
    "/{mencion_id}",
    response_model=MencionConArticuloDTO,
    summary="Detalle de una mención (tenant-scoped)",
)
async def detalle_mencion(
    mencion_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> MencionConArticuloDTO:
    menciones_repo = SqlAlchemyMencionRepository(session)
    arts_repo = SqlAlchemyArticuloRepository(session)
    fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)

    m = await menciones_repo.buscar_por_id(
        despacho_id=ctx.despacho.id, mencion_id=mencion_id,
    )
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mención no existe",
        )
    art = await arts_repo.buscar_por_id(m.articulo_id)
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artículo de la mención no existe",
        )
    fuente = await fuentes_repo.buscar_por_id(art.fuente_id)
    if fuente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fuente del artículo no existe",
        )
    return MencionConArticuloDTO(
        mencion=MencionDTO.model_validate(m, from_attributes=True),
        articulo=ArticuloDTO.model_validate(art, from_attributes=True),
        fuente=FuenteNoticiaDTO.model_validate(fuente, from_attributes=True),
    )


# ---------------------------------------------------------------------------
# GET /fuentes
# ---------------------------------------------------------------------------


@router_fuentes.get(
    "",
    response_model=list[FuenteNoticiaDTO],
    summary="Catálogo de fuentes visibles para el despacho",
)
async def listar_fuentes(
    session: SessionDep,
    ctx: CurrentContext,
) -> list[FuenteNoticiaDTO]:
    """Globales (NACIONAL + POLITICO) + DISTRITALES suscriptas por
    este despacho via puente."""
    repo = SqlAlchemyFuenteNoticiaRepository(session)
    fuentes = await repo.listar_para_despacho(ctx.despacho.id)
    return [
        FuenteNoticiaDTO.model_validate(f, from_attributes=True)
        for f in fuentes
    ]
