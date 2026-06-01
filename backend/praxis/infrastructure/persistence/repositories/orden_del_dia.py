"""Repositorio de OrdenDelDia sobre SQLAlchemy async."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import OrdenDelDiaRepository
from praxis.domain import OrdenDelDia
from praxis.infrastructure.persistence.mappers import (
    from_orden_del_dia,
    to_orden_del_dia,
)
from praxis.infrastructure.persistence.models import OrdenDelDiaOrm


class SqlAlchemyOrdenDelDiaRepository(OrdenDelDiaRepository):
    """Persistencia del OD. Acepta `despacho_id` en `crear` porque la
    asignación a un despacho vive en la capa de persistencia (el dominio
    no lo modela explícitamente — el OD del request siempre viene con
    el contexto del current_context).
    """

    def __init__(
        self, session: AsyncSession, *, despacho_id: UUID | None = None,
    ) -> None:
        self._session = session
        self._despacho_id = despacho_id

    async def crear(self, od: OrdenDelDia) -> OrdenDelDia:
        orm = from_orden_del_dia(od, despacho_id=self._despacho_id)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return to_orden_del_dia(orm)

    async def buscar_por_id(self, od_id: UUID) -> OrdenDelDia | None:
        stmt = select(OrdenDelDiaOrm).where(OrdenDelDiaOrm.id == od_id)
        if self._despacho_id is not None:
            # Tenant scoping: solo el despacho del request puede acceder.
            stmt = stmt.where(OrdenDelDiaOrm.despacho_id == self._despacho_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_orden_del_dia(orm) if orm is not None else None

    async def listar_por_despacho(
        self,
        despacho_id: UUID,
        *,
        limit: int = 20,
    ) -> list[OrdenDelDia]:
        stmt = (
            select(OrdenDelDiaOrm)
            .where(OrdenDelDiaOrm.despacho_id == despacho_id)
            .order_by(OrdenDelDiaOrm.fecha_sesion.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [to_orden_del_dia(orm) for orm in result.scalars()]
