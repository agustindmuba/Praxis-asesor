"""Repositorio SQLAlchemy de `PerfilOpositorDespacho` (feat-42.1).

1 fila por despacho. Upsert reemplaza la fila entera; el caller
decide si setear `inferido_en` (corrida del bot) o `editado_en`
(edición manual del asesor).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import PerfilOpositorRepository
from praxis.domain import PerfilOpositorDespacho
from praxis.infrastructure.persistence.mappers import (
    from_perfil_opositor,
    to_perfil_opositor,
)
from praxis.infrastructure.persistence.models import PerfilOpositorDespachoOrm


class SqlAlchemyPerfilOpositorRepository(PerfilOpositorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilOpositorDespacho | None:
        stmt = select(PerfilOpositorDespachoOrm).where(
            PerfilOpositorDespachoOrm.despacho_id == despacho_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return to_perfil_opositor(orm) if orm is not None else None

    async def upsert(
        self, perfil: PerfilOpositorDespacho,
    ) -> PerfilOpositorDespacho:
        existente = await self._session.get(
            PerfilOpositorDespachoOrm, perfil.despacho_id,
        )
        nueva_orm = from_perfil_opositor(perfil)
        if existente is None:
            self._session.add(nueva_orm)
            await self._session.flush()
            return to_perfil_opositor(nueva_orm)
        # Merge campo a campo (preservamos timestamps que el dominio
        # NO trajo si vienen None).
        existente.bandera_principal = nueva_orm.bandera_principal
        existente.banderas_secundarias = nueva_orm.banderas_secundarias
        existente.temas_de_cuidado = nueva_orm.temas_de_cuidado
        existente.tono_comunicacional = nueva_orm.tono_comunicacional
        existente.adversarios = nueva_orm.adversarios
        existente.aliados = nueva_orm.aliados
        existente.linea_de_bloque = nueva_orm.linea_de_bloque
        existente.justificacion_evidencia = nueva_orm.justificacion_evidencia
        existente.advertencias = nueva_orm.advertencias
        existente.confianza_global = nueva_orm.confianza_global
        if nueva_orm.inferido_en is not None:
            existente.inferido_en = nueva_orm.inferido_en
        if nueva_orm.editado_en is not None:
            existente.editado_en = nueva_orm.editado_en
        if nueva_orm.modelo_inferencia is not None:
            existente.modelo_inferencia = nueva_orm.modelo_inferencia
        existente.prompt_version = nueva_orm.prompt_version
        await self._session.flush()
        return to_perfil_opositor(existente)
