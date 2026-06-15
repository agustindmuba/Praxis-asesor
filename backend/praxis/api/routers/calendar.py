"""Router `/calendar` — feed iCal público del despacho (feat-54.2).

Dos endpoints:

- `GET /calendar/{token}.ics`
  Sin auth Clerk — el token ES la autorización. El cliente del
  calendario (Google / Apple / Outlook) lo refresca periódicamente.
  Devuelve `text/calendar` listo para suscribir.

- `POST /api/v1/calendar/regenerar-token` (tenant-scoped)
  Rota el token actual del despacho. La URL vieja deja de funcionar.
  Usado cuando el asesor sospecha que se filtró.

- `GET /api/v1/calendar/url`
  Devuelve la URL pública del calendario para que el frontend la
  pueda copiar. Si el despacho aún no tiene token, lo genera al vuelo.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, update

from praxis.api.deps import CurrentContext, SessionDep
from praxis.application.use_cases.generar_calendario_despacho import (
    GenerarCalendarioDespacho,
)
from praxis.infrastructure.calendar.ical import generar_ical
from praxis.infrastructure.persistence.models import DespachoOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyEfemerideRepository,
)

log = logging.getLogger(__name__)


# Router público (servido sin /api/v1) — el token va EN la URL.
router_feed = APIRouter(prefix="/calendar", tags=["calendar"])

# Router con auth — gestión del token desde la UI.
router_gestion = APIRouter(prefix="/calendar", tags=["calendar"])


def _generar_token() -> str:
    """32 hex chars = 128 bits — más que suficiente para no-guessable."""
    return secrets.token_hex(16)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CalendarUrlResponse(BaseModel):
    url: str
    token: str


# ---------------------------------------------------------------------------
# Endpoint público (sin auth)
# ---------------------------------------------------------------------------


@router_feed.get("/{token}.ics", response_class=Response)
async def feed_ical(token: str, session: SessionDep) -> Response:
    """Sirve el feed iCal del despacho dueño del token."""
    # Validación rápida del shape — 32 hex chars exactos.
    if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token inválido",
        )

    stmt = select(DespachoOrm).where(DespachoOrm.calendar_token == token)
    result = await session.execute(stmt)
    despacho = result.scalar_one_or_none()
    if despacho is None:
        # No filtramos: respondemos 404 sin pistas del por qué.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendario no encontrado",
        )

    efemerides_repo = SqlAlchemyEfemerideRepository(session)
    uc = GenerarCalendarioDespacho(
        session=session, efemerides=efemerides_repo,
    )
    calendario = await uc.ejecutar(
        despacho_id=despacho.id,
        nombre_despacho=despacho.nombre,
    )
    cuerpo = generar_ical(
        calendario.eventos,
        nombre_calendario=calendario.nombre,
        descripcion_calendario=calendario.descripcion,
    )
    return Response(
        content=cuerpo,
        media_type="text/calendar; charset=utf-8",
        headers={
            # 1h de cache. Los clientes refrescan más seguido si quieren.
            "Cache-Control": "public, max-age=3600",
            # Hint al navegador para descarga si se accede a mano.
            "Content-Disposition": f'inline; filename="praxis-{token[:8]}.ics"',
        },
    )


# ---------------------------------------------------------------------------
# Endpoints de gestión (tenant-scoped)
# ---------------------------------------------------------------------------


@router_gestion.get("/url", response_model=CalendarUrlResponse)
async def obtener_url_calendar(
    request: Request,
    session: SessionDep,
    ctx: CurrentContext,
) -> CalendarUrlResponse:
    """Devuelve la URL pública del feed iCal del despacho.

    Si el despacho aún no tiene token, lo genera y persiste al vuelo.
    Permite que el frontend muestre la URL para copiar al primer load.
    """
    stmt = select(DespachoOrm).where(DespachoOrm.id == ctx.despacho_id)
    result = await session.execute(stmt)
    despacho = result.scalar_one()

    if despacho.calendar_token is None:
        token = _generar_token()
        await session.execute(
            update(DespachoOrm)
            .where(DespachoOrm.id == despacho.id)
            .values(calendar_token=token)
        )
        await session.commit()
    else:
        token = despacho.calendar_token

    base = str(request.base_url).rstrip("/")
    return CalendarUrlResponse(
        url=f"{base}/calendar/{token}.ics",
        token=token,
    )


@router_gestion.post("/regenerar-token", response_model=CalendarUrlResponse)
async def regenerar_token(
    request: Request,
    session: SessionDep,
    ctx: CurrentContext,
) -> CalendarUrlResponse:
    """Rota el token. La URL vieja deja de funcionar inmediatamente."""
    nuevo = _generar_token()
    await session.execute(
        update(DespachoOrm)
        .where(DespachoOrm.id == ctx.despacho_id)
        .values(calendar_token=nuevo)
    )
    await session.commit()

    base = str(request.base_url).rstrip("/")
    return CalendarUrlResponse(
        url=f"{base}/calendar/{nuevo}.ics",
        token=nuevo,
    )
