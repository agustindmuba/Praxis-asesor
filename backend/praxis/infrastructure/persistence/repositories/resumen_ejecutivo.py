"""Repositorio de ResumenEjecutivo sobre SQLAlchemy async.

Una fila por expediente (UNIQUE en `expediente_id`). Inmutable: regenerar
es delete + insert, no update.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import ResumenEjecutivoRepository
from praxis.domain import ResumenEjecutivo
from praxis.infrastructure.persistence.mappers import (
    from_resumen_ejecutivo,
    to_resumen_ejecutivo,
)
from praxis.infrastructure.persistence.models import ResumenEjecutivoOrm


class SqlAlchemyResumenEjecutivoRepository(ResumenEjecutivoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_expediente(self, expediente_id: UUID) -> ResumenEjecutivo | None:
        stmt = select(ResumenEjecutivoOrm).where(ResumenEjecutivoOrm.expediente_id == expediente_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_resumen_ejecutivo(orm) if orm is not None else None

    async def crear(self, resumen: ResumenEjecutivo) -> ResumenEjecutivo:
        orm = from_resumen_ejecutivo(resumen)
        self._session.add(orm)
        await self._session.flush()
        # Refresh para tomar `generado_en` con el server_default.
        await self._session.refresh(orm)
        return to_resumen_ejecutivo(orm)

    async def eliminar(self, expediente_id: UUID) -> bool:
        stmt = delete(ResumenEjecutivoOrm).where(ResumenEjecutivoOrm.expediente_id == expediente_id)
        result = await self._session.execute(stmt)
        # rowcount existe en CursorResult.
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]
