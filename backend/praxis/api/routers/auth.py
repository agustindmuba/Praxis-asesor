"""Router /me — devuelve el contexto autenticado del request actual."""

from __future__ import annotations

from fastapi import APIRouter

from praxis.api.deps import CurrentContext
from praxis.api.schemas import MeResponse

router = APIRouter(tags=["auth"])


@router.get("/me", summary="Contexto del request autenticado", response_model=MeResponse)
async def me(ctx: CurrentContext) -> MeResponse:
    """Devuelve el usuario + despacho activo + rol del request.

    Útil para que el frontend muestre quién está logueado, qué despacho
    tiene activo, y qué acciones habilitar según el rol.
    """
    return MeResponse.from_ctx(ctx)
