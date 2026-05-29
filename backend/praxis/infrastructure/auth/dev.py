"""DevAuthProvider — auth fake para desarrollo local SIN Clerk.

Pensado SOLO para que un desarrollador pueda probar la UI sin tener que
configurar una app real de Clerk. Acepta un token con formato `dev:<sub>`
y devuelve `AuthClaims` con ese `sub`, sin verificar ninguna firma.

Activación: este adapter se monta sólo cuando `Settings.env == "dev"` y
`Settings.clerk_issuer` está vacío. En producción NUNCA se carga.

Seguridad:
- En prod (`ENV=prod`), `praxis.api.deps.get_auth_provider` levanta error
  si alguien intenta usar este provider.
- No hay verificación criptográfica. Cualquiera con acceso al backend
  puede pretender ser cualquier usuario. POR ESO solo dev.

Ejemplo de token aceptado: `dev:user_agustin` → `AuthClaims(sub="user_agustin")`.
"""

from __future__ import annotations

from praxis.application.ports import AuthProvider
from praxis.domain import AuthClaims, AuthError, AuthErrorCode

DEV_TOKEN_PREFIX = "dev:"


class DevAuthProvider(AuthProvider):
    """Provider sin verificación, solo para desarrollo local."""

    async def verificar_token(self, token: str) -> AuthClaims:
        if not token.startswith(DEV_TOKEN_PREFIX):
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN,
                "DevAuthProvider espera token con prefijo 'dev:'",
            )
        sub = token[len(DEV_TOKEN_PREFIX) :].strip()
        if not sub:
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN,
                "DevAuthProvider: token sin sub",
            )
        # Devolvemos claims mínimos. Email/nombre quedan en None; el sistema
        # los toma del Usuario seedeado en DB (ese es el sourcemaster en dev).
        return AuthClaims(sub=sub)
