"""Router REST /legislador-titular (feat-46).

- GET   /legislador-titular/huella : panel con identidad + distribuciones.
- PATCH /legislador-titular/foto   : setea/borra la foto del legislador.

El legislador titular se identifica por `despacho.legislador_titular_slug`.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from praxis.api.deps import CurrentContext, SessionDep
from praxis.api.schemas.huella_legislador import (
    ActualizarFotoLegislador,
    CategoriaConPctDTO,
    HuellaLegisladorDTO,
)
from praxis.application.use_cases.calcular_huella_legislador import (
    CalcularHuellaLegisladorTitular,
)
from praxis.infrastructure.persistence.models import DespachoOrm

router = APIRouter(prefix="/legislador-titular", tags=["legislador-titular"])


@router.get(
    "/huella",
    response_model=HuellaLegisladorDTO,
    summary=(
        "Huella parlamentaria del legislador titular del despacho: "
        "identidad + distribución por estado (con %), tipo y área."
    ),
)
async def get_huella(
    ctx: CurrentContext, session: SessionDep,
) -> HuellaLegisladorDTO:
    uc = CalcularHuellaLegisladorTitular(session=session)
    huella = await uc.ejecutar(
        despacho_id=ctx.despacho.id,
        slug=ctx.despacho.legislador_titular_slug,
        foto_url=ctx.despacho.legislador_foto_url,
    )
    return HuellaLegisladorDTO(
        nombre=huella.nombre,
        slug=huella.slug,
        bloque_dominante=huella.bloque_dominante,
        distrito_dominante=huella.distrito_dominante,
        foto_url=huella.foto_url,
        total_firmados=huella.total_firmados,
        por_estado=[CategoriaConPctDTO(key=c.key, total=c.total, pct=c.pct) for c in huella.por_estado],
        por_tipo=[CategoriaConPctDTO(key=c.key, total=c.total, pct=c.pct) for c in huella.por_tipo],
        por_area=[CategoriaConPctDTO(key=c.key, total=c.total, pct=c.pct) for c in huella.por_area],
    )


@router.patch(
    "/foto",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Setea o borra la URL pública de la foto del legislador titular.",
)
async def set_foto(
    body: ActualizarFotoLegislador,
    ctx: CurrentContext,
    session: SessionDep,
) -> None:
    """Actualiza `despacho.legislador_foto_url` con la URL provista
    (o NULL para borrarla)."""
    stmt = select(DespachoOrm).where(DespachoOrm.id == ctx.despacho.id)
    orm = (await session.execute(stmt)).scalar_one()
    orm.legislador_foto_url = body.foto_url
    await session.commit()
