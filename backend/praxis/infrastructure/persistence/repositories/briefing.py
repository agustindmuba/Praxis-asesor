"""Repositorio de Briefing sobre SQLAlchemy async.

UNIQUE compuesto (despacho_id, orden_del_dia_id). El briefing es
inmutable: regenerar = delete + insert.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import BriefingRepository
from praxis.domain import Briefing
from praxis.infrastructure.persistence.mappers import (
    from_briefing,
    to_briefing,
)
from praxis.infrastructure.persistence.models import BriefingOrm


class SqlAlchemyBriefingRepository(BriefingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_despacho_y_od(
        self,
        *,
        despacho_id: UUID,
        orden_del_dia_id: UUID,
    ) -> Briefing | None:
        stmt = select(BriefingOrm).where(
            BriefingOrm.despacho_id == despacho_id,
            BriefingOrm.orden_del_dia_id == orden_del_dia_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_briefing(orm) if orm is not None else None

    async def crear(self, briefing: Briefing) -> Briefing:
        orm = from_briefing(briefing)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return to_briefing(orm)

    async def eliminar(
        self,
        *,
        despacho_id: UUID,
        orden_del_dia_id: UUID,
    ) -> bool:
        stmt = delete(BriefingOrm).where(
            BriefingOrm.despacho_id == despacho_id,
            BriefingOrm.orden_del_dia_id == orden_del_dia_id,
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]
