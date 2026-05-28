# Spec 12 — Frontend MVP UI

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/17-frontend-planning`

Stack y arquitectura: ver [ADR 0004](../adr/0004-stack-frontend.md).

## Objetivo

Que un asesor parlamentario pueda, después de loguearse, **encontrar un
expediente y empezar a seguirlo**. Eso cierra el loop "alguien usa la
herramienta para resolver una tarea real".

Si la primera pantalla que ve no le sirve para esa tarea en menos de 60
segundos, falló.

## Alcance (4 rutas)

```
/sign-in           Clerk SignIn embebido
/sign-up           Clerk SignUp embebido
/dashboard         Resumen del asesor: seguimientos activos
/expedientes       Tabla con filtros (texto, año, tipo, cámara, comisión)
/expedientes/[id]  Ficha completa + acciones
```

(También `/sign-out` que solo redirige a Clerk.)

## Pantallas en detalle

### `/sign-in` y `/sign-up`

- Componentes `<SignIn />` y `<SignUp />` de `@clerk/nextjs`.
- Layout minimalista: logo "Praxis Asesor", el form, y un footer con
  "¿Problemas? contactanos".
- Post-signin redirect a `/dashboard`.

### `/dashboard` — Hub del asesor

Lo primero que ve después de loguearse. Tiene que responder *"¿qué pasó
mientras no estaba?"*.

**Layout:**

```
┌─────────────────────────────────────────────────────────┐
│ [≡ Sidebar]    Topbar: [⌕ Buscar...] [Despacho ▼] [Avatar]
├─────────────────────────────────────────────────────────┤
│              │                                          │
│ • Dashboard  │  Hola, Ana 👋                            │
│ • Expedientes│                                          │
│ • Seguim.    │  ┌─ Mis seguimientos ────────────────┐  │
│ • Notas      │  │ 12 activos · 3 sin asignar       │  │
│              │  │                                    │  │
│              │  │ [▼ Prioridad Alta (3)]             │  │
│              │  │   1497-D-2024 · Reforma Salud      │  │
│              │  │     EN COMISION · vence 2026-04-30 │  │
│              │  │   100-D-2024 · Presupuesto         │  │
│              │  │     CON DICTAMEN · vence 2025-12-01│  │
│              │  │   ...                              │  │
│              │  └────────────────────────────────────┘  │
│              │                                          │
│              │  ┌─ Actividad reciente ───────────────┐  │
│              │  │ (placeholder por ahora)            │  │
│              │  └────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Componentes:**
- **Sidebar**: nav vertical. Item activo destacado. Colapsa en mobile.
- **Topbar**: buscador global (`Cmd+K`), selector de despacho si hay >1, avatar con dropdown (perfil, sign-out).
- **Card "Mis seguimientos"**: agrupados por prioridad (Alta/Media/Baja).
  Cada item: número expediente, título truncado a 1 línea, badge de estado, fecha caducidad si corresponde. Click → ficha.
- **Card "Actividad reciente"**: placeholder en MVP. En v2 mostrará nuevos eventos en trámite de los seguidos.

**Data:**
- RSC server-side fetch a `GET /api/v1/seguimientos` (cuando exista) o
  fallback: `GET /api/v1/expedientes` con filtro implícito.
  > Nota: el backend hoy no tiene endpoint "listar seguimientos del despacho activo".
  > Lo agregamos antes de implementar el dashboard, o usamos el repo
  > `listar_por_despacho` exponiéndolo con un nuevo endpoint
  > `GET /api/v1/seguimientos`.

### `/expedientes` — Búsqueda y filtros

La tabla principal del producto.

**Layout:**

```
┌─ Filtros ────────────────────────────────────────────┐
│ [Buscar texto... ] [Año ▼] [Tipo ▼] [Cámara ▼]      │
│ [Autor ▼] [Comisión ▼] [Estado ▼]    [Limpiar]      │
└──────────────────────────────────────────────────────┘

Mostrando 1–50 de 234

┌────────────────────────────────────────────────────┐
│ Nº ↑       │ Título            │ Estado     │ Acc.│
├────────────────────────────────────────────────────┤
│ 1497-D-24  │ Reforma Salud...  │ EN COM.    │ ★   │
│ 1500-D-24  │ Presupuesto...    │ CON DICT.  │ ☆   │
│ ...                                                │
└────────────────────────────────────────────────────┘

← Anterior   1 2 3 ... 5   Siguiente →
```

**Comportamiento:**
- Filtros se reflejan en query string (`?texto=salud&anio=2024`) →
  shareable URLs.
- Paginación clásica (50 por página, configurable a 100/200).
- Sort: por defecto `fecha_ingreso DESC` (igual que el backend).
- Click en una fila → `/expedientes/[id]`.
- Botón ★/☆: marcar/desmarcar seguimiento sin abrir la ficha. Optimistic
  update con TanStack Query.

**Data:**
- `GET /api/v1/expedientes?texto=...&anio=...&limit=50&offset=0` directo.
- `useQuery(['expedientes', filters])` con `keepPreviousData` para que
  cambiar página no flashee.

### `/expedientes/[id]` — Ficha del expediente

La pantalla más densa. Acá vive todo lo que el asesor necesita saber
de un expediente.

**Layout:**

```
← Volver a Expedientes

┌──────────────────────────────────────────────────────┐
│  1497-D-2024  ·  HCDN  ·  Proyecto de Ley           │
│  PROTECCIÓN DE DATOS PERSONALES — LEY 25326          │
│                                                      │
│  Estado: EN COMISION  ·  Caducidad: 2026-04-30      │
│  [★ Marcar] [→ Asignar a...] [Compartir]            │
└──────────────────────────────────────────────────────┘

┌─ Tabs ───────────────────────────────────────────────┐
│ [Resumen] [Trámite] [Firmantes] [Notas internas]    │
├──────────────────────────────────────────────────────┤
│                                                      │
│ Resumen:                                             │
│   Sumario: Modificación de los artículos 2 y 4...   │
│   Ingreso: 2024-05-01                                │
│   Texto: [link al PDF]                               │
│   Fuente: [link al portal HCDN]                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Tabs:**
- **Resumen**: campos clave (sumario, fechas, links al PDF/portal).
- **Trámite**: timeline vertical con eventos ordenados por fecha. Indicador visual de "evento sintético" vs "directo del portal" según `fuente`.
- **Firmantes**: lista con nombre, distrito, bloque, orden.
- **Notas internas**: placeholder en MVP. En v2 permitirá agregar notas privadas del despacho.

**Acciones del header:**
- **★ Marcar/Desmarcar**: `POST /api/v1/seguimientos` o `DELETE`. Si ya está marcado, el botón muestra prioridad actual + dropdown para cambiarla.
- **→ Asignar a...**: si el despacho tiene >1 miembro, dropdown con los nombres → `PATCH /api/v1/seguimientos/{id}` con `responsable_id`.
- **Compartir**: copia URL al portapapeles (no requiere backend).

**Data:**
- `GET /api/v1/expedientes/{id}` (RSC + hidratación cliente).
- El seguimiento embebido viene incluido (feat/15).

## Componentes shadcn que vamos a instalar

Para el MVP:

- `button`, `input`, `select`, `card`
- `table` (base, luego TanStack Table arriba)
- `tabs`, `badge`, `tooltip`
- `dropdown-menu`, `command` (Cmd+K), `dialog`
- `toast` (notificaciones de mutations)
- `skeleton` (loading states)
- `avatar`, `separator`, `sheet` (sidebar mobile)

## Cliente API tipado (`lib/api/client.ts`)

Wrapper sobre `fetch` que:
1. Inyecta `Authorization: Bearer <clerk-jwt>` automáticamente.
2. Inyecta `X-Despacho-Id` desde el store activo.
3. Mapea status codes a errores tipados (`ApiError401`, `ApiError403`, etc.).
4. Retorna data tipada (genéricos sobre los DTOs del backend).

**Tipos:** generados desde `/openapi.json` con `openapi-typescript`.
Comando en `package.json`:

```json
"scripts": {
  "gen:api-types": "openapi-typescript http://localhost:8000/openapi.json -o lib/api/types.gen.ts"
}
```

Esto garantiza que cambios en el backend rompan el build del frontend
en lugar de romper en runtime. CI corre `pnpm gen:api-types && tsc --noEmit`.

## Estado global (Zustand)

Mínimo necesario:

```ts
// stores/despacho.ts
type DespachoStore = {
  despachoActivoId: string | null
  setDespachoActivoId: (id: string) => void
  membresias: Membresia[]
  setMembresias: (m: Membresia[]) => void
}
```

El `despachoActivoId` se persiste en cookie HttpOnly (escrita por una
Server Action) para que SSR/RSC tenga acceso desde el primer render.

## Auth: middleware Clerk

`middleware.ts` en la raíz:

```ts
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

const isPublic = createRouteMatcher(['/sign-in(.*)', '/sign-up(.*)'])

export default clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) await auth.protect()
})

export const config = {
  matcher: ['/((?!_next|.*\\..*).*)'],
}
```

Toda ruta protegida automáticamente. El `auth.protect()` redirige a
`/sign-in` si no hay session.

## Tests del frontend (MVP)

- **Vitest unit**: helpers de `lib/`, transformaciones de filtros a query
  string, parseo de respuestas API.
- **Playwright e2e** (un solo flujo completo):
  1. Levantar backend con docker compose.
  2. Seed: `scripts/seed_inicial.py`.
  3. Loguear en Clerk (test mode con JWT generado por SDK).
  4. Navegar a `/expedientes`, buscar "Salud", click en el primer resultado.
  5. Click "★ Marcar".
  6. Ir a `/dashboard`, verificar que el expediente aparece en "Mis seguimientos".

Este test es **el smoke del producto entero**. Si pasa, el sistema funciona.

## Variables de entorno

`frontend/.env.local`:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/dashboard
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/dashboard

# URL del backend.
NEXT_PUBLIC_API_URL=http://localhost:8000
```

`backend/.env` (agregar):

```env
CLERK_ISSUER=https://[your-app].clerk.accounts.dev
CLERK_JWKS_URL=https://[your-app].clerk.accounts.dev/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=whsec_...
```

## Out of scope (en el MVP)

- Notas internas (form + persistencia): feat aparte.
- Asignación de responsable real: el backend ya soporta, pero el UI lo
  deja como botón disabled "Próximamente" hasta tener selector de miembros.
- Alertas / notificaciones (Bloque 3).
- Admin: crear despacho, invitar usuarios.
- Mobile-first UI completo: trabajamos desktop-first; mobile responsive
  básico (sidebar colapsa) pero sin optimización profunda.
- Búsqueda full-text: usamos el `texto` del backend (LIKE).
- Dark mode: estructura preparada (`next-themes`), pero arrancamos light-only.
- i18n: todo en español, hardcodeado.

## Plan de implementación

### PR 1 — Bootstrap (`feat/18-frontend-bootstrap`)
- `frontend/` con Next.js 15 + TS + Tailwind 4.
- shadcn init + primitives base.
- Clerk provider + middleware.
- Cliente API tipado (genera tipos de OpenAPI).
- `/sign-in`, `/dashboard` placeholder.
- Test E2E: login + ver dashboard.

### PR 2 — Búsqueda (`feat/19-frontend-busqueda`)
- `/expedientes` con tabla + filtros funcionales.
- Toda la lógica de query string ↔ TanStack Query.
- Skeleton + empty states.

### PR 3 — Ficha (`feat/20-frontend-ficha`)
- `/expedientes/[id]` completo con tabs.
- Acción ★ marcar/desmarcar.
- Hookeo con el card "Mis seguimientos" del dashboard.

### PR 4 — Pulido (`feat/21-frontend-polish`)
- Cmd+K command palette.
- Atajos de teclado básicos.
- Toast notifications para mutations.
- Accessibility pass (focus, ARIA, contraste).

Cada PR sale **verde con tests** antes de mergear. Ningún `console.log`
en main.

## Riesgos identificados

1. **Generación de tipos OpenAPI**: si el comando `openapi-typescript`
   genera tipos demasiado genéricos (`any` por dataclasses no-Pydantic),
   se rompe la garantía de tipado. Mitigación: validar a mano la primera
   corrida, ajustar si hace falta.

2. **Clerk + RSC**: el provider de Clerk para RSC requiere setup distinto
   al de client components. Si lo configuramos mal, el `auth()` server-side
   no devuelve la session. Mitigación: seguir docs oficiales paso a paso,
   smoke E2E que cruce el server boundary.

3. **CORS**: el backend FastAPI hoy no tiene CORS configurado. Para que
   el frontend (puerto 3000) le pegue al backend (puerto 8000), hay que
   agregar middleware CORS. **Acción a tomar antes del PR 1**: agregar
   `CORSMiddleware` al backend con `allow_origins=[NEXT_PUBLIC_FRONTEND_URL]`.

4. **Endpoint `/api/v1/seguimientos` (listar)**: el backend lo tiene en
   el repo pero NO expuesto vía HTTP. El dashboard lo necesita.
   **Acción a tomar antes del PR 3**: agregar `GET /api/v1/seguimientos`
   al router de seguimientos.
