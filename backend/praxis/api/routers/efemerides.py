"""Router `/efemerides` — endpoints REST de efemérides (feat-53.4).

Endpoints:

- `GET /efemerides` — lista todas, opcionalmente filtradas por tipo y
  relevancia.
- `GET /efemerides/proximas?dias=30&relevancia_minima=media` — las que
  caen en los próximos N días desde HOY. La fecha base es la del server
  (ART). Útil para dashboard.
- `GET /efemerides/{id}` — detalle.
- `POST /efemerides/{id}/generar-declaracion` — genera un proyecto de
  declaración usando el LLM configurado (con FakeLlmProvider si no hay
  Anthropic key). Tenant-scoped: el perfil del despacho del request
  influye en el tono.

Las efemérides son **públicas** (no tenant-scoped). La declaración
sí: usa el perfil opositor del despacho del request.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.application.use_cases.generar_declaracion_desde_efemeride import (
    EfemerideNoEncontrada,
    GenerarDeclaracionDesdeEfemeride,
)
from praxis.domain import (
    EFEMERIDE_TIPO_LABELS,
    Efemeride,
    RelevanciaEfemeride,
    TipoEfemeride,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyEfemerideRepository,
    SqlAlchemyPerfilOpositorRepository,
)

router = APIRouter(prefix="/efemerides", tags=["efemerides"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EfemerideDTO(BaseModel):
    id: UUID
    mes: int
    dia: int
    fecha_corta: str
    titulo: str
    tipo: str
    tipo_label: str
    relevancia: str
    descripcion: str | None
    fuente: str | None
    areas_tematicas: list[str]
    anio_unico: int | None
    es_recurrente: bool

    @classmethod
    def from_domain(cls, ef: Efemeride) -> EfemerideDTO:
        return cls(
            id=ef.id,
            mes=ef.mes,
            dia=ef.dia,
            fecha_corta=ef.fecha_corta,
            titulo=ef.titulo,
            tipo=ef.tipo.value,
            tipo_label=EFEMERIDE_TIPO_LABELS[ef.tipo],
            relevancia=ef.relevancia.value,
            descripcion=ef.descripcion,
            fuente=ef.fuente,
            areas_tematicas=ef.areas_tematicas,
            anio_unico=ef.anio_unico,
            es_recurrente=ef.es_recurrente,
        )


class GenerarDeclaracionResponse(BaseModel):
    efemeride: EfemerideDTO
    tema_generado: str = Field(
        ..., description="Texto que se le pasó al LLM como contexto."
    )
    articulado: list[str]
    fundamentos: str
    modelo: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[EfemerideDTO])
async def listar_efemerides(
    session: SessionDep,
    tipo: Annotated[str | None, Query(description="Filtro por tipo")] = None,
    relevancia: Annotated[str | None, Query(description="Filtro por relevancia")] = None,
) -> list[EfemerideDTO]:
    if tipo is not None and tipo not in {t.value for t in TipoEfemeride}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo inválido: {tipo}",
        )
    if relevancia is not None and relevancia not in {
        r.value for r in RelevanciaEfemeride
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Relevancia inválida: {relevancia}",
        )

    repo = SqlAlchemyEfemerideRepository(session)
    efemerides = await repo.listar_todas(tipo=tipo, relevancia=relevancia)
    return [EfemerideDTO.from_domain(ef) for ef in efemerides]


@router.get("/proximas", response_model=list[EfemerideDTO])
async def proximas_efemerides(
    session: SessionDep,
    dias: Annotated[int, Query(ge=1, le=180)] = 30,
    relevancia_minima: Annotated[str, Query()] = "media",
) -> list[EfemerideDTO]:
    if relevancia_minima not in {"alta", "media", "baja"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"relevancia_minima inválida: {relevancia_minima}",
        )

    hoy = date.today()
    repo = SqlAlchemyEfemerideRepository(session)
    efemerides = await repo.proximas(
        desde_mes=hoy.month,
        desde_dia=hoy.day,
        dias=dias,
        relevancia_minima=relevancia_minima,
    )
    return [EfemerideDTO.from_domain(ef) for ef in efemerides]


@router.get("/{efemeride_id}", response_model=EfemerideDTO)
async def detalle_efemeride(
    efemeride_id: UUID,
    session: SessionDep,
) -> EfemerideDTO:
    repo = SqlAlchemyEfemerideRepository(session)
    ef = await repo.buscar_por_id(efemeride_id)
    if ef is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Efeméride no encontrada",
        )
    return EfemerideDTO.from_domain(ef)


@router.post(
    "/{efemeride_id}/generar-declaracion",
    response_model=GenerarDeclaracionResponse,
)
async def generar_declaracion(
    efemeride_id: UUID,
    session: SessionDep,
    llm: LlmProviderDep,
    ctx: CurrentContext,
) -> GenerarDeclaracionResponse:
    """Genera un proyecto de declaración a partir de la efeméride.

    Usa el `LlmProvider` configurado: AnthropicLlmProvider si hay API
    key, FakeLlmProvider (con plantillas keyword-based) si no.
    El perfil opositor del despacho del request influye en el tono.
    """
    efemerides = SqlAlchemyEfemerideRepository(session)
    perfiles = SqlAlchemyPerfilOpositorRepository(session)
    uc = GenerarDeclaracionDesdeEfemeride(
        efemerides=efemerides, perfiles=perfiles, llm=llm,
    )
    try:
        resultado = await uc.ejecutar(
            efemeride_id=efemeride_id,
            despacho_id=ctx.despacho_id,
        )
    except EfemerideNoEncontrada as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return GenerarDeclaracionResponse(
        efemeride=EfemerideDTO.from_domain(resultado.efemeride),
        tema_generado=resultado.tema_generado,
        articulado=resultado.articulado,
        fundamentos=resultado.fundamentos,
        modelo=resultado.modelo,
    )
