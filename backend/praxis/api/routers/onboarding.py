"""Router /onboarding (feat-44).

- POST /onboarding/configurar-despacho : guarda legislador titular +
  foto + cámara y opcionalmente dispara InferirPerfilOpositor.
- GET  /onboarding/estado : check de pasos completados (legislador,
  perfil, destinatarios, primer accionable).

Tenant-scoped: opera siempre contra `ctx.despacho`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import select, text

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.api.schemas.onboarding import (
    ConfigurarDespachoBody,
    ConfigurarDespachoResponse,
    EstadoOnboardingDTO,
)
from praxis.application.use_cases.inferir_perfil_opositor import (
    InferirPerfilOpositor,
)
from praxis.infrastructure.persistence.models import DespachoOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyPerfilOpositorRepository,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post(
    "/configurar-despacho",
    response_model=ConfigurarDespachoResponse,
    summary=(
        "Persiste legislador titular + foto. Opcionalmente dispara el "
        "bot que infiere el perfil opositor desde la huella parlamentaria."
    ),
)
async def configurar_despacho(
    body: ConfigurarDespachoBody,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> ConfigurarDespachoResponse:
    # 1) Persistir en despacho
    stmt = select(DespachoOrm).where(DespachoOrm.id == ctx.despacho.id)
    despacho_orm = (await session.execute(stmt)).scalar_one()
    despacho_orm.legislador_titular_slug = body.legislador_titular_slug.strip()
    if body.foto_url is not None:
        despacho_orm.legislador_foto_url = body.foto_url.strip() or None
    await session.flush()

    perfil_id: str | None = None
    perfil_inferido = False
    error_inferencia: str | None = None

    # 2) (opcional) Inferir perfil opositor
    if body.inferir_perfil:
        try:
            uc = InferirPerfilOpositor(
                session=session,
                perfiles=SqlAlchemyPerfilOpositorRepository(session),
                llm=llm,
            )
            perfil = await uc.ejecutar(
                despacho_id=ctx.despacho.id,
                nombre_legislador=body.legislador_titular_slug,
            )
            perfil_id = str(perfil.despacho_id) if perfil else None
            perfil_inferido = perfil_id is not None
        except ValueError as exc:
            # Ej: "No encontré actividad parlamentaria para X"
            error_inferencia = str(exc)
            log.warning(
                "onboarding: inferencia falló para %s: %s",
                body.legislador_titular_slug, exc,
            )
        except Exception as exc:    # noqa: BLE001
            error_inferencia = (
                "Inferencia falló por error técnico. Podés intentarlo "
                "de nuevo desde /configuracion/perfil-opositor."
            )
            log.exception(
                "onboarding: error LLM inferencia perfil opositor",
                extra={"despacho_id": str(ctx.despacho.id)},
            )

    await session.commit()
    return ConfigurarDespachoResponse(
        despacho_id=str(ctx.despacho.id),
        legislador_titular_slug=body.legislador_titular_slug,
        foto_url=despacho_orm.legislador_foto_url,
        perfil_inferido=perfil_inferido,
        perfil_id=perfil_id,
        mensaje=(
            "Despacho configurado." +
            (" Perfil opositor inferido." if perfil_inferido
             else " El perfil se puede inferir luego desde "
                  "/configuracion/perfil-opositor.")
        ),
        error_inferencia=error_inferencia,
    )


@router.get(
    "/estado",
    response_model=EstadoOnboardingDTO,
    summary="Devuelve qué pasos del onboarding ya están hechos.",
)
async def estado_onboarding(
    ctx: CurrentContext, session: SessionDep,
) -> EstadoOnboardingDTO:
    despacho_id = ctx.despacho.id

    paso_1 = bool(ctx.despacho.legislador_titular_slug)

    r = await session.execute(text("""
        SELECT COUNT(*) FROM perfil_opositor_despacho
        WHERE despacho_id = :d
    """), {"d": despacho_id})
    paso_2 = int(r.scalar() or 0) > 0

    r = await session.execute(text("""
        SELECT COUNT(*) FROM destinatario
        WHERE despacho_id = :d AND activo
    """), {"d": despacho_id})
    paso_3 = int(r.scalar() or 0) > 0

    r = await session.execute(text("""
        SELECT COUNT(*) FROM accionable_evento
        WHERE despacho_id = :d
    """), {"d": despacho_id})
    paso_4 = int(r.scalar() or 0) > 0

    return EstadoOnboardingDTO(
        despacho_id=str(despacho_id),
        paso_1_legislador_cargado=paso_1,
        paso_2_perfil_opositor_cargado=paso_2,
        paso_3_destinatarios_cargados=paso_3,
        paso_4_primer_accionable=paso_4,
        todo_listo=paso_1 and paso_2,    # mínimo viable
    )
