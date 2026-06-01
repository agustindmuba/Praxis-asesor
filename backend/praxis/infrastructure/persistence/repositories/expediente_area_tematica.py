"""Repositorio de ExpedienteAreaTematica sobre SQLAlchemy async.

Una fila por expediente (UNIQUE en `expediente_id`). Para reclasificar
se borra primero — la versión del prompt cambia, el cache viejo deja
de ser válido.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import ExpedienteAreaTematicaRepository
from praxis.domain import AreaTematica, ExpedienteAreaTematica
from praxis.infrastructure.persistence.mappers import (
    from_expediente_area_tematica,
    to_expediente_area_tematica,
)
from praxis.infrastructure.persistence.models import (
    ExpedienteAreaTematicaOrm,
)


class SqlAlchemyExpedienteAreaTematicaRepository(
    ExpedienteAreaTematicaRepository
):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_expediente(
        self, expediente_id: UUID,
    ) -> ExpedienteAreaTematica | None:
        stmt = select(ExpedienteAreaTematicaOrm).where(
            ExpedienteAreaTematicaOrm.expediente_id == expediente_id
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_expediente_area_tematica(orm) if orm is not None else None

    async def crear(
        self, cache: ExpedienteAreaTematica,
    ) -> ExpedienteAreaTematica:
        orm = from_expediente_area_tematica(cache)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return to_expediente_area_tematica(orm)

    async def eliminar(self, expediente_id: UUID) -> bool:
        stmt = delete(ExpedienteAreaTematicaOrm).where(
            ExpedienteAreaTematicaOrm.expediente_id == expediente_id
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    async def listar_por_area(
        self,
        area: AreaTematica,
        *,
        limit: int = 100,
    ) -> list[ExpedienteAreaTematica]:
        stmt = (
            select(ExpedienteAreaTematicaOrm)
            .where(ExpedienteAreaTematicaOrm.area == area.value)
            .order_by(ExpedienteAreaTematicaOrm.generado_en.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [to_expediente_area_tematica(orm) for orm in result.scalars()]
