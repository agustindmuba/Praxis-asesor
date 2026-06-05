"""Repositorio SQLAlchemy de `ProyectoEnRedaccion` (feat-42.3)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import ProyectoRedaccionRepository
from praxis.domain import ProyectoEnRedaccion
from praxis.infrastructure.persistence.mappers import (
    from_proyecto,
    to_proyecto,
)
from praxis.infrastructure.persistence.models import ProyectoRedaccionOrm


class SqlAlchemyProyectoRedaccionRepository(ProyectoRedaccionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, proyecto: ProyectoEnRedaccion) -> ProyectoEnRedaccion:
        if proyecto.id is None:
            proyecto.id = uuid4()
        orm = from_proyecto(proyecto)
        self._session.add(orm)
        await self._session.flush()
        return to_proyecto(orm)

    async def buscar_por_id(
        self, proyecto_id: UUID,
    ) -> ProyectoEnRedaccion | None:
        orm = await self._session.get(ProyectoRedaccionOrm, proyecto_id)
        return to_proyecto(orm) if orm is not None else None

    async def listar_por_despacho(
        self, despacho_id: UUID, *, limit: int = 50,
    ) -> list[ProyectoEnRedaccion]:
        stmt = (
            select(ProyectoRedaccionOrm)
            .where(ProyectoRedaccionOrm.despacho_id == despacho_id)
            .order_by(ProyectoRedaccionOrm.actualizado_en.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [to_proyecto(o) for o in result.scalars().all()]

    async def actualizar(
        self, proyecto: ProyectoEnRedaccion,
    ) -> ProyectoEnRedaccion:
        if proyecto.id is None:
            raise ValueError("actualizar requiere id no nulo")
        orm = await self._session.get(ProyectoRedaccionOrm, proyecto.id)
        if orm is None:
            raise ValueError(f"Proyecto {proyecto.id} no existe")
        orm.tipo = proyecto.tipo.value
        orm.titulo = proyecto.titulo
        orm.sumario = proyecto.sumario
        orm.articulado = list(proyecto.articulado)
        orm.fundamentos = proyecto.fundamentos
        orm.cofirmantes_sugeridos = list(proyecto.cofirmantes_sugeridos)
        orm.estado = proyecto.estado.value
        orm.autor_legislador = proyecto.autor_legislador
        if proyecto.modelo_asistente is not None:
            orm.modelo_asistente = proyecto.modelo_asistente
        orm.prompt_version = proyecto.prompt_version
        await self._session.flush()
        return to_proyecto(orm)

    async def eliminar(self, proyecto_id: UUID) -> bool:
        orm = await self._session.get(ProyectoRedaccionOrm, proyecto_id)
        if orm is None:
            return False
        await self._session.delete(orm)
        return True
