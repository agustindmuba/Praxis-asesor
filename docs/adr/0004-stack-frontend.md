# 0004 — Stack frontend de Praxis Asesor

- **Estado**: aceptada
- **Fecha**: 2026-05-28
- **Autores**: Agustín DM
- **Supersede a**: la sección "Frontend" de [ADR 0001](0001-stack-inicial.md) (actualización menor; ver §"Diferencia con ADR 0001")
- **Superseded por**: —

## Contexto

ADR 0001 declaró el stack frontend a nivel general (Next.js + Tailwind +
shadcn + TanStack Query). En este ciclo el backend ya está operativo:
9 endpoints, auth Clerk con multi-tenancy via `X-Despacho-Id`, smoke test
verde contra Postgres real. Toca poner cara al backend.

Antes de pedirle al primer asesor que use el producto, tres decisiones
operativas pendientes:

1. **Dónde vive el código del frontend** (monorepo vs repo separado).
2. **Qué versión y patrón de Next.js** (la 14 del ADR 0001 quedó vieja —
   Next.js 15 con RSC estabilizado es lo de hoy).
3. **Cómo se enchufa Clerk** (provider, middleware, sync con backend).

Esto define el `frontend/` que vamos a construir.

## Decisión

### Layout: monorepo

El frontend vive en `praxis-asesor/frontend/`. PRs traen cambios coordinados
backend/frontend, una sola fuente de versionado, un solo CI.

```
praxis-asesor/
├── backend/      # Python 3.12, FastAPI, SQLAlchemy
├── frontend/     # Next.js 15, TypeScript, Tailwind, shadcn
├── docs/         # ADRs + specs + runbooks compartidos
├── docker-compose.yml
└── CLAUDE.md
```

No hay paquetes compartidos en JavaScript: el contrato API ya está
documentado vía OpenAPI (FastAPI lo genera). Si en el futuro queremos
tipos compartidos, agregamos `shared/openapi-types/` generado desde
`/openapi.json`.

### Stack (Node 22 LTS + TypeScript strict)

| Pieza | Elección | Por qué |
|---|---|---|
| Runtime | **Node 22 LTS** | Long-term support hasta abril 2027. |
| Framework | **Next.js 15 (App Router + RSC)** | Server Components estabilizados, streaming, generación parcial. Mejor SEO + perf. |
| Lenguaje | **TypeScript 5.6+ strict** | Mismo estándar de "tipado fuerte donde duele" que el backend. |
| Estilos | **Tailwind CSS 4** | Velocidad, sin context-switching de CSS files. v4 trae mejor perf de build. |
| Componentes | **shadcn/ui** + **Radix UI primitives** | Copy-paste; cero lock-in; primitives accesibles desde el día 1. |
| Iconos | **lucide-react** | Set consistente, tree-shakeable, hermano de shadcn. |
| Auth | **Clerk Next.js SDK** | `@clerk/nextjs` con middleware. JWT con `sub` que matchea `auth_provider_id` del backend. |
| Data fetching | **TanStack Query v5** | Cache, invalidación, optimistic updates. Para mutations + lists. |
| HTTP client | **fetch nativo** + wrapper tipado | Sin axios. Wrapper centraliza headers (Authorization, X-Despacho-Id) y errores. |
| Formularios | **React Hook Form** + **Zod** | Validación isomórfica (la podemos compartir con el backend si vale la pena). |
| Tablas | **TanStack Table v8** | Headless, ideal para tablas densas con sort/filter/pagination. |
| Estado global | **Zustand** (mínimo) | Solo para el despacho activo + UI state. El resto vive en TanStack Query. |
| Tests unit | **Vitest** | Veloz, compatible con Vite/Jest. |
| Tests e2e | **Playwright** | Cross-browser, screenshots automáticos. |
| Lint/format | **ESLint** (config Next.js) + **Prettier** | Reemplazables por Biome si la velocidad duele. |

### Look & feel

**Linear/Notion-ish: productivo y denso.**

- **Sidebar fija** con navegación principal (Dashboard, Expedientes, Seguimientos, Notas).
- **Topbar** con buscador global, selector de despacho activo (si el usuario es miembro de >1), avatar.
- **Tablas densas** con paginación, filtros inline, sort por columna.
- **Detalle con tabs** (Resumen | Trámite | Firmantes | Notas internas).
- **Tema claro por default**, con dark mode opcional (`next-themes`). Light gris muy claro, accents azul desaturado, tipografía Inter.
- **Atajos de teclado** desde el día 1: `Cmd+K` buscar, `g d` ir a dashboard, `g e` ir a expedientes (estilo Linear).

### Arquitectura interna del frontend

```
frontend/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # rutas sin layout app (login, signup)
│   │   ├── sign-in/[[...sign-in]]/page.tsx
│   │   └── sign-up/[[...sign-up]]/page.tsx
│   ├── (app)/                    # rutas con sidebar + auth guard
│   │   ├── layout.tsx            # shell: sidebar + topbar
│   │   ├── dashboard/page.tsx
│   │   ├── expedientes/
│   │   │   ├── page.tsx          # listado + filtros
│   │   │   └── [id]/page.tsx     # ficha
│   │   └── seguimientos/page.tsx
│   ├── api/                      # NO usamos esto — todo va al backend Python
│   ├── layout.tsx                # root layout + providers
│   └── globals.css
├── components/
│   ├── ui/                       # shadcn primitives
│   └── features/                 # composiciones por dominio
│       ├── expedientes/
│       └── seguimientos/
├── lib/
│   ├── api/                      # cliente tipado del backend
│   │   ├── client.ts             # fetch wrapper
│   │   ├── expedientes.ts
│   │   ├── seguimientos.ts
│   │   └── me.ts
│   ├── auth.ts                   # helpers Clerk + tenant
│   └── utils.ts                  # cn(), etc.
├── hooks/                        # React hooks reutilizables
├── stores/                       # Zustand stores
├── middleware.ts                 # Clerk middleware
├── next.config.ts
├── tailwind.config.ts
├── package.json
└── tsconfig.json
```

### Cómo conversan frontend y backend

1. **Auth flow:**
   - Usuario aterriza → Clerk SignIn/SignUp.
   - Clerk dispara webhook `user.created` → backend lo provisiona en DB
     (feat/16 ya cubre esto).
   - Sysadmin asigna `MembresiaDespacho` (futuro endpoint de admin; por
     ahora seed manual con `scripts/seed_inicial.py`).
   - Frontend pide token de session de Clerk + lo manda en `Authorization: Bearer`.

2. **Despacho activo:**
   - GET `/api/v1/me` devuelve `usuario + despacho + rol`.
   - Si el usuario está en un solo despacho, ese queda activo.
   - Si está en varios (caso futuro), un selector en topbar lo cambia.
   - El `despacho_id` activo se guarda en Zustand store + cookie HttpOnly
     para SSR/RSC.
   - **Cada request HTTP** del frontend incluye `X-Despacho-Id` con ese UUID.

3. **Renderizado:**
   - **RSC para reads** (lista expedientes, ficha): el server component
     hace el fetch al backend, los datos se serializan en el HTML inicial.
     TanStack Query "hidrata" desde el server-state.
   - **Client components para writes** (POST seguimiento, PATCH archivar):
     usan `useMutation` con invalidación automática del cache.

4. **Variables de entorno frontend (`.env.local`):**
   ```env
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
   CLERK_SECRET_KEY=sk_test_...
   NEXT_PUBLIC_API_URL=http://localhost:8000  # dev
   ```

5. **Errores del backend → UI:**
   - `401` → forzar re-login (Clerk redirect).
   - `403` → modal "no tenés permisos en este despacho".
   - `404` → página 404 contextual.
   - `409` → toast "ya seguías este expediente".
   - `422` → resaltado de campos del form (Zod errors mapeados).
   - `5xx` → toast "error inesperado, reintentar" + Sentry capture.

## Diferencia con ADR 0001

ADR 0001 dijo Next.js 14. Acá actualizamos a 15 — RSC estabilizado, Turbopack
maduro, `after()` hook para tasks post-response. No es una decisión nueva
estructural; es ponernos al día con la versión vigente.

Las demás piezas (Tailwind, shadcn, TanStack, Clerk) **se confirman** con
detalle operativo agregado (Zustand para despacho activo, Node 22, dark
mode opcional, atajos de teclado, etc.).

## Alternativas consideradas

### Repo separado

Permitía deploys independientes y CI más rápido por proyecto. Descartado
porque el costo de coordinar versiones manualmente y la fricción de PRs
que tocan ambos lados (ej. agregar un campo a la ficha) supera el beneficio
en este tamaño de equipo (1 desarrollador). Si en el futuro el frontend
crece a un equipo aparte, separarlo es trivial.

### Vite + React SPA

Más liviano y con menos magia. Pero perdemos SSR/RSC (peor SEO + perf
inicial), perdemos las file-based routes idiomáticas, y reescribir el
SDK de Clerk para no-SSR es trabajo gratis. Descartado.

### Remix v2

Muy sólido en data loading. Pero el ecosistema shadcn + Clerk + TanStack
está más maduro en Next. El switch costaría más que el beneficio en este
momento.

### Astro + React islands

Apto para sitios mayormente estáticos. Nuestra app es altamente interactiva
(filtros en vivo, mutations frecuentes). Overkill el split estático/dinámico.

### Biome vs ESLint+Prettier

Biome es 10× más rápido y un solo binario. Pero el ecosistema Next.js
asume ESLint, y la config `next lint` "just works". Mantenemos ESLint
hasta que el tiempo de lint duela. Sin compromiso.

## Plan de implementación (alcance del primer PR de frontend)

Ver [spec 12](../specs/12-frontend-mvp-ui.md) para detalle por pantalla.
En síntesis:

1. **Bootstrap**: `frontend/` con Next.js 15 + Tailwind + shadcn + Clerk.
2. **Cliente API tipado**: `lib/api/client.ts` con headers + manejo de errores.
3. **Provider tree**: Clerk + TanStack Query + tema + Zustand.
4. **4 rutas**: `/sign-in`, `/dashboard`, `/expedientes`, `/expedientes/[id]`.
5. **Smoke E2E**: Playwright corre login + búsqueda + ficha + marcar
   seguimiento contra el backend levantado.

## Consecuencias

**Positivas:**
- Single repo = un solo PR para cambios end-to-end.
- Stack moderno con buena DX (Next.js 15 + Tailwind 4 + shadcn).
- Auth resuelto con Clerk; sin reinventar.
- RSC reduce código cliente y carga JS inicial.

**Negativas / aceptadas:**
- Vendor lock parcial en Clerk (mitigado por el puerto `AuthProvider` del
  backend; el frontend hablaría con cualquier IdP que firme JWTs).
- Next.js es opinionado y se mueve rápido; vamos a tener que upgradear
  ~1×/año.
- Aumenta el tamaño del repo (npm/pnpm install).
- Aprender shadcn + RSC patterns para devs nuevos suma curva.

**Reversible si:**
- Si Next.js 15 RSC nos rompe productividad → caemos a SPA (Pages Router
  o Vite).
- Si Clerk se vuelve caro → cambiamos el adapter (puerto + `ClerkAuthProvider`
  del backend lo deja preparado).
