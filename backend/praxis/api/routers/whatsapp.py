"""Routers `/destinatarios`, `/envios-whatsapp`, `/plantillas`
(feat-41.5). Todos tenant-scoped excepto `/plantillas` (catálogo
global de Meta).

Endpoints:

- GET /destinatarios : lista del despacho.
- POST /destinatarios : crea uno nuevo. Lanza al `opt_in_solicitud`
  como side-effect (en v1.1; en v1 solo persiste con activo=False y
  el opt-in lo hace el destinatario por la app de WhatsApp).
- PATCH /destinatarios/{id} : actualiza campos opcionales.
- DELETE /destinatarios/{id} : hard-delete tenant-scoped.
- GET /envios-whatsapp : histórico con filtros (tipo, desde, hasta).
- GET /plantillas : catálogo global de plantillas WhatsApp.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas.whatsapp import (
    ActualizarDestinatarioBody,
    CrearDestinatarioBody,
    DestinatarioDTO,
    EnvioWhatsAppDTO,
    PlantillaWhatsAppDTO,
)
from praxis.domain import Destinatario
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyPlantillaWhatsAppRepository,
)

router_destinatarios = APIRouter(
    prefix="/destinatarios", tags=["destinatarios"],
)
router_envios = APIRouter(
    prefix="/envios-whatsapp", tags=["envios-whatsapp"],
)
router_plantillas = APIRouter(
    prefix="/plantillas", tags=["plantillas"],
)


DEFAULT_VENTANA_ENVIOS_DIAS = 30


# ---------------------------------------------------------------------------
# Destinatarios
# ---------------------------------------------------------------------------


@router_destinatarios.get(
    "",
    response_model=list[DestinatarioDTO],
    summary="Lista destinatarios del despacho",
)
async def listar_destinatarios(
    session: SessionDep,
    ctx: CurrentContext,
    solo_activos: Annotated[bool, Query()] = False,
) -> list[DestinatarioDTO]:
    repo = SqlAlchemyDestinatarioRepository(session)
    items = await repo.listar_por_despacho(
        ctx.despacho.id, solo_activos=solo_activos,
    )
    return [
        DestinatarioDTO.model_validate(d, from_attributes=True) for d in items
    ]


@router_destinatarios.post(
    "",
    response_model=DestinatarioDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crea un destinatario nuevo",
)
async def crear_destinatario(
    body: CrearDestinatarioBody,
    session: SessionDep,
    ctx: CurrentContext,
) -> DestinatarioDTO:
    repo = SqlAlchemyDestinatarioRepository(session)
    try:
        telefono = body.telefono_normalizado()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Pre-check UNIQUE para devolver 409 limpio en lugar de IntegrityError.
    existente = await repo.buscar_por_telefono(
        despacho_id=ctx.despacho.id, telefono_e164=telefono,
    )
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay un destinatario con el teléfono {telefono}",
        )

    nuevo = await repo.crear(
        Destinatario(
            id=None,
            despacho_id=ctx.despacho.id,
            nombre=body.nombre,
            rol_interno=body.rol_interno,
            telefono_e164=telefono,
            recibe_briefing_diario=body.recibe_briefing_diario,
            recibe_alertas_menciones=body.recibe_alertas_menciones,
            recibe_alertas_otras=body.recibe_alertas_otras,
        ),
    )
    await session.commit()
    return DestinatarioDTO.model_validate(nuevo, from_attributes=True)


@router_destinatarios.patch(
    "/{destinatario_id}",
    response_model=DestinatarioDTO,
    summary="Actualiza campos del destinatario",
)
async def actualizar_destinatario(
    destinatario_id: UUID,
    body: ActualizarDestinatarioBody,
    session: SessionDep,
    ctx: CurrentContext,
) -> DestinatarioDTO:
    repo = SqlAlchemyDestinatarioRepository(session)
    actual = await repo.buscar_por_id(
        despacho_id=ctx.despacho.id, destinatario_id=destinatario_id,
    )
    if actual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destinatario no existe",
        )

    # Compone una versión nueva con overrides del body.
    nombre = body.nombre.strip() if body.nombre is not None else actual.nombre
    rol = body.rol_interno or actual.rol_interno
    telefono = actual.telefono_e164
    if body.telefono_e164 is not None:
        try:
            telefono = body.telefono_e164  # validado por el dominio
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    nueva = Destinatario(
        id=actual.id,
        despacho_id=actual.despacho_id,
        usuario_id=actual.usuario_id,
        nombre=nombre,
        rol_interno=rol,
        telefono_e164=telefono,
        recibe_briefing_diario=(
            body.recibe_briefing_diario
            if body.recibe_briefing_diario is not None
            else actual.recibe_briefing_diario
        ),
        recibe_alertas_menciones=(
            body.recibe_alertas_menciones
            if body.recibe_alertas_menciones is not None
            else actual.recibe_alertas_menciones
        ),
        recibe_alertas_otras=(
            body.recibe_alertas_otras
            if body.recibe_alertas_otras is not None
            else actual.recibe_alertas_otras
        ),
        opt_in_en=actual.opt_in_en,
        opt_out_en=actual.opt_out_en,
        activo=actual.activo,
    )
    actualizado = await repo.actualizar(nueva)
    await session.commit()
    return DestinatarioDTO.model_validate(actualizado, from_attributes=True)


@router_destinatarios.delete(
    "/{destinatario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Elimina un destinatario",
)
async def eliminar_destinatario(
    destinatario_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> None:
    repo = SqlAlchemyDestinatarioRepository(session)
    borrado = await repo.eliminar(
        despacho_id=ctx.despacho.id, destinatario_id=destinatario_id,
    )
    if not borrado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destinatario no existe",
        )
    await session.commit()


# ---------------------------------------------------------------------------
# Envíos WhatsApp
# ---------------------------------------------------------------------------


@router_envios.get(
    "",
    response_model=list[EnvioWhatsAppDTO],
    summary="Histórico tenant-scoped de envíos WhatsApp",
)
async def listar_envios(
    session: SessionDep,
    ctx: CurrentContext,
    tipo: Annotated[str | None, Query()] = None,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
) -> list[EnvioWhatsAppDTO]:
    repo = SqlAlchemyEnvioWhatsAppRepository(session)
    ahora = datetime.now(UTC)
    desde_efectivo = desde or ahora - timedelta(
        days=DEFAULT_VENTANA_ENVIOS_DIAS,
    )
    hasta_efectivo = hasta or ahora

    items = await repo.listar_por_despacho(
        ctx.despacho.id,
        desde=desde_efectivo,
        hasta=hasta_efectivo,
        tipo=tipo,
    )
    return [
        EnvioWhatsAppDTO.model_validate(e, from_attributes=True) for e in items
    ]


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------


@router_plantillas.get(
    "",
    response_model=list[PlantillaWhatsAppDTO],
    summary="Catálogo de plantillas WhatsApp",
)
async def listar_plantillas(
    session: SessionDep,
    solo_aprobadas: Annotated[bool, Query()] = False,
) -> list[PlantillaWhatsAppDTO]:
    """Catálogo global — no tenant-scoped (las plantillas son del
    catálogo Meta, mismas para todos los despachos)."""
    repo = SqlAlchemyPlantillaWhatsAppRepository(session)
    items = await repo.listar(solo_aprobadas=solo_aprobadas)
    return [
        PlantillaWhatsAppDTO.model_validate(p, from_attributes=True)
        for p in items
    ]
