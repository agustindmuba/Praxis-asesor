"""Repositorio de Expediente sobre SQLAlchemy async."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from praxis.application.ports import ExpedienteRepository
from praxis.domain import (
    Expediente,
    ExpedienteQuery,
    NumeroExpediente,
    ResultadoBusqueda,
)
from praxis.infrastructure.persistence.mappers import from_expediente, to_expediente
from praxis.infrastructure.persistence.models import (
    ExpedienteAreaTematicaOrm,
    ExpedienteOrm,
    FirmanteOrm,
    GiroOrm,
    SeguimientoExpedienteOrm,
)


def _ilike_contains(column: Any, value: str) -> ColumnElement[bool]:
    """Match case-insensitive de `value` contenido en `column`.

    Usa `LOWER(col) LIKE '%lower(value)%'` para portabilidad SQLite ↔ Postgres
    (ILIKE solo existe en Postgres y el LIKE de SQLite no es case-insensitive
    para caracteres no-ASCII como ñ, á, é).

    El parámetro `column` se tipa como `Any` porque acá entra tanto un
    `InstrumentedAttribute` (ej. `FirmanteOrm.nombre`) como un `ColumnElement`
    crudo, y unificar ambos en el sistema de tipos de SQLAlchemy 2.0 obliga
    a importar APIs internas que no vale la pena exponer.

    Trade-off: descarta cualquier índice sobre `column` para esta query. Es
    aceptable en MVP. Cuando duela migramos a `tsvector` + GIN en Postgres.
    """
    return func.lower(column).like(f"%{value.lower()}%")


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

    # -----------------------------------------------------------------------
    # Búsqueda filtrada — ver docs/specs/08-busqueda-expedientes.md
    # -----------------------------------------------------------------------

    def _build_predicate(self, query: ExpedienteQuery) -> list[ColumnElement[bool]]:
        """Construye la lista de condiciones WHERE desde un ExpedienteQuery.

        Compartido entre `buscar` y `contar` para que ambos apliquen el
        mismo filtro exactamente (el `total` es del mismo set que la página).
        """
        conds: list[ColumnElement[bool]] = []

        if query.texto is not None:
            # texto matchea en titulo OR sumario. sumario puede ser NULL —
            # COALESCE para que el LIKE no falle.
            t = query.texto.strip().lower()
            conds.append(
                func.lower(
                    func.coalesce(ExpedienteOrm.titulo, "")
                    + " "
                    + func.coalesce(ExpedienteOrm.sumario, "")
                ).like(f"%{t}%")
            )
        if query.anio is not None:
            conds.append(ExpedienteOrm.anio == query.anio)
        if query.tipo is not None:
            conds.append(ExpedienteOrm.tipo == query.tipo.value)
        if query.camara is not None:
            conds.append(ExpedienteOrm.camara == query.camara.value)
        if query.origen is not None:
            conds.append(ExpedienteOrm.origen == query.origen.value)
        if query.estado is not None:
            conds.append(ExpedienteOrm.estado == query.estado.value)
        if query.fecha_ingreso_desde is not None:
            conds.append(ExpedienteOrm.fecha_ingreso >= query.fecha_ingreso_desde)
        if query.fecha_ingreso_hasta is not None:
            conds.append(ExpedienteOrm.fecha_ingreso <= query.fecha_ingreso_hasta)

        if query.autor_nombre is not None:
            # EXISTS: un expediente con N firmantes no se duplica en el output.
            subq = (
                select(FirmanteOrm.id)
                .where(
                    FirmanteOrm.expediente_id == ExpedienteOrm.id,
                    _ilike_contains(FirmanteOrm.nombre, query.autor_nombre.strip()),
                )
                .exists()
            )
            conds.append(subq)
        if query.comision is not None:
            subq = (
                select(GiroOrm.id)
                .where(
                    GiroOrm.expediente_id == ExpedienteOrm.id,
                    _ilike_contains(GiroOrm.comision, query.comision.strip()),
                )
                .exists()
            )
            conds.append(subq)

        # ----- Filtros derivados del despacho (feat-43.1) -----

        if query.area_tematica is not None:
            subq = (
                select(ExpedienteAreaTematicaOrm.expediente_id)
                .where(
                    ExpedienteAreaTematicaOrm.expediente_id == ExpedienteOrm.id,
                    ExpedienteAreaTematicaOrm.area == query.area_tematica.value,
                )
                .exists()
            )
            conds.append(subq)

        if query.con_dictamen:
            # "Con dictamen" = expedientes que YA pasaron de mero ingreso/comision.
            # Incluye dictamen firmado, media sancion y sancionado.
            conds.append(
                ExpedienteOrm.estado.in_([
                    "con_dictamen",
                    "media_sancion_hcdn",
                    "media_sancion_hsn",
                    "sancionado",
                ])
            )

        if query.por_caducar_dias is not None:
            # Ley 13.640: caduca si no avanza. Mostramos solo los que vencen
            # dentro de los proximos N dias (y todavia no estan caducos).
            from datetime import date as _date, timedelta as _timedelta
            limite = _date.today() + _timedelta(days=query.por_caducar_dias)
            conds.append(ExpedienteOrm.fecha_caducidad.is_not(None))
            conds.append(ExpedienteOrm.fecha_caducidad <= limite)
            conds.append(ExpedienteOrm.fecha_caducidad >= _date.today())
            conds.append(ExpedienteOrm.estado != "caduco")
            conds.append(ExpedienteOrm.estado != "sancionado")

        if query.con_seguimiento_del_despacho is not None:
            subq = (
                select(SeguimientoExpedienteOrm.expediente_id)
                .where(
                    SeguimientoExpedienteOrm.expediente_id == ExpedienteOrm.id,
                    SeguimientoExpedienteOrm.despacho_id
                    == query.con_seguimiento_del_despacho,
                )
                .exists()
            )
            conds.append(subq)

        if query.firmados_por_titular_slug is not None:
            # Match laxo: el slug es "JULIANO, PABLO" -> matchea por
            # "juliano" en LOWER(firmante.nombre). Permite que el slug del
            # despacho sea distinto del nombre exacto que cargo HCDN.
            slug = query.firmados_por_titular_slug.strip().split(",")[0].strip().lower()
            if slug:
                subq = (
                    select(FirmanteOrm.id)
                    .where(
                        FirmanteOrm.expediente_id == ExpedienteOrm.id,
                        _ilike_contains(FirmanteOrm.nombre, slug),
                    )
                    .exists()
                )
                conds.append(subq)

        return conds

    async def buscar(self, query: ExpedienteQuery) -> ResultadoBusqueda:
        """Implementación de búsqueda filtrada con paginación.

        Hace 2 queries: una para los items (con limit/offset) y otra para
        el `total` (count del mismo predicate). Vale el roundtrip extra —
        la UI lo necesita y no es hot path.
        """
        conds = self._build_predicate(query)

        items_stmt = (
            select(ExpedienteOrm)
            .where(*conds)
            .order_by(
                # NULLS LAST: expedientes sin fecha_ingreso al final, no al inicio.
                ExpedienteOrm.fecha_ingreso.desc().nulls_last(),
                ExpedienteOrm.id.desc(),
            )
            .limit(query.limit)
            .offset(query.offset)
            .options(
                selectinload(ExpedienteOrm.firmantes),
                selectinload(ExpedienteOrm.giros),
                selectinload(ExpedienteOrm.tramite),
            )
        )
        items_result = await self._session.execute(items_stmt)
        items = [to_expediente(orm) for orm in items_result.scalars()]

        count_stmt = select(func.count()).select_from(ExpedienteOrm).where(*conds)
        count_result = await self._session.execute(count_stmt)
        total = int(count_result.scalar_one())

        return ResultadoBusqueda(items=items, total=total, limit=query.limit, offset=query.offset)

    async def contar(self, query: ExpedienteQuery) -> int:
        """Conteo puro del predicate. Ignora limit/offset del query."""
        conds = self._build_predicate(query)
        stmt = select(func.count()).select_from(ExpedienteOrm).where(*conds)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
