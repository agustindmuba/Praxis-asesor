"""Repositorio de Expediente sobre SQLAlchemy async."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from praxis.application.ports import ExpedienteRepository
from praxis.domain import Expediente, NumeroExpediente
from praxis.infrastructure.persistence.mappers import from_expediente, to_expediente
from praxis.infrastructure.persistence.models import ExpedienteOrm


class SqlAlchemyExpedienteRepository(ExpedienteRepository):
    """Persistencia de Expediente (+ firmantes, giros, trámite) en Postgres.

    `crear` inserta de cero. `buscar_por_*` carga el agregado completo
    con eager loading de relaciones (selectinload) para evitar N+1.

    Convención (igual que `SqlAlchemyDespachoRepository`): el caller
    maneja la transacción (commit/rollback). El repo solo flushea.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, expediente: Expediente) -> Expediente:
        orm = from_expediente(expediente)
        self._session.add(orm)
        await self._session.flush()
        # Recargar con las relaciones para que to_expediente devuelva todo poblado.
        await self._session.refresh(orm, ["firmantes", "giros", "tramite"])
        return to_expediente(orm)

    async def buscar_por_id(self, expediente_id: UUID) -> Expediente | None:
        stmt = (
            select(ExpedienteOrm)
            .where(ExpedienteOrm.id == expediente_id)
            .options(
                selectinload(ExpedienteOrm.firmantes),
                selectinload(ExpedienteOrm.giros),
                selectinload(ExpedienteOrm.tramite),
            )
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_expediente(orm) if orm is not None else None

    async def buscar_por_numero(self, numero: NumeroExpediente) -> Expediente | None:
        stmt = (
            select(ExpedienteOrm)
            .where(
                ExpedienteOrm.numero == numero.numero,
                ExpedienteOrm.origen == numero.origen.value,
                ExpedienteOrm.anio == numero.anio,
                ExpedienteOrm.camara == numero.camara.value,
            )
            .options(
                selectinload(ExpedienteOrm.firmantes),
                selectinload(ExpedienteOrm.giros),
                selectinload(ExpedienteOrm.tramite),
            )
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_expediente(orm) if orm is not None else None

    async def listar(self, *, limit: int = 50, offset: int = 0) -> list[Expediente]:
        stmt = (
            select(ExpedienteOrm)
            .order_by(ExpedienteOrm.id)  # UUID v7 ⇒ orden temporal aproximado.
            .limit(limit)
            .offset(offset)
            .options(
                selectinload(ExpedienteOrm.firmantes),
                selectinload(ExpedienteOrm.giros),
                selectinload(ExpedienteOrm.tramite),
            )
        )
        result = await self._session.execute(stmt)
        return [to_expediente(orm) for orm in result.scalars()]
