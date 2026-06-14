"""Repo SQL de Efemerides (feat-53.1)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import EfemerideRepository
from praxis.domain import Efemeride, RelevanciaEfemeride, TipoEfemeride
from praxis.infrastructure.persistence.models import EfemerideOrm


# Orden de prioridad para 'relevancia_minima': alta > media > baja.
_RELEVANCIAS_PERMITIDAS: dict[str, set[str]] = {
    "alta": {"alta"},
    "media": {"alta", "media"},
    "baja": {"alta", "media", "baja"},
}


def _to_domain(orm: EfemerideOrm) -> Efemeride:
    return Efemeride(
        id=orm.id,
        mes=orm.mes,
        dia=orm.dia,
        titulo=orm.titulo,
        tipo=TipoEfemeride(orm.tipo),
        relevancia=RelevanciaEfemeride(orm.relevancia),
        descripcion=orm.descripcion,
        fuente=orm.fuente,
        areas_tematicas=list(orm.areas_tematicas or []),
        anio_unico=orm.anio_unico,
        creado_en=orm.creado_en,
    )


class SqlAlchemyEfemerideRepository(EfemerideRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_id(self, efemeride_id: UUID) -> Efemeride | None:
        stmt = select(EfemerideOrm).where(EfemerideOrm.id == efemeride_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def proximas(
        self,
        *,
        desde_mes: int,
        desde_dia: int,
        dias: int = 30,
        relevancia_minima: str = "media",
    ) -> list[Efemeride]:
        """Devuelve las efemérides recurrentes que caen en los próximos N días
        a partir de (desde_mes, desde_dia). Sin cruce de fin de año por simpleza
        del MVP — si caés cerca del 31/12, vas a ver las de enero solo cuando
        cambies de año (lo aceptamos como deuda controlada).
        """
        rels = _RELEVANCIAS_PERMITIDAS.get(relevancia_minima, {"alta", "media"})
        stmt = select(EfemerideOrm).where(
            EfemerideOrm.relevancia.in_(rels),
        )
        result = await self._session.execute(stmt)
        todas = [_to_domain(o) for o in result.scalars()]

        # Filtro en memoria: armar lista de (mes, dia) target para los
        # próximos `dias` y quedarse con efemérides cuya fecha caiga ahí.
        # Es eficiente porque el corpus de efemérides es chico (~80-500).
        from datetime import date, timedelta
        base = date(2000, desde_mes, desde_dia)  # año dummy, solo MM-DD importa
        ventana = {
            (base + timedelta(days=i)).month * 100 + (base + timedelta(days=i)).day
            for i in range(dias)
        }
        fechas_efemerides = [
            (ef, ef.mes * 100 + ef.dia)
            for ef in todas
            if ef.es_recurrente
        ]
        # Ordenar por (mes, dia) ascendente desde el día de hoy
        proximas = [(ef, key) for ef, key in fechas_efemerides if key in ventana]

        def _orden(item: tuple[Efemeride, int]) -> int:
            ef, key = item
            base_key = desde_mes * 100 + desde_dia
            # Distancia circular dentro de la ventana
            return (key - base_key) % 1300

        proximas.sort(key=_orden)
        return [ef for ef, _ in proximas]

    async def listar_todas(
        self, *, tipo: str | None = None, relevancia: str | None = None,
    ) -> list[Efemeride]:
        stmt = select(EfemerideOrm)
        if tipo is not None:
            stmt = stmt.where(EfemerideOrm.tipo == tipo)
        if relevancia is not None:
            stmt = stmt.where(EfemerideOrm.relevancia == relevancia)
        stmt = stmt.order_by(EfemerideOrm.mes, EfemerideOrm.dia)
        result = await self._session.execute(stmt)
        return [_to_domain(o) for o in result.scalars()]
