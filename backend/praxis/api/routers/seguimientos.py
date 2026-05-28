"""Router /seguimientos — CRUD tenant-scoped del seguimiento de expedientes.

Todos los endpoints usan `ctx.despacho.id` (de `current_context`) como
tenant. NUNCA se debe permitir que el cliente pase el `despacho_id` por
body o query — eso abriría la puerta a cross-tenant access.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas import (
    ActualizarSeguimientoBody,
    CrearSeguimientoBody,
    SeguimientoDTO,
)
from praxis.domain import SeguimientoExpediente
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyExpedienteRepository,
    SqlAlchemySeguimientoExpedienteRepository,
)

router = APIRouter(prefix="/seguimientos", tags=["seguimientos"])


@router.post(
    "",
    summary="Crear un seguimiento del despacho activo sobre un expediente",
    status_code=status.HTTP_201_CREATED,
    response_model=SeguimientoDTO,
)
async def crear_seguimiento(
    body: CrearSeguimientoBody,
    session: SessionDep,
    ctx: CurrentContext,
) -> SeguimientoDTO:
    """Marca un expediente como de interés para el despacho activo.

    Errores:
    - 404 si el expediente no existe en el catálogo.
    - 409 si el despacho ya sigue ese expediente (UNIQUE).
    """
    # Validar que el expediente existe — sin esto la FK violaría con un 500.
    exp_repo = SqlAlchemyExpedienteRepository(session)
    expediente = await exp_repo.buscar_por_id(body.expediente_id)
    if expediente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expediente no encontrado",
        )

    seg_repo = SqlAlchemySeguimientoExpedienteRepository(session)
    nuevo = SeguimientoExpediente(
        id=uuid4(),
        despacho_id=ctx.despacho.id,
        expediente_id=body.expediente_id,
        prioridad=body.prioridad,
    )
    try:
        creado = await seg_repo.crear(nuevo)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El despacho ya sigue este expediente",
        ) from exc

    return SeguimientoDTO.model_validate(creado)


@router.patch(
    "/{seguimiento_id}",
    summary="Actualizar prioridad/responsable/archivar de un seguimiento",
    response_model=SeguimientoDTO,
)
async def actualizar_seguimiento(
    seguimiento_id: UUID,
    body: ActualizarSeguimientoBody,
    session: SessionDep,
    ctx: CurrentContext,
) -> SeguimientoDTO:
    """Aplica las modificaciones indicadas en el body.

    Tenant isolation:
    - Si el seguimiento_id no pertenece al despacho activo, devolvemos 404
      (no leakemos existencia con un 403 distinguible).

    Body:
    - `responsable_id` (UUID | null): asigna o desasigna.
    - `archivado` (bool): True archiva; False no-op (sin "desarchivar" todavía).
    """
    seg_repo = SqlAlchemySeguimientoExpedienteRepository(session)
    fields_set = body.model_fields_set

    # Operaciones idempotentes: aplicamos cada una con su método dedicado y
    # un guard de "row not found" → 404. Hacemos `buscar_por_id` al final
    # para devolver el estado actualizado completo.
    modificado = False

    if "responsable_id" in fields_set:
        ok = await seg_repo.asignar_responsable(
            despacho_id=ctx.despacho.id,
            seguimiento_id=seguimiento_id,
            responsable_id=body.responsable_id,
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Seguimiento no encontrado",
            )
        modificado = True

    if body.archivado is True:
        ok = await seg_repo.archivar(
            despacho_id=ctx.despacho.id,
            seguimiento_id=seguimiento_id,
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Seguimiento no encontrado",
            )
        modificado = True

    if not modificado:
        # Nada para hacer — devolvemos el estado actual sin cambios.
        # Igual chequeamos que exista bajo este despacho.
        actual = await seg_repo.buscar_por_id(
            despacho_id=ctx.despacho.id,
            seguimiento_id=seguimiento_id,
        )
        if actual is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Seguimiento no encontrado",
            )
        return SeguimientoDTO.model_validate(actual)

    await session.commit()

    actualizado = await seg_repo.buscar_por_id(
        despacho_id=ctx.despacho.id,
        seguimiento_id=seguimiento_id,
    )
    assert actualizado is not None, "Seguimiento desapareció después del update"
    return SeguimientoDTO.model_validate(actualizado)


@router.delete(
    "/{seguimiento_id}",
    summary="Archivar un seguimiento (soft delete)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archivar_seguimiento(
    seguimiento_id: UUID,
    session: SessionDep,
    ctx: CurrentContext,
) -> None:
    """Archiva el seguimiento. Equivalente a `PATCH {archivado: true}`.

    Mantenemos `DELETE` como interfaz semánticamente más limpia para clientes
    REST estándar, aunque por ahora no hay borrado físico (preservamos historial).
    """
    seg_repo = SqlAlchemySeguimientoExpedienteRepository(session)
    ok = await seg_repo.archivar(
        despacho_id=ctx.despacho.id,
        seguimiento_id=seguimiento_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seguimiento no encontrado",
        )
    await session.commit()
