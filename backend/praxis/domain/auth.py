"""Value objects de autenticación + contexto de request.

Ver `docs/specs/09-auth-multitenancy.md` para el flujo completo.

Estos viven en `domain/` porque son contratos del modelo (qué información
necesita el sistema para identificar al usuario y su tenant). El adapter
que verifica el JWT vive en `infrastructure/auth/clerk.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from praxis.domain.despacho import Despacho
from praxis.domain.exceptions import DomainError
from praxis.domain.usuario import Rol, Usuario


@dataclass(frozen=True, slots=True)
class AuthClaims:
    """Claims útiles extraídos de un JWT ya verificado.

    `sub` es el id del usuario en el provider externo (Clerk's user_id).
    Nuestro lookup contra `UsuarioRepository.buscar_por_auth_provider_id`
    usa este valor.
    """

    sub: str
    email: str | None = None
    nombre: str | None = None

    def __post_init__(self) -> None:
        if not self.sub.strip():
            raise ValueError("AuthClaims.sub no puede ser vacío")


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Contexto resuelto de un request autenticado.

    Una vez construido, todas las capas de aplicación pueden confiar en que:
    - El `usuario` está autenticado contra el provider externo.
    - El `despacho` existe.
    - El `rol` viene de una `MembresiaDespacho` activa entre ambos.

    Construirlo es responsabilidad de `ResolverContextoRequest` (caso de uso).
    Los endpoints lo reciben ya armado por DI.
    """

    usuario: Usuario
    despacho: Despacho
    rol: Rol


class AuthErrorCode(StrEnum):
    """Códigos discretos de error de autenticación.

    Permiten al adapter FastAPI mapear cada subtipo a un HTTP status code
    sin necesidad de hacer isinstance contra subtipos de Exception.
    """

    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    WRONG_ISSUER = "wrong_issuer"
    USER_NOT_PROVISIONED = "user_not_provisioned"
    DESPACHO_NOT_FOUND = "despacho_not_found"
    NOT_A_MEMBER = "not_a_member"


class AuthError(DomainError):
    """Falla del flujo de autenticación/autorización.

    Lleva un `code` (de `AuthErrorCode`) que el adapter HTTP usa para
    elegir el status code de la respuesta. Ver
    `docs/specs/09-auth-multitenancy.md` §"Excepciones".
    """

    def __init__(self, code: AuthErrorCode, detalle: str | None = None) -> None:
        msg = code.value
        if detalle:
            msg = f"{msg}: {detalle}"
        super().__init__(msg)
        self.code = code
        self.detalle = detalle
