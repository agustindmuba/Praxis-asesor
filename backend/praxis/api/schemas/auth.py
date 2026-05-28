"""Schemas de respuesta de /me."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from praxis.domain import RequestContext, Rol


class _UsuarioDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    nombre: str


class _DespachoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nombre: str


class MeResponse(BaseModel):
    """Devuelto por GET /me. Resumen del contexto autenticado."""

    model_config = ConfigDict(from_attributes=True)

    usuario: _UsuarioDTO
    despacho: _DespachoDTO
    rol: Rol

    @classmethod
    def from_ctx(cls, ctx: RequestContext) -> MeResponse:
        return cls(
            usuario=_UsuarioDTO.model_validate(ctx.usuario),
            despacho=_DespachoDTO.model_validate(ctx.despacho),
            rol=ctx.rol,
        )
