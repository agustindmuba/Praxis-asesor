"""Repositorio de SeguimientoExpediente.

Tenant-scoped: TODA query filtra por despacho_id explícito (ADR 0003 §4).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import SeguimientoExpedienteRepository
from praxis.domain import SeguimientoExpediente
from praxis.infrastructure.persistence.mappers import from_seguimiento, to_seguimiento
from praxis.infrastructure.persistence.models import SeguimientoExpedienteOrm


class SqlAlchemySeguimientoExpedienteRepository(SeguimientoExpedienteRepository):
    """Implementación de seguimiento sobre SQLAlchemy async.

    Filter explícito de `despacho_id` en cada query (ADR 0003 §4).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, seguimiento: SeguimientoExpediente) -> SeguimientoExpediente:
        orm = from_seguimiento(seguimiento)
        self._session.add(orm)
        await self._session.flush()
        return to_seguimiento(orm)

    async def buscar(
        self,
        *,
        despacho_id: UUID,
        expediente_id: UUID,
    ) -> SeguimientoExpediente | None:
        """Lookup por (despacho_id, expediente_id). Tenant-isolated por design."""
        stmt = select(SeguimientoExpedienteOrm).where(
            SeguimientoExpedienteOrm.despacho_id == despacho_id,
            SeguimientoExpedienteOrm.expediente_id == expediente_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_seguimiento(orm) if orm is not None else None

    async def buscar_por_id(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
    ) -> SeguimientoExpediente | None:
        """Lookup por UUID + filter explícito de despacho_id.

        El despacho_id no es redundante: protege contra leak entre tenants
        si alguien pasa un seguimiento_id que no le pertenece.
        """
        stmt = select(SeguimientoExpedienteOrm).where(
            SeguimientoExpedienteOrm.id == seguimiento_id,
            SeguimientoExpedienteOrm.despacho_id == despacho_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_seguimiento(orm) if orm is not None else None

    async def listar_por_despacho(
        self,
        despacho_id: UUID,
        *,
        incluir_archivados: bool = False,
    ) -> list[SeguimientoExpediente]:
        stmt = select(SeguimientoExpedienteOrm).where(
            SeguimientoExpedienteOrm.despacho_id == despacho_id,
        )
        if not incluir_archivados:
            stmt = stmt.where(SeguimientoExpedienteOrm.archivado.is_(False))
        result = await self._session.execute(stmt)
        return [to_seguimiento(orm) for orm in result.scalars()]

    async def archivar(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
    ) -> bool:
        """Marca archivado=True. Devuelve True si afectó una fila, False si no."""
        stmt = (
            update(SeguimientoExpedienteOrm)
            .where(
                SeguimientoExpedienteOrm.id == seguimiento_id,
                SeguimientoExpedienteOrm.despacho_id == despacho_id,
            )
            .values(archivado=True)
        )
        result = await self._session.execute(stmt)
        # rowcount existe en CursorResult (subclase de Result), no en la base.
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def asignar_responsable(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
        responsable_id: UUID | None,
    ) -> bool:
        """Asigna o desasigna (None) el responsable. Tenant-isolated."""
        stmt = (
            update(SeguimientoExpedienteOrm)
            .where(
                SeguimientoExpedienteOrm.id == seguimiento_id,
                SeguimientoExpedienteOrm.despacho_id == despacho_id,
            )
            .values(responsable_id=responsable_id)
        )
        result = await self._session.execute(stmt)
        # rowcount existe en CursorResult (subclase de Result), no en la base.
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]
