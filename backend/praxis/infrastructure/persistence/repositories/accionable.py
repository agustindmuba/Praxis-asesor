"""Repositorio SQLAlchemy de `AccionableEvento` (feat-42.2)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import AccionableEventoRepository
from praxis.domain import AccionableEvento, TipoEvento
from praxis.infrastructure.persistence.mappers import (
    from_accionable,
    to_accionable,
)
from praxis.infrastructure.persistence.models import AccionableEventoOrm


class SqlAlchemyAccionableEventoRepository(AccionableEventoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_evento(
        self,
        *,
        despacho_id: UUID,
        tipo_evento: TipoEvento,
        evento_id: UUID,
    ) -> AccionableEvento | None:
        stmt = select(AccionableEventoOrm).where(
            AccionableEventoOrm.despacho_id == despacho_id,
            AccionableEventoOrm.tipo_evento == tipo_evento.value,
            AccionableEventoOrm.evento_id == evento_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_accionable(orm) if orm is not None else None

    async def upsert(
        self, accionable: AccionableEvento,
    ) -> AccionableEvento:
        # Buscar por UNIQUE clave (despacho, tipo, evento).
        existente = await self.buscar_por_evento(
            despacho_id=accionable.despacho_id,
            tipo_evento=accionable.tipo_evento,
            evento_id=accionable.evento_id,
        )
        if existente is None:
            if accionable.id is None:
                accionable.id = uuid4()
            orm = from_accionable(accionable)
            self._session.add(orm)
            await self._session.flush()
            return to_accionable(orm)
        # Replace en lugar de update — el regenerar pisa todo.
        stmt = select(AccionableEventoOrm).where(
            AccionableEventoOrm.id == existente.id,
        )
        orm = (await self._session.execute(stmt)).scalar_one()
        orm.razon_para_despacho = accionable.razon_para_despacho
        orm.accion_sugerida = accionable.accion_sugerida.value
        orm.explicacion_accion = accionable.explicacion_accion
        orm.tweets_sugeridos = [
            {"tono": t.tono, "texto": t.texto, "caracteres": t.caracteres}
            for t in accionable.tweets_sugeridos
        ]
        orm.confianza = accionable.confianza.value
        if accionable.generado_en is not None:
            orm.generado_en = accionable.generado_en
        if accionable.editado_en is not None:
            orm.editado_en = accionable.editado_en
        if accionable.modelo is not None:
            orm.modelo = accionable.modelo
        orm.prompt_version = accionable.prompt_version
        await self._session.flush()
        return to_accionable(orm)

    async def listar_por_despacho_y_tipo(
        self,
        *,
        despacho_id: UUID,
        tipo_evento: TipoEvento,
    ) -> list[AccionableEvento]:
        stmt = (
            select(AccionableEventoOrm)
            .where(
                AccionableEventoOrm.despacho_id == despacho_id,
                AccionableEventoOrm.tipo_evento == tipo_evento.value,
            )
            .order_by(AccionableEventoOrm.generado_en.desc())
        )
        result = await self._session.execute(stmt)
        return [to_accionable(o) for o in result.scalars().all()]
