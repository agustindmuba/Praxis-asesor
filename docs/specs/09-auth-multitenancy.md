# Spec 09 — Auth + multi-tenancy

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/14-auth-clerk`

## Contexto

Hasta ahora la capa de persistencia ya está tenant-aware (`despacho_id`
explícito en cada query crítica), pero no hay nadie que sepa **qué usuario**
hace cada request ni **qué despacho** tiene activo.

Esta feature mete la pieza de identificación: dado un request HTTP, resolver
`(usuario, despacho, rol)` y bloquear si algo no cuadra.

## Decisiones (chat 2026-05-28)

1. **Provider**: Clerk como IdP. Estable, soporta SSO, planes generosos
   para arrancar, frontend listo.
2. **Verificación de token**: JWKS público de Clerk con cache TTL.
   Verificamos firma + iss + exp localmente. Sin roundtrip a Clerk por request.
3. **Tenant resolution**: el frontend manda `X-Despacho-Id` con el UUID del
   despacho activo. El middleware valida membresía contra
   `MembresiaDespachoRepository`.
4. **Librería JWT**: `pyjwt[crypto]`.

## Componentes

```
┌──────────────────┐      verifica firma + claims
│ AuthProvider     │──────────────────────────────►  AuthClaims
│ (puerto)         │                                 (sub, email, ...)
└──────────────────┘
        ▲
        │ implementa
┌──────────────────┐
│ ClerkAuthProvider│  ◄── JWKS cache TTL ~1h
└──────────────────┘

┌────────────────────────────┐
│ ResolverContextoRequest    │  caso de uso:
│ (token, despacho_id_header)│  1. verifica token → AuthClaims
│                            │  2. busca/crea Usuario (auth_provider_id)
│                            │  3. valida MembresiaDespacho(usuario, despacho)
└────────────┬───────────────┘  → RequestContext(usuario, despacho, rol)
             │
             ▼
   ┌────────────────────────┐
   │ FastAPI dep            │  HTTPException 401/403 según corresponda
   │ current_context()      │
   └────────────────────────┘
```

## Value objects (domain)

```python
@dataclass(frozen=True, slots=True)
class AuthClaims:
    sub: str                    # auth_provider_id de Clerk
    email: str | None = None
    nombre: str | None = None

@dataclass(frozen=True, slots=True)
class RequestContext:
    usuario: Usuario
    despacho: Despacho
    rol: Rol
```

Ambos viven en `praxis.domain.auth` (módulo nuevo).

## Puerto

```python
class AuthProvider(ABC):
    @abstractmethod
    async def verificar_token(self, token: str) -> AuthClaims:
        """Verifica firma + claims (iss, exp, aud) y devuelve los claims útiles.

        Raises:
            AuthError: si el token es inválido, expirado o el issuer no matchea.
        """
```

## Caso de uso

```python
class ResolverContextoRequest:
    def __init__(self, auth, usuario_repo, despacho_repo, membresia_repo): ...
    async def execute(self, token: str, despacho_id: UUID) -> RequestContext:
        # 1. verifica token con AuthProvider
        # 2. lookup Usuario por auth_provider_id; si no existe, AuthError
        # 3. lookup Despacho por id; si no existe, AuthError
        # 4. lookup Membresia (usuario_id, despacho_id) activa; si no, AuthError
        # 5. devuelve RequestContext
```

Diseño: **no crea usuario on-the-fly**. El sync de usuarios viene por webhook
de Clerk en otra feature (o por endpoint admin manual). Esto mantiene la
auth pura y previene auto-creación silenciosa.

## Excepciones

`AuthError(DomainError)` con subtipos discriminados por `code`:
- `INVALID_TOKEN` (firma, formato, decode falla)
- `TOKEN_EXPIRED`
- `WRONG_ISSUER`
- `USER_NOT_PROVISIONED` (token válido pero el usuario no está en nuestra DB)
- `DESPACHO_NOT_FOUND`
- `NOT_A_MEMBER` (el usuario no tiene membresía activa en ese despacho)

Cada subtipo se mapea a un HTTP status code distinto en el adapter FastAPI:
- 401 para token problems (inválido/expirado/issuer/no provisionado)
- 403 para despacho problems (no es miembro)
- 404 para despacho inexistente — opinión: 403 también, no leakeamos
  existencia de despachos a usuarios no autorizados.

## Cache de JWKS

`ClerkAuthProvider` mantiene un dict `kid → public_key` en memoria con
timestamp de last refresh. Si llega un kid no conocido, hace fetch + actualiza.
TTL hard: 1h (refresh proactivo si el JWT viene con kid conocido pero el
último refresh fue hace >1h).

Concurrencia: lock asyncio para que múltiples requests no disparen N fetches
simultáneos del JWKS.

## Config

Variables nuevas en `praxis.config.Settings`:

```python
clerk_issuer: str  # ej. https://clerk.tu-app.com
clerk_jwks_url: str  # ej. https://clerk.tu-app.com/.well-known/jwks.json
clerk_audience: str | None = None  # opcional, depende de cómo configuren Clerk
```

En tests, `clerk_issuer="https://test.clerk.dev"` y JWKS in-memory generado
con `cryptography`.

## FastAPI dep

```python
async def current_context(
    request: Request,
    # extraídos de headers
) -> RequestContext: ...
```

Extrae:
- `Authorization: Bearer <token>` (si falta → 401)
- `X-Despacho-Id: <uuid>` (si falta o no parsea → 400)

Luego llama al caso de uso y devuelve el `RequestContext`. Cualquier endpoint
protegido pone `ctx: RequestContext = Depends(current_context)` y obtiene
las 3 entidades resueltas y verificadas.

## Tests

- Unit del adapter Clerk: generamos pares RSA con `cryptography`, firmamos
  un JWT con kid="test-key-1", publicamos el JWKS como dict in-memory.
  Verificamos: token válido, token expirado, firma rota, kid desconocido,
  issuer incorrecto.
- Unit del caso de uso: con `AuthProvider` mockeado, recorremos las 5
  ramas de error + caso happy.
- Integración del dep FastAPI: app de prueba con un endpoint protegido,
  hits con headers correctos e incorrectos.

## Out of scope (feat futuras)

- Webhook de Clerk para crear/actualizar usuarios on signup.
- Roles fine-grained (autz por endpoint según `Rol`). Se construye encima
  de `RequestContext.rol`.
- Refresh tokens / silent refresh — eso lo maneja Clerk en el cliente.
- Sesiones server-side.
