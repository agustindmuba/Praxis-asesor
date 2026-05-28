"""Adapter de auth contra Clerk: verifica JWTs con su JWKS público.

Diseño (ver spec 09 §"Cache de JWKS"):
- Descarga el JWKS al primer uso y lo cachea con TTL (default 1h).
- Si llega un `kid` desconocido, refresca el JWKS y reintenta una sola vez
  (evita bucle infinito si el `kid` realmente no existe).
- Lock `asyncio.Lock` para que múltiples requests concurrentes no disparen
  fetches simultáneos del JWKS.
- Sin acoplamiento a Clerk en la API: el constructor toma `issuer` y
  `jwks_url`. Funciona con cualquier IdP que sirva JWKS y firme con RS256.

PyJWT (`pyjwt[crypto]`) hace el heavy lifting de verificar firma + claims;
nosotros solo orquestamos el fetch del JWKS y mapeamos excepciones al
`AuthError` del dominio.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from praxis.application.ports import AuthProvider
from praxis.domain import AuthClaims, AuthError, AuthErrorCode


class ClerkAuthProvider(AuthProvider):
    """Verifica tokens Clerk (o cualquier IdP con JWKS / RS256).

    Args:
        issuer: el valor esperado del claim `iss` (ej. tu Clerk frontend API URL).
        jwks_url: URL del endpoint JWKS (`.well-known/jwks.json`).
        audience: si Clerk lo configura, el `aud` esperado. None desactiva la check.
        http_client: cliente httpx para fetch del JWKS. Inyectable para tests.
        jwks_ttl: TTL del cache de JWKS. Default 1h.
        clock: callable que devuelve `datetime` UTC actual. Inyectable para tests.
    """

    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: str,
        audience: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        jwks_ttl: timedelta = timedelta(hours=1),
        clock: Any = None,
    ) -> None:
        self._issuer = issuer
        self._jwks_url = jwks_url
        self._audience = audience
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._ttl = jwks_ttl
        self._clock = clock or (lambda: datetime.now(UTC))

        # Cache + lock.
        self._keys: dict[str, Any] = {}
        self._last_refresh: datetime | None = None
        self._lock = asyncio.Lock()

    # -----------------------------------------------------------------------
    # API pública del puerto
    # -----------------------------------------------------------------------

    async def verificar_token(self, token: str) -> AuthClaims:
        """Verifica firma + claims y devuelve `AuthClaims`.

        Pasos:
        1. Lee el `kid` del header sin verificar (PyJWT permite esto).
        2. Obtiene la public key correspondiente (cache + refresh on-demand).
        3. `jwt.decode` con la clave pública valida firma + iss + aud + exp.
        4. Mapea cualquier excepción de PyJWT a `AuthError` con `code` específico.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.DecodeError as exc:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, str(exc)) from exc

        kid = header.get("kid")
        if not kid:
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "JWT sin claim 'kid' en header")

        public_key = await self._get_key(kid)

        # `jwt.decode` chequea: firma (con la clave), `exp` (siempre, si está),
        # `iss` (si pasamos `issuer`), `aud` (si pasamos `audience`).
        decode_kwargs: dict[str, Any] = {
            "key": public_key,
            "algorithms": ["RS256"],
            "issuer": self._issuer,
            # leeway: pequeño margen para clock skew entre nuestro server y Clerk.
            "leeway": timedelta(seconds=30),
        }
        if self._audience is not None:
            decode_kwargs["audience"] = self._audience

        try:
            claims = jwt.decode(token, **decode_kwargs)
        except jwt.ExpiredSignatureError as exc:
            raise AuthError(AuthErrorCode.TOKEN_EXPIRED, str(exc)) from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthError(AuthErrorCode.WRONG_ISSUER, str(exc)) from exc
        except jwt.InvalidTokenError as exc:
            # cubre firma inválida, aud incorrecto, formato malformado, etc.
            raise AuthError(AuthErrorCode.INVALID_TOKEN, str(exc)) from exc

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise AuthError(AuthErrorCode.INVALID_TOKEN, "JWT sin claim 'sub'")

        return AuthClaims(
            sub=sub,
            email=_str_or_none(claims.get("email")),
            nombre=_extract_nombre(claims),
        )

    # -----------------------------------------------------------------------
    # JWKS cache
    # -----------------------------------------------------------------------

    async def _get_key(self, kid: str) -> Any:
        """Devuelve la clave pública asociada a `kid`. Refresca el JWKS si hace
        falta. Lanza AuthError(INVALID_TOKEN) si el kid no existe ni después
        de refrescar.
        """
        key = self._keys.get(kid)
        if key is not None and not self._cache_expired():
            return key

        # Cache stale o miss. Refresh bajo lock para no disparar N fetches.
        async with self._lock:
            # Double-check después de tomar el lock (otro coro pudo haberlo refrescado).
            key = self._keys.get(kid)
            if key is not None and not self._cache_expired():
                return key
            await self._refresh_jwks()

        key = self._keys.get(kid)
        if key is None:
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN,
                f"kid '{kid}' no encontrado en JWKS",
            )
        return key

    def _cache_expired(self) -> bool:
        if self._last_refresh is None:
            return True
        return (self._clock() - self._last_refresh) > self._ttl

    async def _refresh_jwks(self) -> None:
        """Baja el JWKS y popula el dict `kid → public_key`."""
        try:
            response = await self._http.get(self._jwks_url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN,
                f"no se pudo descargar JWKS: {exc}",
            ) from exc

        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise AuthError(
                AuthErrorCode.INVALID_TOKEN,
                "JWKS sin campo 'keys' válido",
            )

        nuevo: dict[str, Any] = {}
        for jwk in keys:
            if not isinstance(jwk, dict):
                continue
            kid = jwk.get("kid")
            if not isinstance(kid, str):
                continue
            try:
                # RSAAlgorithm.from_jwk acepta dict o JSON-string; le pasamos dict
                # con seguridad (la firma de tipos de PyJWT toma str | dict).
                public_key = RSAAlgorithm.from_jwk(jwk)
            except (ValueError, KeyError):
                # Una clave malformada no debe tirar todo el JWKS.
                continue
            nuevo[kid] = public_key

        self._keys = nuevo
        self._last_refresh = self._clock()


# -----------------------------------------------------------------------
# Helpers de claims
# -----------------------------------------------------------------------


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _extract_nombre(claims: dict[str, Any]) -> str | None:
    """Clerk puede mandar `name`, o `first_name`+`last_name`, o nada.

    Devolvemos el primer match útil. Si no hay nada, None.
    """
    if (name := _str_or_none(claims.get("name"))) is not None:
        return name
    first = _str_or_none(claims.get("first_name"))
    last = _str_or_none(claims.get("last_name"))
    if first and last:
        return f"{first} {last}"
    return first or last
