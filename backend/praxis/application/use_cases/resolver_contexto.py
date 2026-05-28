"""Caso de uso: resolver el contexto autenticado de un request.

Toma `(token, despacho_id)` y devuelve `RequestContext` o lanza `AuthError`.

Ver `docs/specs/09-auth-multitenancy.md`.
"""

from __future__ import annotations

from uuid import UUID

from praxis.application.ports import (
    AuthProvider,
    DespachoRepository,
    MembresiaDespachoRepository,
    UsuarioRepository,
)
from praxis.domain import AuthError, AuthErrorCode, RequestContext


class ResolverContextoRequest:
    """Caso de uso de identificación.

    Pasos:
    1. Verifica el token con `AuthProvider` (firma + iss + exp) → `AuthClaims`.
    2. Busca el `Usuario` por `auth_provider_id`. Si no existe, USER_NOT_PROVISIONED.
       (No autocreamos — el sync viene por webhook en otra feature.)
    3. Busca el `Despacho` por id. Si no existe, NOT_A_MEMBER.
       (Devolvemos NOT_A_MEMBER en lugar de DESPACHO_NOT_FOUND para no leakear
       a un usuario no autorizado la existencia de despachos.)
    4. Busca la `MembresiaDespacho` activa entre ambos. Si no hay o está inactiva,
       NOT_A_MEMBER.
    5. Devuelve `RequestContext(usuario, despacho, rol)`.
    """

    def __init__(
        self,
        *,
        auth: AuthProvider,
        usuarios: UsuarioRepository,
        despachos: DespachoRepository,
        membresias: MembresiaDespachoRepository,
    ) -> None:
        self._auth = auth
        self._usuarios = usuarios
        self._despachos = despachos
        self._membresias = membresias

    async def execute(self, *, token: str, despacho_id: UUID) -> RequestContext:
        # 1. Verifica el token — propaga AuthError (INVALID_TOKEN, TOKEN_EXPIRED,
        # WRONG_ISSUER) del AuthProvider tal cual.
        claims = await self._auth.verificar_token(token)

        # 2. Usuario provisionado en nuestra DB?
        usuario = await self._usuarios.buscar_por_auth_provider_id(claims.sub)
        if usuario is None:
            raise AuthError(AuthErrorCode.USER_NOT_PROVISIONED, claims.sub)
        if not usuario.activo:
            raise AuthError(AuthErrorCode.USER_NOT_PROVISIONED, "usuario inactivo")

        # 3 + 4. Despacho + membresía. Combinamos en NOT_A_MEMBER para no
        # leakear info sobre despachos a usuarios externos.
        despacho = await self._despachos.buscar_por_id(despacho_id)
        if despacho is None:
            raise AuthError(AuthErrorCode.NOT_A_MEMBER, str(despacho_id))

        membresia = await self._membresias.buscar(usuario_id=usuario.id, despacho_id=despacho_id)
        if membresia is None or not membresia.activo:
            raise AuthError(AuthErrorCode.NOT_A_MEMBER, str(despacho_id))

        # 5. Listo: contexto completo.
        return RequestContext(usuario=usuario, despacho=despacho, rol=membresia.rol)
