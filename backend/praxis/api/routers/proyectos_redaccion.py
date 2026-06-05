"""Router REST /proyectos-redaccion (feat-42.3).

CRUD básico + 3 endpoints de asistencia LLM:
- POST /proyectos-redaccion/{id}/asistir/articulado
- POST /proyectos-redaccion/{id}/asistir/fundamentos
- POST /proyectos-redaccion/asistir/refinar
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.proyecto_redaccion import (
    ActualizarProyectoBody,
    CrearProyectoBody,
    GenerarArticuladoBody,
    ProyectoRedaccionDTO,
    RefinarTextoBody,
    TextoRefinadoDTO,
)
from praxis.application.use_cases.asistir_redaccion_proyecto import (
    GenerarArticuladoConLLM,
    GenerarFundamentosConLLM,
    RefinarArticuloConLLM,
)
from praxis.domain import EstadoProyecto, ProyectoEnRedaccion
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyPerfilOpositorRepository,
    SqlAlchemyProyectoRedaccionRepository,
)

router = APIRouter(prefix="/proyectos-redaccion", tags=["proyectos-redaccion"])


def _to_dto(p: ProyectoEnRedaccion) -> ProyectoRedaccionDTO:
    assert p.id is not None
    return ProyectoRedaccionDTO(
        id=p.id,
        despacho_id=p.despacho_id,
        tipo=p.tipo,
        titulo=p.titulo,
        sumario=p.sumario,
        articulado=list(p.articulado),
        fundamentos=p.fundamentos,
        cofirmantes_sugeridos=list(p.cofirmantes_sugeridos),
        estado=p.estado,
        autor_legislador=p.autor_legislador,
        creado_en=p.creado_en,
        actualizado_en=p.actualizado_en,
        modelo_asistente=p.modelo_asistente,
        prompt_version=p.prompt_version,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProyectoRedaccionDTO])
async def listar_proyectos(
    ctx: CurrentContext, session: SessionDep,
) -> list[ProyectoRedaccionDTO]:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    proyectos = await repo.listar_por_despacho(ctx.despacho.id)
    return [_to_dto(p) for p in proyectos]


@router.post(
    "",
    response_model=ProyectoRedaccionDTO,
    status_code=status.HTTP_201_CREATED,
)
async def crear_proyecto(
    body: CrearProyectoBody,
    ctx: CurrentContext,
    session: SessionDep,
) -> ProyectoRedaccionDTO:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    proyecto = ProyectoEnRedaccion(
        despacho_id=ctx.despacho.id,
        tipo=body.tipo,
        titulo=body.titulo,
        sumario=body.sumario,
        autor_legislador=body.autor_legislador,
    )
    nuevo = await repo.crear(proyecto)
    await session.commit()
    return _to_dto(nuevo)


@router.get("/{proyecto_id}", response_model=ProyectoRedaccionDTO)
async def get_proyecto(
    proyecto_id: UUID, ctx: CurrentContext, session: SessionDep,
) -> ProyectoRedaccionDTO:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    p = await repo.buscar_por_id(proyecto_id)
    if p is None or p.despacho_id != ctx.despacho.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _to_dto(p)


@router.patch("/{proyecto_id}", response_model=ProyectoRedaccionDTO)
async def actualizar_proyecto(
    proyecto_id: UUID,
    body: ActualizarProyectoBody,
    ctx: CurrentContext,
    session: SessionDep,
) -> ProyectoRedaccionDTO:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    p = await repo.buscar_por_id(proyecto_id)
    if p is None or p.despacho_id != ctx.despacho.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if body.tipo is not None:
        p.tipo = body.tipo
    if body.titulo is not None:
        p.titulo = body.titulo
    if body.sumario is not None:
        p.sumario = body.sumario
    if body.articulado is not None:
        p.articulado = body.articulado
    if body.fundamentos is not None:
        p.fundamentos = body.fundamentos
    if body.cofirmantes_sugeridos is not None:
        p.cofirmantes_sugeridos = body.cofirmantes_sugeridos
    if body.estado is not None:
        p.estado = body.estado
    if body.autor_legislador is not None:
        p.autor_legislador = body.autor_legislador
    actualizado = await repo.actualizar(p)
    await session.commit()
    return _to_dto(actualizado)


@router.delete("/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_proyecto(
    proyecto_id: UUID, ctx: CurrentContext, session: SessionDep,
) -> None:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    p = await repo.buscar_por_id(proyecto_id)
    if p is None or p.despacho_id != ctx.despacho.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await repo.eliminar(proyecto_id)
    await session.commit()


# ---------------------------------------------------------------------------
# Asistentes LLM
# ---------------------------------------------------------------------------


@router.post(
    "/{proyecto_id}/asistir/articulado",
    response_model=ProyectoRedaccionDTO,
    summary="Genera articulado con LLM y lo persiste en el proyecto.",
)
async def asistir_articulado(
    proyecto_id: UUID,
    body: GenerarArticuladoBody,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> ProyectoRedaccionDTO:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    p = await repo.buscar_por_id(proyecto_id)
    if p is None or p.despacho_id != ctx.despacho.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    uc = GenerarArticuladoConLLM(
        perfiles=SqlAlchemyPerfilOpositorRepository(session), llm=llm,
    )
    tema = body.tema_override or p.sumario
    result = await uc.ejecutar(
        despacho_id=ctx.despacho.id, tipo=p.tipo, tema=tema,
    )
    p.articulado = result.articulado
    p.modelo_asistente = result.modelo
    actualizado = await repo.actualizar(p)
    await session.commit()
    return _to_dto(actualizado)


@router.post(
    "/{proyecto_id}/asistir/fundamentos",
    response_model=ProyectoRedaccionDTO,
    summary="Genera fundamentos con LLM y los persiste en el proyecto.",
)
async def asistir_fundamentos(
    proyecto_id: UUID,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> ProyectoRedaccionDTO:
    repo = SqlAlchemyProyectoRedaccionRepository(session)
    p = await repo.buscar_por_id(proyecto_id)
    if p is None or p.despacho_id != ctx.despacho.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not p.articulado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generá primero el articulado.",
        )
    uc = GenerarFundamentosConLLM(
        perfiles=SqlAlchemyPerfilOpositorRepository(session), llm=llm,
    )
    result = await uc.ejecutar(
        despacho_id=ctx.despacho.id,
        tipo=p.tipo,
        tema=p.sumario,
        articulado=p.articulado,
    )
    p.fundamentos = result.fundamentos
    p.modelo_asistente = result.modelo
    actualizado = await repo.actualizar(p)
    await session.commit()
    return _to_dto(actualizado)


@router.post(
    "/asistir/refinar",
    response_model=TextoRefinadoDTO,
    summary="Refina un texto (artículo o fragmento) sin persistir.",
)
async def asistir_refinar(
    body: RefinarTextoBody,
    ctx: CurrentContext,
    llm: LlmProviderDep,
) -> TextoRefinadoDTO:
    uc = RefinarArticuloConLLM(llm=llm)
    texto, modelo = await uc.ejecutar(
        texto_actual=body.texto, instruccion=body.instruccion,
    )
    return TextoRefinadoDTO(texto_refinado=texto, modelo=modelo)
