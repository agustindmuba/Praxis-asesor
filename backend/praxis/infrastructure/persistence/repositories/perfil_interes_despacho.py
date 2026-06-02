"""Repositorio SQLAlchemy de `PerfilInteresDespacho`.

Una fila por despacho (PK = `despacho_id`). El upsert reemplaza la fila
entera; el caller setea `sembrado_at` o `editado_at` antes del
upsert según corresponda.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import PerfilInteresDespachoRepository
from praxis.domain import PerfilInteresDespacho
from praxis.infrastructure.persistence.mappers import (
    from_perfil_interes,
    to_perfil_interes,
)
from praxis.infrastructure.persistence.models import PerfilInteresDespachoOrm


class SqlAlchemyPerfilInteresDespachoRepository(PerfilInteresDespachoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilInteresDespacho | None:
        stmt = select(PerfilInteresDespachoOrm).where(
            PerfilInteresDespachoOrm.despacho_id == despacho_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_perfil_interes(orm) if orm is not None else None

    async def upsert(
        self, perfil: PerfilInteresDespacho,
    ) -> PerfilInteresDespacho:
        # SQLAlchemy 2.0 + SQLite + asyncpg no comparte una sintaxis de
        # UPSERT realmente portátil. Implementamos como "buscar + merge
        # campos o insert".
        existente = await self._session.get(
            PerfilInteresDespachoOrm, perfil.despacho_id,
        )
        if existente is None:
            orm = from_perfil_interes(perfil)
            self._session.add(orm)
            await self._session.flush()
            await self._session.refresh(orm)
            return to_perfil_interes(orm)

        # Actualizar campos in-place (reusa fila existente).
        existente.areas_tematicas = list(perfil.areas_tematicas)
        existente.comisiones_legislador = list(perfil.comisiones_legislador)
        existente.distritos_observados = list(perfil.distritos_observados)
        existente.aliases_legislador = list(perfil.aliases_legislador)
        existente.sembrado_at = perfil.sembrado_at
        existente.editado_at = perfil.editado_at
        await self._session.flush()
        await self._session.refresh(existente)
        return to_perfil_interes(existente)
