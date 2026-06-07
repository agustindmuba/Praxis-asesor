"""Router REST /perfil-opositor (feat-42.1).

- GET /perfil-opositor : trae el perfil del despacho activo.
- POST /perfil-opositor/inferir : corre el bot sobre la huella + persiste.
- PATCH /perfil-opositor : edición manual desde la UI.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.perfil_opositor import (
    ActualizarPerfilBody,
    DistribucionAccionDTO,
    FiguraReferidaDTO,
    InferirPerfilBody,
    InsightsFeedbackDTO,
    PerfilOpositorDTO,
    SugerenciaInsightDTO,
)
from praxis.application.use_cases.calcular_insights_feedback import (
    CalcularInsightsFeedback,
)
from praxis.domain import PerfilOpositorDespacho


def _to_dto(p: PerfilOpositorDespacho) -> PerfilOpositorDTO:
    """Construye el DTO Pydantic desde la entidad de dominio.

    No usamos model_validate(from_attributes=True) porque las listas
    de FiguraReferida (dataclass) no se auto-convierten a
    FiguraReferidaDTO (BaseModel) — error de schema_type."""
    return PerfilOpositorDTO(
        despacho_id=p.despacho_id,
        bandera_principal=p.bandera_principal,
        banderas_secundarias=list(p.banderas_secundarias),
        temas_de_cuidado=list(p.temas_de_cuidado),
        tono_comunicacional=p.tono_comunicacional,
        adversarios=[FiguraReferidaDTO(nombre=a.nombre, razon=a.razon) for a in p.adversarios],
        aliados=[FiguraReferidaDTO(nombre=a.nombre, razon=a.razon) for a in p.aliados],
        linea_de_bloque=p.linea_de_bloque,
        justificacion_evidencia=p.justificacion_evidencia,
        advertencias=list(p.advertencias),
        confianza_global=p.confianza_global,
        inferido_en=p.inferido_en,
        editado_en=p.editado_en,
        modelo_inferencia=p.modelo_inferencia,
        prompt_version=p.prompt_version,
    )
from praxis.application.use_cases.inferir_perfil_opositor import (
    InferirPerfilOpositor,
)
from praxis.domain import FiguraReferida
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyPerfilOpositorRepository,
)

router = APIRouter(prefix="/perfil-opositor", tags=["perfil-opositor"])


@router.get(
    "",
    response_model=PerfilOpositorDTO | None,
    summary="Trae el perfil opositor del despacho activo (puede ser None).",
)
async def get_perfil_opositor(
    ctx: CurrentContext, session: SessionDep,
) -> PerfilOpositorDTO | None:
    repo = SqlAlchemyPerfilOpositorRepository(session)
    perfil = await repo.buscar_por_despacho(ctx.despacho.id)
    if perfil is None:
        return None
    return _to_dto(perfil)


@router.post(
    "/inferir",
    response_model=PerfilOpositorDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Corre el bot de perfilamiento y persiste el borrador.",
)
async def inferir_perfil(
    body: InferirPerfilBody,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> PerfilOpositorDTO:
    repo = SqlAlchemyPerfilOpositorRepository(session)
    uc = InferirPerfilOpositor(session=session, perfiles=repo, llm=llm)
    try:
        perfil = await uc.ejecutar(
            despacho_id=ctx.despacho.id,
            nombre_legislador=body.nombre_legislador,
            max_votaciones=body.max_votaciones,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        ) from e
    await session.commit()
    return _to_dto(perfil)


@router.patch(
    "",
    response_model=PerfilOpositorDTO,
    summary="Actualiza los campos editados manualmente desde la UI.",
)
async def actualizar_perfil(
    body: ActualizarPerfilBody,
    ctx: CurrentContext,
    session: SessionDep,
) -> PerfilOpositorDTO:
    repo = SqlAlchemyPerfilOpositorRepository(session)
    actual = await repo.buscar_por_despacho(ctx.despacho.id)
    if actual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay perfil que actualizar. Inferí uno primero.",
        )

    # Aplicar deltas
    if body.bandera_principal is not None:
        actual.bandera_principal = body.bandera_principal
    if body.banderas_secundarias is not None:
        actual.banderas_secundarias = body.banderas_secundarias
    if body.temas_de_cuidado is not None:
        actual.temas_de_cuidado = body.temas_de_cuidado
    if body.tono_comunicacional is not None:
        actual.tono_comunicacional = body.tono_comunicacional
    if body.adversarios is not None:
        actual.adversarios = [
            FiguraReferida(nombre=a.nombre, razon=a.razon) for a in body.adversarios
        ]
    if body.aliados is not None:
        actual.aliados = [
            FiguraReferida(nombre=a.nombre, razon=a.razon) for a in body.aliados
        ]
    if body.linea_de_bloque is not None:
        actual.linea_de_bloque = body.linea_de_bloque

    actual.editado_en = datetime.now(UTC)
    nuevo = await repo.upsert(actual)
    await session.commit()
    return _to_dto(nuevo)


# ---------------------------------------------------------------------------
# Insights del feedback (feat-43.3)
# ---------------------------------------------------------------------------


@router.get(
    "/insights-feedback",
    response_model=InsightsFeedbackDTO,
    summary=(
        "Insights del feedback del asesor en accionables (últimos 28 días): "
        "distribución por tipo de acción + sugerencias automáticas para el perfil."
    ),
)
async def get_insights_feedback(
    ctx: CurrentContext,
    session: SessionDep,
) -> InsightsFeedbackDTO:
    uc = CalcularInsightsFeedback(session=session)
    r = await uc.ejecutar(despacho_id=ctx.despacho.id)
    return InsightsFeedbackDTO(
        ventana_dias=r.ventana_dias,
        total_accionables=r.total_accionables,
        total_con_feedback=r.total_con_feedback,
        distribucion=[
            DistribucionAccionDTO(
                accion=d.accion,
                total=d.total,
                pendientes=d.pendientes,
                hechos=d.hechos,
                ignorados=d.ignorados,
                adaptados=d.adaptados,
                pct_ignorado=d.pct_ignorado,
                pct_hecho=d.pct_hecho,
                pct_adaptado=d.pct_adaptado,
            )
            for d in r.distribucion
        ],
        sugerencias=[
            SugerenciaInsightDTO(
                tipo=s.tipo,
                accion_objetivo=s.accion_objetivo,
                mensaje=s.mensaje,
                severidad=s.severidad,
            )
            for s in r.sugerencias
        ],
    )
