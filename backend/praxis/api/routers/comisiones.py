"""Router `/comisiones` — endpoints REST de comisiones HCDN (feat-61.6).

- GET /comisiones — todas las comisiones (catálogo público).
- GET /comisiones/del-despacho — las que integra el legislador titular.
- GET /comisiones/{id} — detalle + integrantes.
- GET /comisiones/{id}/reuniones — agenda de esa comisión.
- GET /comisiones/agenda-del-despacho — reuniones próximas de TODAS las
  comisiones del despacho, ordenadas por fecha.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from praxis.api.deps import CurrentContext, LlmProviderDep, SessionDep
from praxis.application.use_cases.enriquecer_reunion_comision import (
    EnriquecerReunionComision,
)
from praxis.domain import Camara
from praxis.infrastructure.persistence.models import (
    ComisionHcdnOrm,
    IntegranteComisionOrm,
    ReunionComisionOrm,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyComisionHcdnRepository,
    SqlAlchemyPerfilOpositorRepository,
)

router = APIRouter(prefix="/comisiones", tags=["comisiones"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class ComisionDTO(BaseModel):
    id: UUID
    camara: str
    slug: str
    nombre: str
    tipo: str
    url_oficial: str


class IntegranteDTO(BaseModel):
    id: UUID
    nombre_diputado: str
    cargo: str
    partido: str | None
    distrito: str | None


class ReunionDTO(BaseModel):
    id: UUID
    fecha: date
    titulo: str
    citacion_pdf_url: str | None


class ComisionDetalleDTO(ComisionDTO):
    integrantes: list[IntegranteDTO]


class ReunionConComisionDTO(ReunionDTO):
    comision_id: UUID
    comision_nombre: str
    rol_legislador: str | None  # Cargo del legislador titular en la comisión
    hora: str | None
    sala: str | None
    descripcion: str | None
    tema_corto: str | None
    tipo_reunion: str | None
    convocada_por: str | None
    oportunidad_politica: str | None
    accion_sugerida: str | None
    expedientes_citados: list[str]
    enriquecida_en: datetime | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_a_patron_apellido(slug: str | None) -> str | None:
    """Heurística MVP para matchear el slug del legislador titular con
    el `nombre_diputado` que viene del scraper.

    Casos conocidos:
    - "pjuliano" → "Juliano" (letra del primer nombre + apellido)
    - "JULIANO, PABLO" → "JULIANO" (formato del padrón crudo)
    - "Pablo Juliano" → "Juliano" (lo escrito a mano)
    """
    if not slug:
        return None
    s = slug.strip()
    if "," in s:
        return s.split(",", 1)[0].strip().split()[-1]
    palabras = s.replace("_", " ").split()
    if len(palabras) >= 2:
        # "Pablo Juliano" → apellido = última palabra capitalizada
        return palabras[-1]
    # Slug pegado tipo "pjuliano". Asumimos primer char = inicial nombre.
    if len(s) >= 4 and s[1:].isalpha():
        return s[1:]
    return s


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ComisionDTO])
async def listar_comisiones(session: SessionDep) -> list[ComisionDTO]:
    """Catálogo público de las 46 comisiones HCDN permanentes."""
    repo = SqlAlchemyComisionHcdnRepository(session)
    cs = await repo.listar_todas()
    return [
        ComisionDTO(
            id=c.id, camara=c.camara.value, slug=c.slug, nombre=c.nombre,
            tipo=c.tipo.value, url_oficial=c.url_oficial,
        )
        for c in cs if c.id is not None
    ]


@router.get("/del-despacho", response_model=list[ComisionDTO])
async def comisiones_del_despacho(
    session: SessionDep, ctx: CurrentContext,
) -> list[ComisionDTO]:
    """Comisiones donde figura el legislador titular del despacho.

    Match heurístico por apellido contra `nombre_diputado`. Cuando
    enlacemos `legislador_id` correctamente (feat futura), esto se vuelve
    una FK exacta.
    """
    patron = _slug_a_patron_apellido(ctx.despacho.legislador_titular_slug)
    if not patron:
        return []
    stmt = (
        select(ComisionHcdnOrm)
        .join(
            IntegranteComisionOrm,
            IntegranteComisionOrm.comision_id == ComisionHcdnOrm.id,
        )
        .where(IntegranteComisionOrm.nombre_diputado.ilike(f"%{patron}%"))
        .order_by(ComisionHcdnOrm.nombre)
        .distinct()
    )
    result = await session.execute(stmt)
    return [
        ComisionDTO(
            id=c.id, camara=c.camara, slug=c.slug, nombre=c.nombre,
            tipo=c.tipo, url_oficial=c.url_oficial,
        )
        for c in result.scalars().all()
    ]


@router.get(
    "/agenda-del-despacho",
    response_model=list[ReunionConComisionDTO],
)
async def agenda_del_despacho(
    session: SessionDep,
    ctx: CurrentContext,
    dias: Annotated[int, Query(ge=1, le=180)] = 30,
) -> list[ReunionConComisionDTO]:
    """Próximas reuniones de las comisiones del legislador titular."""
    patron = _slug_a_patron_apellido(ctx.despacho.legislador_titular_slug)
    if not patron:
        return []
    hoy = date.today()
    hasta = hoy + timedelta(days=dias)
    stmt = (
        select(
            ReunionComisionOrm,
            ComisionHcdnOrm.nombre,
            IntegranteComisionOrm.cargo,
        )
        .join(
            ComisionHcdnOrm, ComisionHcdnOrm.id == ReunionComisionOrm.comision_id,
        )
        .join(
            IntegranteComisionOrm,
            and_(
                IntegranteComisionOrm.comision_id == ComisionHcdnOrm.id,
                IntegranteComisionOrm.nombre_diputado.ilike(f"%{patron}%"),
            ),
        )
        .where(
            ReunionComisionOrm.fecha >= hoy,
            ReunionComisionOrm.fecha <= hasta,
        )
        .order_by(ReunionComisionOrm.fecha)
    )
    result = await session.execute(stmt)
    out: list[ReunionConComisionDTO] = []
    for reunion, comision_nombre, cargo in result.all():
        out.append(
            ReunionConComisionDTO(
                id=reunion.id,
                fecha=reunion.fecha,
                titulo=reunion.titulo,
                citacion_pdf_url=reunion.citacion_pdf_url,
                comision_id=reunion.comision_id,
                comision_nombre=comision_nombre,
                rol_legislador=cargo,
                hora=reunion.hora.strftime("%H:%M") if reunion.hora else None,
                sala=reunion.sala,
                descripcion=reunion.descripcion,
                tema_corto=reunion.tema_corto,
                tipo_reunion=reunion.tipo_reunion,
                convocada_por=reunion.convocada_por,
                oportunidad_politica=reunion.oportunidad_politica,
                accion_sugerida=reunion.accion_sugerida,
                expedientes_citados=list(reunion.expedientes_citados or []),
                enriquecida_en=reunion.enriquecida_en,
            ),
        )
    return out


@router.get("/{comision_id}", response_model=ComisionDetalleDTO)
async def detalle_comision(
    comision_id: UUID, session: SessionDep,
) -> ComisionDetalleDTO:
    stmt = select(ComisionHcdnOrm).where(ComisionHcdnOrm.id == comision_id)
    c = (await session.execute(stmt)).scalar_one_or_none()
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comisión no encontrada",
        )
    int_stmt = (
        select(IntegranteComisionOrm)
        .where(IntegranteComisionOrm.comision_id == comision_id)
        .order_by(IntegranteComisionOrm.cargo)
    )
    integrantes = (await session.execute(int_stmt)).scalars().all()
    return ComisionDetalleDTO(
        id=c.id, camara=c.camara, slug=c.slug, nombre=c.nombre,
        tipo=c.tipo, url_oficial=c.url_oficial,
        integrantes=[
            IntegranteDTO(
                id=i.id,
                nombre_diputado=i.nombre_diputado,
                cargo=i.cargo,
                partido=i.partido,
                distrito=i.distrito,
            )
            for i in integrantes
        ],
    )


@router.get("/{comision_id}/reuniones", response_model=list[ReunionDTO])
async def reuniones_de_comision(
    comision_id: UUID,
    session: SessionDep,
    dias: Annotated[int, Query(ge=1, le=180)] = 60,
) -> list[ReunionDTO]:
    hoy = date.today()
    hasta = hoy + timedelta(days=dias)
    stmt = (
        select(ReunionComisionOrm)
        .where(
            ReunionComisionOrm.comision_id == comision_id,
            ReunionComisionOrm.fecha >= hoy,
            ReunionComisionOrm.fecha <= hasta,
        )
        .order_by(ReunionComisionOrm.fecha)
    )
    result = await session.execute(stmt)
    return [
        ReunionDTO(
            id=r.id, fecha=r.fecha, titulo=r.titulo,
            citacion_pdf_url=r.citacion_pdf_url,
        )
        for r in result.scalars().all()
    ]


class ReunionEnriquecidaDTO(BaseModel):
    id: UUID
    fecha: date
    hora: str | None
    sala: str | None
    titulo: str
    descripcion: str | None
    comisiones_invitadas: list[str]
    citacion_pdf_url: str | None
    # Enriquecimiento LLM (None si todavía no se llamó al LLM).
    tema_corto: str | None
    tipo_reunion: str | None
    convocada_por: str | None
    expedientes_citados: list[str]
    oportunidad_politica: str | None
    accion_sugerida: str | None
    huella_historica: str | None
    enriquecida_en: datetime | None


@router.post(
    "/reuniones/{reunion_id}/enriquecer",
    response_model=ReunionEnriquecidaDTO,
)
async def enriquecer_reunion(
    reunion_id: UUID,
    ctx: CurrentContext,
    session: SessionDep,
    llm: LlmProviderDep,
) -> ReunionEnriquecidaDTO:
    """Dispara el LLM contra una reunión: baja el PDF de citación, lo
    analiza junto con el perfil opositor del despacho, y persiste tema +
    oportunidad política + acción sugerida."""
    repo = SqlAlchemyComisionHcdnRepository(session)
    reunion = await repo.buscar_reunion_por_id(reunion_id)
    if reunion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reunión no encontrada",
        )
    # Cargamos la comisión para el contexto del LLM.
    com_stmt = select(ComisionHcdnOrm).where(
        ComisionHcdnOrm.id == reunion.comision_id,
    )
    com_orm = (await session.execute(com_stmt)).scalar_one_or_none()
    if com_orm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comisión de la reunión no encontrada",
        )
    comision = await repo.buscar_por_slug(
        camara=Camara(com_orm.camara), slug=com_orm.slug,
    )
    assert comision is not None

    perfiles = SqlAlchemyPerfilOpositorRepository(session)
    uc = EnriquecerReunionComision(
        llm=llm, perfiles=perfiles, comisiones=repo,
    )
    resultado = await uc.ejecutar(
        despacho_id=ctx.despacho.id,
        reunion=reunion,
        comision=comision,
    )
    ahora = datetime.now(UTC)
    await repo.actualizar_enriquecimiento_reunion(
        reunion_id=reunion_id,
        tema_corto=resultado.tema_corto,
        tipo_reunion=resultado.tipo_reunion,
        convocada_por=resultado.convocada_por,
        expedientes_citados=resultado.expedientes_citados,
        oportunidad_politica=resultado.oportunidad_politica,
        accion_sugerida=resultado.accion_sugerida,
        huella_historica=None,  # feat-61.4.B.4 lo llena después
        enriquecida_en=ahora,
    )
    await session.commit()
    actualizada = await repo.buscar_reunion_por_id(reunion_id)
    assert actualizada is not None
    return _reunion_dto(actualizada)


def _reunion_dto(r: object) -> ReunionEnriquecidaDTO:
    # Cast helper para no repetir 15 líneas en cada endpoint.
    return ReunionEnriquecidaDTO(
        id=r.id,  # type: ignore[attr-defined]
        fecha=r.fecha,  # type: ignore[attr-defined]
        hora=r.hora.strftime("%H:%M") if r.hora else None,  # type: ignore[attr-defined]
        sala=r.sala,  # type: ignore[attr-defined]
        titulo=r.titulo,  # type: ignore[attr-defined]
        descripcion=r.descripcion,  # type: ignore[attr-defined]
        comisiones_invitadas=list(r.comisiones_invitadas or []),  # type: ignore[attr-defined]
        citacion_pdf_url=r.citacion_pdf_url,  # type: ignore[attr-defined]
        tema_corto=r.tema_corto,  # type: ignore[attr-defined]
        tipo_reunion=r.tipo_reunion,  # type: ignore[attr-defined]
        convocada_por=r.convocada_por,  # type: ignore[attr-defined]
        expedientes_citados=list(r.expedientes_citados or []),  # type: ignore[attr-defined]
        oportunidad_politica=r.oportunidad_politica,  # type: ignore[attr-defined]
        accion_sugerida=r.accion_sugerida,  # type: ignore[attr-defined]
        huella_historica=r.huella_historica,  # type: ignore[attr-defined]
        enriquecida_en=r.enriquecida_en,  # type: ignore[attr-defined]
    )


# Silenciar import-no-usado del helper `or_` por si el linter molesta.
_ = or_
