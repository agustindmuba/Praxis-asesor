# Praxis Asesor — Frontend

Stack: **Next.js 15 App Router + React 19 + TypeScript strict + Tailwind 4
+ shadcn/ui + Clerk + TanStack Query + Zustand**.

Ver decisiones en:
- [ADR 0004 — Stack frontend](../docs/adr/0004-stack-frontend.md)
- [Spec 12 — Frontend MVP UI](../docs/specs/12-frontend-mvp-ui.md)

## Quick start

Requiere Node ≥ 22 y pnpm ≥ 9.

```bash
# Desde la raíz del repo
cd frontend

# Instalar deps (la primera vez)
pnpm install

# Configurar env
cp .env.example .env.local
# Editar .env.local con las keys reales de Clerk

# Arrancar el dev server
pnpm dev
```

El frontend levanta en http://localhost:3000.

> **Importante:** el backend tiene que estar corriendo para que /me y los
> endpoints funcionen. Levantar el stack completo (Postgres + backend):
>
> ```bash
> # En otra terminal, desde la raíz del repo:
> docker compose up -d
> cd backend && uv run alembic upgrade head
> uv run python -m praxis.api.main  # arranca en :8000
> ```

## Scripts

| Script | Qué hace |
|---|---|
| `pnpm dev` | Dev server con Turbopack |
| `pnpm build` | Build de producción |
| `pnpm start` | Sirve el build (después de `pnpm build`) |
| `pnpm lint` | ESLint |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm format` | Prettier --write |
| `pnpm test` | Vitest unit tests |
| `pnpm e2e` | Playwright e2e tests |
| `pnpm gen:api-types` | Regenera tipos desde el OpenAPI del backend (requiere backend corriendo) |

## Estructura

```
frontend/
├── app/
│   ├── (auth)/            # Rutas sin shell: /sign-in, /sign-up
│   ├── (app)/             # Rutas con shell: /dashboard, /expedientes, /seguimientos
│   ├── actions/           # Server Actions (cookie despacho)
│   ├── layout.tsx         # Root layout + ClerkProvider + QueryProvider
│   └── globals.css        # Tailwind 4 + tema
├── components/
│   ├── providers/         # Query/Despacho providers
│   ├── ui/                # shadcn primitives (se agregarán por feature)
│   └── app-shell.tsx      # Sidebar + topbar
├── lib/
│   ├── api/               # Cliente HTTP tipado, endpoints, tipos
│   └── utils.ts           # cn() helper
├── stores/                # Zustand stores
├── middleware.ts          # Clerk middleware (protege rutas)
├── next.config.ts
├── tsconfig.json
├── postcss.config.mjs     # Tailwind 4
└── package.json
```

## Flujo de auth + tenant

1. Usuario aterriza en `/` → middleware Clerk → redirect a `/sign-in`.
2. Usuario se loguea → Clerk redirect a `/dashboard`.
3. `(app)/layout.tsx` (Server Component):
   - Lee token de Clerk + cookie del despacho.
   - Si no hay cookie de despacho: muestra placeholder ("pedile a tu admin").
   - Hace `GET /api/v1/me` con `Authorization` + `X-Despacho-Id`.
   - Pasa `me` a `<AppShell>` + hidrata el store Zustand del despacho.
4. Componentes cliente leen el token vía `useApiContext()` + el despacho vía
   `useDespachoStore()` para hacer mutations (POST seguimientos, etc.).

## Generación de tipos desde el backend

El backend FastAPI expone `/openapi.json`. Para regenerar `lib/api/types.gen.ts`:

```bash
# Con el backend corriendo en :8000:
pnpm gen:api-types
```

Por ahora `lib/api/types.ts` está escrito a mano (cobertura mínima del MVP).
Cuando estabilice el contrato, switch a generación automática.

## Tests

- **Vitest unit**: `pnpm test` — helpers de `lib/`, transformaciones, etc.
- **Playwright e2e**: `pnpm e2e` — smoke del producto entero. Requiere
  backend + Postgres + seed corriendo.

## Próximos PRs

- `feat/20-frontend-busqueda` — Tabla de expedientes + filtros funcionales.
- `feat/21-frontend-ficha` — Ficha detallada + marcar/asignar seguimientos.
- `feat/22-frontend-polish` — Cmd+K, atajos, toasts, accessibility.
