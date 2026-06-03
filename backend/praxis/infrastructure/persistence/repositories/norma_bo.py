"""Repositorios SQLAlchemy para BO: NormaBO + NormaBOTexto +
ClasificacionNormaBO + NormaBOAccionable.

Cuatro repos en un archivo porque pertenecen al mismo agregado y se
escriben/leen juntos en los casos de uso del scraper BO (feat-39.3+).

- `SqlAlchemyNormaBORepository`: upsert idempotente por identidad
  natural; lookup por hash, por id, por fecha.
- `SqlAlchemyNormaBOTextoRepository`: 1:1 con NormaBO, tabla aparte.
- `SqlAlchemyClasificacionNormaBORepository`: UNIQUE en `norma_id`,
  reclasificar = delete + insert.
- `SqlAlchemyNormaBOAccionableRepository`: tenant-scoped por
  `despacho_id`; expose `borrar_por_despacho_y_fecha` para recálculos
  atómicos cuando cambia el perfil.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    ClasificacionNormaBORepository,
    NormaBOAccionableRepository,
    NormaBORepository,
    NormaBOTextoRepository,
)
from praxis.domain import (
    ClasificacionNormaBO,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    SeccionBO,
)
from praxis.infrastructure.persistence.mappers import (
    from_clasificacion_norma_bo,
    from_norma_bo,
    from_norma_bo_accionable,
    from_norma_bo_texto,
    to_clasificacion_norma_bo,
    to_norma_bo,
    to_norma_bo_accionable,
    to_norma_bo_texto,
)
from praxis.infrastructure.persistence.models import (
    ClasificacionNormaBOOrm,
    NormaBOAccionableOrm,
    NormaBOOrm,
    NormaBOTextoOrm,
)


class SqlAlchemyNormaBORepository(NormaBORepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_lote(self, normas: list[NormaBO]) -> list[NormaBO]:
        """Idempotente: si ya existe por identidad natural, devuelve la
        existente sin tocar; si no, inserta.

        El identificador de identidad es
        `(fecha_publicacion, seccion, tipo_norma, numero_norma)`. Como
        backup, también miramos por `hash_sumario` (UNIQUE).
        """
        if not normas:
            return []

        resultado: list[NormaBO] = []
        for norma in normas:
            stmt = select(NormaBOOrm).where(
                NormaBOOrm.fecha_publicacion == norma.fecha_publicacion,
                NormaBOOrm.seccion == norma.seccion.value,
                NormaBOOrm.tipo_norma == norma.tipo_norma,
                NormaBOOrm.numero_norma == norma.numero_norma,
            )
            existente = (
                await self._session.execute(stmt)
            ).scalar_one_or_none()
            if existente is not None:
                resultado.append(to_norma_bo(existente))
                continue

            orm = from_norma_bo(norma)
            self._session.add(orm)
            await self._session.flush()
            await self._session.refresh(orm)
            resultado.append(to_norma_bo(orm))
        return resultado

    async def buscar_por_id(self, norma_id: UUID) -> NormaBO | None:
        orm = await self._session.get(NormaBOOrm, norma_id)
        return to_norma_bo(orm) if orm is not None else None

    async def listar_por_fecha(
        self, fecha: date, *, seccion: SeccionBO | None = None,
    ) -> list[NormaBO]:
        stmt = select(NormaBOOrm).where(
            NormaBOOrm.fecha_publicacion == fecha,
        )
        if seccion is not None:
            stmt = stmt.where(NormaBOOrm.seccion == seccion.value)
        stmt = stmt.order_by(NormaBOOrm.numero_norma)
        result = await self._session.execute(stmt)
        return [to_norma_bo(orm) for orm in result.scalars()]

    async def buscar_por_hash(self, hash_sumario: str) -> NormaBO | None:
        stmt = select(NormaBOOrm).where(
            NormaBOOrm.hash_sumario == hash_sumario,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_norma_bo(orm) if orm is not None else None


class SqlAlchemyNormaBOTextoRepository(NormaBOTextoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def crear(self, texto: NormaBOTexto) -> NormaBOTexto:
        orm = from_norma_bo_texto(texto)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return to_norma_bo_texto(orm)

    async def buscar_por_norma(
        self, norma_id: UUID,
    ) -> NormaBOTexto | None:
        orm = await self._session.get(NormaBOTextoOrm, norma_id)
        return to_norma_bo_texto(orm) if orm is not None else None


class SqlAlchemyClasificacionNormaBORepository(
    ClasificacionNormaBORepository,
):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_norma(
        self, norma_id: UUID,
    ) -> ClasificacionNormaBO | None:
        stmt = select(ClasificacionNormaBOOrm).where(
            ClasificacionNormaBOOrm.norma_id == norma_id,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return to_clasificacion_norma_bo(orm) if orm is not None else None

    async def crear(
        self, clasif: ClasificacionNormaBO,
    ) -> ClasificacionNormaBO:
        orm = from_clasificacion_norma_bo(clasif)
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return to_clasificacion_norma_bo(orm)

    async def eliminar(self, norma_id: UUID) -> bool:
        stmt = delete(ClasificacionNormaBOOrm).where(
            ClasificacionNormaBOOrm.norma_id == norma_id,
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]


class SqlAlchemyNormaBOAccionableRepository(NormaBOAccionableRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, accionable: NormaBOAccionable,
    ) -> NormaBOAccionable:
        existente = await self._session.get(
            NormaBOAccionableOrm,
            (accionable.norma_id, accionable.despacho_id),
        )
        if existente is None:
            orm = from_norma_bo_accionable(accionable)
            self._session.add(orm)
            await self._session.flush()
            await self._session.refresh(orm)
            return to_norma_bo_accionable(orm)

        existente.score = accionable.score
        existente.prioridad = accionable.prioridad.value
        existente.razon = accionable.razon
        existente.expedientes_tocados = [
            str(eid) for eid in accionable.expedientes_tocados
        ]
        await self._session.flush()
        await self._session.refresh(existente)
        return to_norma_bo_accionable(existente)

    async def listar_por_despacho_y_fecha(
        self,
        *,
        despacho_id: UUID,
        fecha: date,
        top_n: int | None = None,
    ) -> list[NormaBOAccionable]:
        # JOIN para filtrar por fecha de la norma. Tenant-scoped por
        # despacho_id explícito.
        stmt = (
            select(NormaBOAccionableOrm)
            .join(
                NormaBOOrm,
                NormaBOAccionableOrm.norma_id == NormaBOOrm.id,
            )
            .where(
                NormaBOAccionableOrm.despacho_id == despacho_id,
                NormaBOOrm.fecha_publicacion == fecha,
            )
            .order_by(NormaBOAccionableOrm.score.desc())
        )
        if top_n is not None:
            stmt = stmt.limit(top_n)
        result = await self._session.execute(stmt)
        return [to_norma_bo_accionable(orm) for orm in result.scalars()]

    async def borrar_por_despacho_y_fecha(
        self, *, despacho_id: UUID, fecha: date,
    ) -> int:
        # Necesitamos saber qué norma_ids tienen esa fecha para borrar.
        stmt_normas = select(NormaBOOrm.id).where(
            NormaBOOrm.fecha_publicacion == fecha,
        )
        norma_ids = (await self._session.execute(stmt_normas)).scalars().all()
        if not norma_ids:
            return 0

        stmt = delete(NormaBOAccionableOrm).where(
            NormaBOAccionableOrm.despacho_id == despacho_id,
            NormaBOAccionableOrm.norma_id.in_(norma_ids),
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
