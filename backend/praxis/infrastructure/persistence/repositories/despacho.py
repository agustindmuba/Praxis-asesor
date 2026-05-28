"""Repositorio de Despacho sobre SQLAlchemy async."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import DespachoRepository
from praxis.domain.despacho import Despacho
from praxis.infrastructure.persistence.mappers import from_despacho, to_despacho
from praxis.infrastructure.persistence.models import DespachoOrm


class SqlAlchemyDespachoRepository(DespachoRepository):
    """Implementación de `DespachoRepository` sobre SQLAlchemy 2.0 async.

    Se construye con una `AsyncSession`. Por convención, la sesión la maneja
    el caller (típicamente vía dependency-injection en FastAPI). El repo
    no abre transacciones; quien lo invoca decide commit/rollback.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, despacho: Despacho) -> Despacho:
        orm = from_despacho(despacho)
        self._session.add(orm)
        await self._session.flush()  # asegura que id y timestamps estén poblados
        return to_despacho(orm)

    async def buscar_por_id(self, despacho_id: UUID) -> Despacho | None:
        orm = await self._session.get(DespachoOrm, despacho_id)
        return to_despacho(orm) if orm is not None else None

    async def listar(self) -> list[Despacho]:
        result = await self._session.execute(select(DespachoOrm))
        return [to_despacho(orm) for orm in result.scalars()]
