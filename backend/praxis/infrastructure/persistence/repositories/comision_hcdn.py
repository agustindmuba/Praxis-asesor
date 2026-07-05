"""Repo SQL de ComisionHcdn + integrantes + reuniones (feat-61.3).

Idempotencia:
- `upsert` (camara, slug): si existe, actualiza nombre/url/tipo/descripcion.
- `reemplazar_integrantes`: DELETE + INSERT atómico del set completo
  (el scraper trae el listado oficial cada corrida).
- `upsert_reuniones` (comision_id, fecha, titulo): ignora duplicados.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import ComisionHcdnRepository
from praxis.domain import (
    Camara,
    ComisionHcdn,
    IntegranteComision,
    ReunionComision,
    TipoComision,
)
from praxis.infrastructure.persistence.base import uuid7
from praxis.infrastructure.persistence.models import (
    ComisionHcdnOrm,
    IntegranteComisionOrm,
    ReunionComisionOrm,
)


def _comision_to_domain(orm: ComisionHcdnOrm) -> ComisionHcdn:
    return ComisionHcdn(
        id=orm.id,
        camara=Camara(orm.camara),
        slug=orm.slug,
        nombre=orm.nombre,
        tipo=TipoComision(orm.tipo),
        url_oficial=orm.url_oficial,
        descripcion=orm.descripcion,
        capturado_en=orm.capturado_en,
    )


def _integrante_to_domain(orm: IntegranteComisionOrm) -> IntegranteComision:
    return IntegranteComision(
        id=orm.id,
        comision_id=orm.comision_id,
        nombre_diputado=orm.nombre_diputado,
        cargo=orm.cargo,
        partido=orm.partido,
        distrito=orm.distrito,
        legislador_id=orm.legislador_id,
        capturado_en=orm.capturado_en,
    )


def _reunion_to_domain(orm: ReunionComisionOrm) -> ReunionComision:
    return ReunionComision(
        id=orm.id,
        comision_id=orm.comision_id,
        fecha=orm.fecha,
        titulo=orm.titulo,
        hora=orm.hora,
        sala=orm.sala,
        citacion_pdf_url=orm.citacion_pdf_url,
        descripcion=orm.descripcion,
        comisiones_invitadas=list(orm.comisiones_invitadas or []),
        tema_corto=orm.tema_corto,
        tipo_reunion=orm.tipo_reunion,
        convocada_por=orm.convocada_por,
        expedientes_citados=list(orm.expedientes_citados or []),
        oportunidad_politica=orm.oportunidad_politica,
        accion_sugerida=orm.accion_sugerida,
        huella_historica=orm.huella_historica,
        enriquecida_en=orm.enriquecida_en,
        capturado_en=orm.capturado_en,
    )


class SqlAlchemyComisionHcdnRepository(ComisionHcdnRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, comision: ComisionHcdn) -> ComisionHcdn:
        stmt = (
            pg_insert(ComisionHcdnOrm)
            .values(
                id=uuid7(),
                camara=comision.camara.value,
                slug=comision.slug,
                nombre=comision.nombre,
                tipo=comision.tipo.value,
                url_oficial=comision.url_oficial,
                descripcion=comision.descripcion,
            )
            .on_conflict_do_update(
                constraint="uq_comision_hcdn_camara_slug",
                set_={
                    "nombre": comision.nombre,
                    "tipo": comision.tipo.value,
                    "url_oficial": comision.url_oficial,
                    "descripcion": comision.descripcion,
                },
            )
            .returning(ComisionHcdnOrm)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one()
        return _comision_to_domain(orm)

    async def buscar_por_slug(
        self, *, camara: Camara, slug: str,
    ) -> ComisionHcdn | None:
        stmt = select(ComisionHcdnOrm).where(
            and_(
                ComisionHcdnOrm.camara == camara.value,
                ComisionHcdnOrm.slug == slug,
            ),
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _comision_to_domain(orm) if orm else None

    async def listar_todas(
        self, *, camara: Camara | None = None,
    ) -> list[ComisionHcdn]:
        stmt = select(ComisionHcdnOrm)
        if camara is not None:
            stmt = stmt.where(ComisionHcdnOrm.camara == camara.value)
        stmt = stmt.order_by(ComisionHcdnOrm.nombre)
        result = await self._session.execute(stmt)
        return [_comision_to_domain(o) for o in result.scalars().all()]

    async def listar_del_legislador(
        self, *, legislador_id: UUID,
    ) -> list[ComisionHcdn]:
        stmt = (
            select(ComisionHcdnOrm)
            .join(
                IntegranteComisionOrm,
                IntegranteComisionOrm.comision_id == ComisionHcdnOrm.id,
            )
            .where(IntegranteComisionOrm.legislador_id == legislador_id)
            .order_by(ComisionHcdnOrm.nombre)
        )
        result = await self._session.execute(stmt)
        return [_comision_to_domain(o) for o in result.scalars().unique().all()]

    async def reemplazar_integrantes(
        self, *, comision_id: UUID, integrantes: list[IntegranteComision],
    ) -> None:
        await self._session.execute(
            delete(IntegranteComisionOrm).where(
                IntegranteComisionOrm.comision_id == comision_id,
            ),
        )
        if not integrantes:
            return
        self._session.add_all([
            IntegranteComisionOrm(
                comision_id=comision_id,
                nombre_diputado=i.nombre_diputado,
                cargo=i.cargo,
                partido=i.partido,
                distrito=i.distrito,
                legislador_id=i.legislador_id,
            )
            for i in integrantes
        ])

    async def upsert_reuniones(
        self, *, comision_id: UUID, reuniones: list[ReunionComision],
    ) -> None:
        for r in reuniones:
            stmt = (
                pg_insert(ReunionComisionOrm)
                .values(
                    id=uuid7(),
                    comision_id=comision_id,
                    fecha=r.fecha,
                    titulo=r.titulo,
                    hora=r.hora,
                    sala=r.sala,
                    citacion_pdf_url=r.citacion_pdf_url,
                    descripcion=r.descripcion,
                    comisiones_invitadas=list(r.comisiones_invitadas),
                )
                .on_conflict_do_update(
                    constraint="uq_reunion_comision_fecha_titulo",
                    set_={
                        "hora": r.hora,
                        "sala": r.sala,
                        "citacion_pdf_url": r.citacion_pdf_url,
                        "descripcion": r.descripcion,
                        "comisiones_invitadas": list(r.comisiones_invitadas),
                    },
                )
            )
            await self._session.execute(stmt)

    async def proximas_reuniones(
        self,
        *,
        comisiones_ids: list[UUID],
        desde: date,
        hasta: date,
    ) -> list[ReunionComision]:
        if not comisiones_ids:
            return []
        stmt = (
            select(ReunionComisionOrm)
            .where(
                ReunionComisionOrm.comision_id.in_(comisiones_ids),
                ReunionComisionOrm.fecha >= desde,
                ReunionComisionOrm.fecha <= hasta,
            )
            .order_by(ReunionComisionOrm.fecha)
        )
        result = await self._session.execute(stmt)
        return [_reunion_to_domain(o) for o in result.scalars().all()]

    async def proximas_reuniones_por_apellido(
        self,
        *,
        apellido: str,
        desde: date,
        hasta: date,
        limit: int = 5,
    ) -> list[tuple[ReunionComision, str, str]]:
        stmt = (
            select(
                ReunionComisionOrm,
                ComisionHcdnOrm.nombre,
                ComisionHcdnOrm.url_oficial,
            )
            .join(
                ComisionHcdnOrm,
                ComisionHcdnOrm.id == ReunionComisionOrm.comision_id,
            )
            .join(
                IntegranteComisionOrm,
                and_(
                    IntegranteComisionOrm.comision_id == ComisionHcdnOrm.id,
                    IntegranteComisionOrm.nombre_diputado.ilike(
                        f"%{apellido}%",
                    ),
                ),
            )
            .where(
                ReunionComisionOrm.fecha >= desde,
                ReunionComisionOrm.fecha <= hasta,
            )
            .order_by(ReunionComisionOrm.fecha)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        out: list[tuple[ReunionComision, str, str]] = []
        for reunion, nombre, url in result.all():
            out.append((_reunion_to_domain(reunion), nombre, url or ""))
        return out

    async def buscar_reunion_por_id(
        self, reunion_id: UUID,
    ) -> ReunionComision | None:
        stmt = select(ReunionComisionOrm).where(
            ReunionComisionOrm.id == reunion_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _reunion_to_domain(orm) if orm else None

    async def actualizar_enriquecimiento_reunion(
        self,
        *,
        reunion_id: UUID,
        tema_corto: str,
        tipo_reunion: str,
        convocada_por: str,
        expedientes_citados: list[str],
        oportunidad_politica: str,
        accion_sugerida: str,
        huella_historica: str | None,
        enriquecida_en: datetime,
    ) -> None:
        stmt = (
            update(ReunionComisionOrm)
            .where(ReunionComisionOrm.id == reunion_id)
            .values(
                tema_corto=tema_corto,
                tipo_reunion=tipo_reunion,
                convocada_por=convocada_por,
                expedientes_citados=list(expedientes_citados),
                oportunidad_politica=oportunidad_politica,
                accion_sugerida=accion_sugerida,
                huella_historica=huella_historica,
                enriquecida_en=enriquecida_en,
            )
        )
        await self._session.execute(stmt)
