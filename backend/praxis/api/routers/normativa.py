"""Router REST /normativa (feat-42.6).

- POST /normativa/buscar : búsqueda semántica directa sobre el corpus.
- POST /proyectos-redaccion/{id}/validar-conflictos : evalúa el
  articulado del proyecto contra el corpus normativo cargado.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.normativa import (
    BuscarNormativaBody,
    ChunkSimilarDTO,
    ConflictoDetectadoDTO,
    ResultadoValidacionDTO,
)
from praxis.application.use_cases.validar_conflictos_normativos import (
    BuscarNormativaSimilar,
    ValidarConflictosNormativos,
)
from praxis.infrastructure.persistence.models import ProyectoRedaccionOrm

router = APIRouter(prefix="/normativa", tags=["normativa"])


@router.post(
    "/buscar",
    response_model=list[ChunkSimilarDTO],
    summary="Búsqueda semántica sobre el corpus normativo cargado.",
)
async def buscar_normativa(
    body: BuscarNormativaBody,
    ctx: CurrentContext,
    session: SessionDep,
) -> list[ChunkSimilarDTO]:
    uc = BuscarNormativaSimilar(session=session)
    chunks = await uc.ejecutar(query=body.query, top_k=body.top_k)
    return [
        ChunkSimilarDTO(
            fuente=c.fuente,
            articulo_label=c.articulo_label,
            texto=c.texto[:1500],
            distancia=c.distancia,
        )
        for c in chunks
    ]


# Este endpoint vive en /proyectos-redaccion conceptualmente pero
# armamos un router aparte para no inflar el router de proyectos.
router_validar = APIRouter(
    prefix="/proyectos-redaccion", tags=["proyectos-redaccion"],
)


@router_validar.post(
    "/{proyecto_id}/validar-conflictos",
    response_model=ResultadoValidacionDTO,
    summary="Evalúa el articulado del proyecto contra el corpus normativo.",
)
async def validar_conflictos(
    proyecto_id: UUID,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> ResultadoValidacionDTO:
    proyecto = (await session.execute(
        select(ProyectoRedaccionOrm).where(
            ProyectoRedaccionOrm.id == proyecto_id,
            ProyectoRedaccionOrm.despacho_id == ctx.despacho.id,
        ),
    )).scalar_one_or_none()
    if proyecto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not proyecto.articulado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generá primero el articulado del proyecto.",
        )

    # Verificar que haya corpus cargado.
    total_chunks = (await session.execute(
        select(func.count()).select_from(
            __import__(
                "praxis.infrastructure.persistence.models",
                fromlist=["ProyectoRedaccionOrm"],
            ).ProyectoRedaccionOrm,
        ),
    )).scalar_one()
    # Mejor checkear directo norma_juridica_chunk:
    from sqlalchemy import text as sa_text
    has_corpus = (await session.execute(
        sa_text("SELECT COUNT(*) FROM norma_juridica_chunk"),
    )).scalar_one()
    if has_corpus == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "El corpus normativo está vacío. Corré "
                "`scripts/cargar_corpus_normativo.py` primero."
            ),
        )

    uc = ValidarConflictosNormativos(session=session, llm=llm)
    conflictos = await uc.ejecutar(articulado=list(proyecto.articulado))

    return ResultadoValidacionDTO(
        proyecto_id=str(proyecto_id),
        n_articulos_evaluados=len(proyecto.articulado),
        conflictos=[
            ConflictoDetectadoDTO(
                indice_articulo_proyecto=c.indice_articulo_proyecto,
                fuente=c.fuente,
                articulo_label=c.articulo_label,
                severidad=c.severidad,
                explicacion=c.explicacion,
                texto_norma_referida=c.texto_norma_referida,
            )
            for c in conflictos
        ],
        sin_conflictos=len(conflictos) == 0,
    )
