"""Repositorio de MembresiaDespacho."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import MembresiaDespachoRepository
from praxis.domain import MembresiaDespacho
from praxis.infrastructure.persistence.mappers import (
    from_membresia_despacho,
    to_membresia_despacho,
)
from praxis.infrastructure.persistence.models import MembresiaDespachoOrm


class SqlAlchemyMembresiaDespachoRepository(MembresiaDespachoRepository):
    """Persistencia de pertenencia Usuario ↔ Despacho.

    Filter explícito de `despacho_id` en cada método tenant-scoped
    (ver ADR 0003 §4).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def agregar(self, membresia: MembresiaDespacho) -> MembresiaDespacho:
        orm = from_membresia_despacho(membresia)
        self._session.add(orm)
        await self._session.flush()
        return to_membresia_despacho(orm)

    async def buscar(
        self,
        *,
        usuario_id: UUID,
        despacho_id: UUID,
    ) -> MembresiaDespacho | None:
        orm = await self._session.get(MembresiaDespachoOrm, (usuario_id, despacho_id))
        return to_membresia_despacho(orm) if orm is not None else None

    async def listar_por_despacho(self, despacho_id: UUID) -> list[MembresiaDespacho]:
        """Tenant-scoped: filter explícito por despacho_id."""
        stmt = select(MembresiaDespachoOrm).where(MembresiaDespachoOrm.despacho_id == despacho_id)
        result = await self._session.execute(stmt)
        return [to_membresia_despacho(orm) for orm in result.scalars()]

    async def listar_por_usuario(self, usuario_id: UUID) -> list[MembresiaDespacho]:
        """Cross-tenant desde la perspectiva del usuario: devuelve sus
        membresías en todos los despachos a los que pertenece."""
        stmt = select(MembresiaDespachoOrm).where(MembresiaDespachoOrm.usuario_id == usuario_id)
        result = await self._session.execute(stmt)
        return [to_membresia_despacho(orm) for orm in result.scalars()]
