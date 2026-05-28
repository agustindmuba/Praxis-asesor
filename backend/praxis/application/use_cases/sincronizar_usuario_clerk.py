"""Caso de uso: sincronizar Usuario desde un evento de webhook de Clerk.

Se invoca desde el router POST /webhooks/clerk después de que la firma
Svix esté verificada. Recibe el tipo de evento + el payload `data` que
manda Clerk.

Ver `docs/specs/11-webhook-clerk.md`.

Eventos manejados:
- `user.created` → crea (o updatea si ya existe — idempotente).
- `user.updated` → updatea email/nombre/activo.
- `user.deleted` → marca `activo=False`.
- `session.created` → log estructurado, no-op en DB.
- cualquier otro → "ignored" sin error.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog

from praxis.application.ports import UsuarioRepository
from praxis.domain import Usuario

log = structlog.get_logger()


class SincronizarUsuarioDesdeClerk:
    """Aplica un evento de Clerk al estado de nuestro `Usuario`."""

    def __init__(self, usuarios: UsuarioRepository) -> None:
        self._usuarios = usuarios

    async def execute(self, *, evento_tipo: str, data: dict[str, Any]) -> str:
        """Procesa el evento. Devuelve `"processed"` o `"ignored"`.

        No lanza excepciones para eventos desconocidos — devolver "ignored"
        evita que Clerk reintente (que sucede si respondemos !2xx).
        """
        match evento_tipo:
            case "user.created" | "user.updated":
                await self._upsert(data)
                return "processed"
            case "user.deleted":
                await self._desactivar(data)
                return "processed"
            case "session.created":
                # Telemetría solamente — qué usuario se logueó.
                log.info(
                    "clerk.session_created",
                    user_id=data.get("user_id"),
                    session_id=data.get("id"),
                )
                return "processed"
            case _:
                log.info("clerk.event_ignored", tipo=evento_tipo)
                return "ignored"

    async def _upsert(self, data: dict[str, Any]) -> None:
        """Idempotente: crea si no existe, actualiza si existe."""
        clerk_id = _extract_clerk_id(data)
        email = _extract_email(data)
        nombre = _extract_nombre(data)

        existente = await self._usuarios.buscar_por_auth_provider_id(clerk_id)
        if existente is None:
            # No existe: lo creamos. Mantenemos el flujo de auto-asignación
            # FUERA de acá — sólo provisiona el Usuario; el sysadmin asigna
            # despacho/rol después (o futura UI de invitación).
            nuevo = Usuario(
                id=uuid4(),
                email=email,
                nombre=nombre,
                auth_provider_id=clerk_id,
                activo=True,
            )
            await self._usuarios.crear(nuevo)
            log.info("clerk.user_provisioned", clerk_id=clerk_id, email=email)
        else:
            # Existe: sync de email/nombre. Preserva `activo` (no lo
            # reactivamos automáticamente si estaba en False — eso es decisión
            # del sysadmin).
            actualizado = Usuario(
                id=existente.id,
                email=email,
                nombre=nombre,
                auth_provider_id=clerk_id,
                activo=existente.activo,
            )
            await self._usuarios.actualizar(actualizado)
            log.info("clerk.user_synced", clerk_id=clerk_id, email=email)

    async def _desactivar(self, data: dict[str, Any]) -> None:
        """Marca al usuario como activo=False. No borra físicamente."""
        clerk_id = _extract_clerk_id(data)
        existente = await self._usuarios.buscar_por_auth_provider_id(clerk_id)
        if existente is None:
            # No tenemos al usuario: nada que desactivar. No es error.
            log.info("clerk.user_delete_unknown", clerk_id=clerk_id)
            return
        actualizado = Usuario(
            id=existente.id,
            email=existente.email,
            nombre=existente.nombre,
            auth_provider_id=existente.auth_provider_id,
            activo=False,
        )
        await self._usuarios.actualizar(actualizado)
        log.info("clerk.user_deactivated", clerk_id=clerk_id)


# ---------------------------------------------------------------------------
# Extractores puros (testeables sin mocks).
# ---------------------------------------------------------------------------


def _extract_clerk_id(data: dict[str, Any]) -> str:
    """El id del usuario en Clerk."""
    clerk_id = data.get("id")
    if not isinstance(clerk_id, str) or not clerk_id.strip():
        raise ValueError("payload Clerk sin 'id' válido")
    return clerk_id


def _extract_email(data: dict[str, Any]) -> str:
    """Clerk manda email_addresses como lista con un primary_email_address_id.

    Estructura:
    ```json
    {
      "email_addresses": [
        {"id": "ea_1", "email_address": "a@b.com"},
        {"id": "ea_2", "email_address": "x@y.com"}
      ],
      "primary_email_address_id": "ea_1"
    }
    ```

    Si no hay primary o no matchea, tomamos el primero. Si no hay ninguno,
    lanza ValueError — no podemos crear usuario sin email.
    """
    addresses = data.get("email_addresses")
    if not isinstance(addresses, list) or not addresses:
        raise ValueError("payload Clerk sin email_addresses")

    primary_id = data.get("primary_email_address_id")
    chosen: dict[str, Any] | None = None
    if isinstance(primary_id, str):
        for addr in addresses:
            if isinstance(addr, dict) and addr.get("id") == primary_id:
                chosen = addr
                break
    if chosen is None:
        chosen = addresses[0] if isinstance(addresses[0], dict) else None
    if chosen is None:
        raise ValueError("payload Clerk con email_addresses malformado")

    email = chosen.get("email_address")
    if not isinstance(email, str) or "@" not in email:
        raise ValueError(f"email inválido en payload Clerk: {email!r}")
    return email


def _extract_nombre(data: dict[str, Any]) -> str:
    """Clerk manda first_name y last_name (cualquiera puede ser None)."""
    first = data.get("first_name")
    last = data.get("last_name")
    parts = [p for p in (first, last) if isinstance(p, str) and p.strip()]
    if parts:
        return " ".join(p.strip() for p in parts)
    # Fallback: username si está, sino el email (sin @).
    username = data.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()
    try:
        email = _extract_email(data)
    except ValueError:
        return "(sin nombre)"
    return email.split("@")[0]
