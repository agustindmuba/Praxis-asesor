# Spec 11 — Webhook de Clerk

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/16-webhook-clerk`

## Contexto

Hoy el caso de uso `ResolverContextoRequest` (feat/14) requiere que el
`Usuario` ya exista en nuestra DB con `auth_provider_id` poblado. Si no
existe, devuelve `USER_NOT_PROVISIONED` → 401. Sin un mecanismo de
provisioning, cada usuario hay que crearlo a mano por SQL.

El flujo "el usuario se registra en Clerk → aparece en nuestra DB → puede
entrar" se cierra acá: Clerk dispara un webhook a nuestro endpoint cuando
hay cambios, y nosotros sincronizamos.

## Decisiones (chat 2026-05-28)

1. **Verificación de firma**: librería `svix` oficial. Verifica
   `svix-id`, `svix-timestamp`, `svix-signature` con el secret del webhook.
2. **Eventos procesados**:
   - `user.created` → crea `Usuario` en nuestra DB (sin asignar despacho;
     ese paso es admin manual o futuro endpoint de invitación).
   - `user.updated` → sync de `email`, `nombre`.
   - `user.deleted` → marca `activo=False` (no borra físicamente — preservamos
     historial de seguimientos).
   - `session.created` → log estructurado para telemetría, no-op en DB.
3. **Idempotencia**: si llega `user.created` para un `clerk_user_id` que ya
   existe, no es error — lo tratamos como `updated`.

## Endpoint

`POST /api/v1/webhooks/clerk`

- **No** lleva `Depends(current_context)` — el webhook viene del servidor de
  Clerk, no de un usuario logueado.
- Headers requeridos: `svix-id`, `svix-timestamp`, `svix-signature`.
- Body: JSON con `{type: str, data: object, ...}`.
- Response: 200 OK con `{"status": "processed"|"ignored"}`.

### Errores

- 400 si faltan headers Svix o el body no es JSON válido.
- 401 si la firma no verifica (Svix lanza `WebhookVerificationError`).
- 200 con `"ignored"` si el `type` no está en nuestra lista (vs 4xx — Clerk
  reintenta si no es 2xx, y no queremos que reintente eventos que ignoramos).

## Config

Nueva variable en `Settings`:

```python
clerk_webhook_secret: str | None = None
```

Si no está seteada, el endpoint devuelve 503 (no podemos verificar).

## Estructura del código

```
backend/praxis/
├── application/
│   └── use_cases/
│       └── sincronizar_usuario_clerk.py    # NEW
├── infrastructure/
│   └── auth/
│       └── webhook_verify.py                # NEW: wrapper svix
└── api/
    └── routers/
        └── webhooks.py                      # NEW: POST /webhooks/clerk
```

### `UsuarioRepository.actualizar(usuario) -> Usuario`

Necesario para `user.updated` y `user.deleted`. Agrego al puerto + implementación
SQL. Update por `id` (no por email — el email puede cambiar).

### Caso de uso

```python
class SincronizarUsuarioDesdeClerk:
    async def execute(self, *, evento_tipo: str, data: dict) -> str:
        # Devuelve "processed" | "ignored".
        match evento_tipo:
            case "user.created" | "user.updated": ...
            case "user.deleted": ...
            case _: return "ignored"
```

El parseo de `data` (Clerk manda `email_addresses: [{email_address, primary}]`,
`first_name`, `last_name`, `id`) vive dentro del caso de uso. Funciones puras
de extracción para que sean fáciles de testear sin armar el payload completo.

## Out of scope

- Auto-asignación a un despacho. El sysadmin debe crear `MembresiaDespacho`
  manualmente (o futura UI de invitación con tokens).
- Webhook events de organizations / memberships de Clerk — si llegamos a
  modelar tenants en Clerk también, hablamos de eso aparte.
- Replay protection más fuerte que la TTL de svix (5 min default).

## Tests

- Unit del caso de uso: payloads sintéticos por tipo, fakes del repo,
  verifica que crea/actualiza/desactiva correctamente.
- Unit del extractor de campos (`email_addresses` primary picking).
- Integración del router: TestClient + payload firmado con un secret de
  prueba. Verifica firma válida → 200, inválida → 401, faltan headers → 400,
  evento desconocido → 200 ignored.
