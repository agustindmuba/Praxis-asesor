# 0001 — Stack inicial de Praxis Asesor

- **Estado**: aceptada
- **Fecha**: 2026-05-27
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —

## Contexto

Praxis Asesor entra al ciclo 1 (scaffolding + scraping exploratorio). Antes de generar código, se necesita una decisión formal y trazable sobre el stack técnico, porque:

1. **Restricción dura**: el producto debe desplegarse en SaaS cloud, SaaS con datos en Argentina, o self-hosted en infraestructura del cliente (ver `ARCHITECTURE.md` §"Principios rectores" — despliegue agnóstico). Cualquier elección debe ser compatible con los tres escenarios.
2. **Restricción de equipo**: hoy hay un solo desarrollador (Agustín). El stack debe ser productivo en solitario y a la vez admitir incorporación de devs senior sin reescrituras.
3. **Restricción de dominio**: el sistema vive del scraping de portales oficiales (HCDN, HSN), del cruce de datos, y de notificaciones en tiempo casi real. El ecosistema elegido debe ser fuerte en esos tres ejes.
4. **Restricción de horizonte**: el roadmap declara v3 con asistencia de IA, lo que implica preparación temprana para vectorización y RAG (`pgvector` o equivalente).

## Decisión

Se adopta el stack descripto en `ARCHITECTURE.md` §"Stack técnico", con esta lectura formal:

### Backend (Python 3.12)

| Pieza | Elección | Rol |
|---|---|---|
| Gestor de paquetes y entornos | **uv** | Reemplaza pip + virtualenv + Poetry; 10-100× más rápido; ecosistema Astral (mismos autores que ruff). |
| Framework web | **FastAPI** | API HTTP, OpenAPI auto, async nativo. |
| Validación | **Pydantic v2** | Modelos de entrada/salida, settings. |
| ORM | **SQLAlchemy 2.0 (async)** | Acceso a datos, sesiones async. |
| Migraciones | **Alembic** | Schema evolutivo trazable. |
| Cola de tareas | **Celery + Redis** | Scraping periódico, alertas, jobs pesados. |
| DB principal | **PostgreSQL 16** + **pgvector** | Datos relacionales + vectores (RAG futuro). |
| Tests | **pytest** + **pytest-asyncio** + **factory-boy** | Unit + integración. |
| Lint/format | **ruff** | Reemplaza black, isort, flake8. |
| Type check | **mypy --strict** en `domain/` y `application/` | Seguridad de tipos en lógica núcleo. |

### Frontend (Node 20 + TypeScript strict)

| Pieza | Elección | Rol |
|---|---|---|
| Framework | **Next.js 14 (App Router)** | SSR/RSC, ecosistema. |
| Estilos | **Tailwind CSS** | Velocidad y consistencia. |
| Componentes | **shadcn/ui** + **Radix** | Copy-paste, cero lock-in. |
| Data fetching | **TanStack Query** | Cache, revalidación. |
| Formularios | **React Hook Form** + **Zod** | Performance + tipado. |
| Tablas | **TanStack Table** | Listas largas de expedientes. |
| Tests | **Vitest** + **Playwright** | Unit + e2e. |

### Servicios externos (intercambiables vía puerto)

| Concepto | Inicial | Alternativas previstas |
|---|---|---|
| Auth | **Clerk** | Auth0, Supabase Auth, propio. |
| Email | **Resend** o **SES** | SendGrid, SMTP propio. |
| Storage | **S3-compatible (R2)** | MinIO, GCS, Azure Blob. |
| Secretos | Vars del proveedor (dev) / **Doppler** (prod) | AWS Secrets Manager, Vault. |
| Observabilidad | **Sentry** + **Posthog** | Datadog, OpenTelemetry. |
| LLM | **API de Anthropic** | Único proveedor por ahora. |

### Despliegue dev/staging

- **Docker** desde día 1 (portabilidad y consistencia).
- **Railway o Render** para staging (definir en ciclo 2).
- **GitHub Actions** para CI (lint, type-check, test, build).

## Alternativas consideradas

### Backend

- **Django + DRF**: descartado. Más rápido para CRUD clásico, pero `async` y FastAPI ganan en latencia + tipado + OpenAPI gratis, y la curva de aprendizaje es comparable.
- **Node/NestJS unificado con frontend**: descartado. El ecosistema Python es superior para scraping (`httpx`, `lxml`, `pdfplumber`) y para IA (clientes Anthropic, tooling NLP). Mantener dos lenguajes es aceptable.
- **Go**: descartado. Más performance, pero curva más empinada para un equipo no-senior y ecosistema scraping/IA menos maduro.

### Gestor de paquetes

- **Poetry**: descartado. Maduro y con más material online, pero significativamente más lento que uv y con un workflow más cargado. Si uv se rompe, migrar a Poetry es trivial (mismo `pyproject.toml` estándar).
- **pip + requirements.txt**: descartado. Sin lockfile robusto, sin resolución determinista, dificulta reproducibilidad entre entornos.

### DB

- **SQLite**: viable para spike inicial; descartado como elección de producción por concurrencia y por la dependencia de `pgvector` para RAG.
- **MongoDB**: descartado. El dominio es fuertemente relacional (expedientes ↔ firmantes ↔ comisiones ↔ trámites), schema rígido es ventaja, no obstáculo.

### Cola

- **Tareas in-process con APScheduler**: viable a corto plazo; descartado por imposibilidad de escalar a workers múltiples sin migrar.
- **RQ**: más simple que Celery pero menos rico (sin scheduling avanzado, sin retries declarativos, sin chains/groups).

### Frontend

- **Remix**: comparable a Next.js; se eligió Next por mayor tamaño de comunidad y por integración natural con Vercel/Railway si se llega.
- **SvelteKit**: menos masa crítica en componentes (shadcn/ui para Svelte es inmaduro respecto al de React).
- **Sin frontend dedicado (Streamlit/HTMX)**: descartado para el MVP, sirve para spikes internos.

### Auth

- **Auth propio**: descartado para MVP. Costo de implementación + riesgos de seguridad excesivos para el momento.
- **Supabase Auth**: viable; Clerk gana por UX de onboarding multi-tenant out-of-the-box.

## Consecuencias

### Que ganamos

- Async-first desde el día 1; el sistema puede atender múltiples despachos sin bloquearse.
- Tipado estricto en `domain/` y `application/` — la lógica de negocio crítica del despacho queda protegida.
- Multi-tenancy implementable limpiamente sobre PostgreSQL + middleware ORM.
- Ecosistema Python fuerte para scraping y futura IA.
- Frontend moderno con productividad alta y cero lock-in de componentes.
- Auth y email manejados por servicios maduros; sin reinventar.

### Que aceptamos como costo

- **Curva de aprendizaje** del paradigma async + hexagonal + SQLAlchemy 2.0 para un dev no-senior. Mitigación: layout y convenciones documentadas explícitamente en `CLAUDE.md` y `ARCHITECTURE.md`; revisión arquitectónica con dev senior externo al menos una vez antes de producción (declarado como riesgo en `ARCHITECTURE.md` §"Riesgos técnicos abiertos").
- **Operación de Celery + Redis + Postgres + frontend** desde día 1: superficie operativa mayor que un monolito simple. Mitigación: todo containerizado con Docker Compose en dev; Railway/Render absorben gran parte de la operación en staging.
- **Vendor lock-in parcial** con Clerk y los proveedores cloud iniciales. Mitigación: la regla hexagonal exige que toda integración externa pase por un puerto (interface). Reemplazar Clerk por otro proveedor implica reescribir el adaptador, no el código de negocio.
- **Costo en USD** por servicios externos (Clerk, Sentry, Posthog, Anthropic, hosting). Aceptable en escala de MVP; se monitorea explícitamente.
- **Dos lenguajes (Python + TypeScript)**: doble tooling, doble linting, doble CI. Aceptable a cambio de usar lo mejor de cada ecosistema.

### Lo que esta decisión bloquea

Cualquier cambio de pieza listada acá requiere un nuevo ADR que supersede a éste, salvo:

- Cambios de versión menor de las dependencias (3.12.x → 3.12.y).
- Reemplazo de un servicio externo por uno de la columna "Alternativas previstas" — basta nota en este mismo ADR y mención en commit.

## Próximos pasos

1. Scaffolding backend en este orden: `backend/pyproject.toml` con `uv` → layout hexagonal → `config.py` con `pydantic-settings` → FastAPI app con `/health` → SQLAlchemy 2.0 async setup → Alembic init → `docker-compose.yml` en la raíz del repo (Postgres 16 con pgvector + Redis) → Celery setup → estructura de tests → GitHub Actions.
2. Scaffolding frontend (separado, ADR no lo bloquea).
3. Spike de scraping HCDN/HSN — feature 1 del MVP (ver `PRODUCT.md` §"Features en orden de implementación").
