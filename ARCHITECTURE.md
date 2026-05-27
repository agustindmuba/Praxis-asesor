# ARCHITECTURE.md — Praxis Asesor

## Principios rectores

1. **Despliegue agnóstico**: el código de negocio no conoce el proveedor de infraestructura.
2. **Simplicidad antes que cleverness**: preferimos código aburrido y legible.
3. **Datos correctos antes que features brillantes**: la confianza en los datos es nuestro activo principal.
4. **Async-first**: toda I/O es asíncrona; el sistema debe escalar a múltiples despachos sin bloquearse.
5. **Auditabilidad**: toda acción importante deja rastro.
6. **Testing donde duele**: tests rigurosos en lógica de negocio y parsers; pragmáticos en UI.

## Arquitectura general

Estilo: **arquitectura hexagonal (ports & adapters)** con tres capas concéntricas.

```
┌─────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE                       │
│  (DB, scrapers, email, queue, auth provider, storage)   │
│  ┌───────────────────────────────────────────────────┐  │
│  │                  APPLICATION                      │  │
│  │       (casos de uso, orquestación, servicios)     │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │                 DOMAIN                      │  │  │
│  │  │  (entidades, value objects, reglas puras)   │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

Regla: las dependencias apuntan SIEMPRE hacia adentro.
Domain no conoce Application. Application no conoce Infrastructure.
```

### Capa Domain

- Entidades puras (`Expediente`, `Tramite`, `Legislador`, `Despacho`, etc.).
- Value objects (`NumeroExpediente`, `Camara`, `EstadoExpediente`).
- Reglas de negocio que no requieren I/O.
- Sin dependencias externas (ni SQLAlchemy, ni FastAPI, ni nada).
- 100% testeable sin mocks.

### Capa Application

- Casos de uso (`SeguirExpediente`, `AsignarExpedienteAAsesor`, `ConfigurarAlerta`).
- Define **puertos** (interfaces abstractas): `ExpedienteRepository`, `NotificationSender`, `EventBus`, etc.
- No conoce implementaciones concretas; recibe puertos por inyección.

### Capa Infrastructure

- **Adaptadores** que implementan los puertos:
  - `SqlAlchemyExpedienteRepository` (implementa `ExpedienteRepository`).
  - `SmtpNotificationSender`, `SesNotificationSender` (implementan `NotificationSender`).
  - `HcdnScraper`, `HsnScraper` (implementan `FuenteExpedientes`).
- API HTTP (FastAPI routers): traduce HTTP ↔ casos de uso.
- Migraciones, jobs de Celery, configuración.

## Stack técnico (propuesta inicial, confirmar en ciclo 1)

### Backend

| Componente | Elección | Justificación |
|---|---|---|
| Lenguaje | Python 3.12 | Ecosistema NLP/scraping/PDF, curva suave, productividad alta. |
| Framework web | FastAPI | Async nativo, tipado con Pydantic, OpenAPI gratis. |
| ORM | SQLAlchemy 2.0 async | Estándar de facto, soporte async maduro. |
| Migraciones | Alembic | Va con SQLAlchemy. |
| DB | PostgreSQL 16 | Robusto, JSON, full-text search, pgvector para RAG futuro. |
| Cola | Celery + Redis | Scraping periódico, envío de alertas, jobs pesados. |
| Validación | Pydantic v2 | Va con FastAPI. |
| Tests | pytest + pytest-asyncio + factory-boy | Estándar. |
| Lint/format | ruff | Rápido, reemplaza black + isort + flake8. |
| Type check | mypy --strict (en domain/application) | Seguridad de tipos en capas críticas. |

### Frontend

| Componente | Elección | Justificación |
|---|---|---|
| Framework | Next.js 14 (App Router) | SSR/RSC, ecosistema, productividad. |
| Lenguaje | TypeScript strict | Tipado obligatorio. |
| Estilos | Tailwind CSS | Velocidad, consistencia. |
| Componentes | shadcn/ui + Radix | No es una librería: copiás componentes, los adaptás. Cero lock-in. |
| Data fetching | TanStack Query (React Query) | Cache, revalidation, optimistic updates. |
| Formularios | React Hook Form + Zod | Performance + validación tipada. |
| Tablas | TanStack Table | Listas largas de expedientes con filtros. |
| Tests | Vitest + Playwright | Unit + e2e. |

### Servicios externos (con adaptadores intercambiables)

| Servicio | Inicial | Alternativas |
|---|---|---|
| Auth | Clerk | Auth0, Supabase Auth, propio. |
| Email | Resend o SES | SendGrid, SMTP propio. |
| Storage de archivos | S3-compatible (R2 inicial) | MinIO, GCS, Azure Blob. |
| Secretos | Variables del proveedor (dev), Doppler (prod) | AWS Secrets Manager, Vault. |
| Observabilidad | Sentry + Posthog | Datadog, OpenTelemetry. |
| LLM | API Anthropic (Claude) | Único proveedor por ahora. |

### Despliegue (dev/staging)

- **Railway o Render**: rápido para dev/staging. Producción se define según cliente.
- **Docker**: todo containerizado desde el día 1 para portabilidad.
- **CI/CD**: GitHub Actions (lint, test, build, deploy a staging en merge a `develop`).

## Modelo de datos (esquema inicial)

> Esquema preliminar. Definitivo en ciclo 2.

```
camara
  id (HCDN | HSN)
  nombre

bloque
  id
  camara_id
  nombre
  fecha_creacion, fecha_disolucion

comision
  id
  camara_id
  nombre
  tipo (permanente | especial | bicameral)

legislador
  id
  nombre_completo
  documento
  fecha_nacimiento, distrito
  -- relaciones por mandato/período en tabla aparte

mandato
  id
  legislador_id
  camara_id
  bloque_id (al inicio)
  fecha_inicio, fecha_fin
  distrito

membresia_comision
  legislador_id, comision_id, mandato_id
  cargo (presidente, vicepresidente, secretario, vocal)
  fecha_inicio, fecha_fin

expediente
  id
  camara_id
  numero        -- ej. "1234-D-2025" o "S-456/25"
  tipo          -- ley, resolucion, declaracion, comunicacion
  titulo
  sumario
  fecha_ingreso
  estado_actual
  texto_url, texto_hash
  perdida_estado_parlamentario_en (calculado)

firmante
  expediente_id, legislador_id
  orden (1 = autor principal)

giro
  expediente_id, comision_id
  fecha
  orden_giro    -- cabecera, complementario, etc.

dictamen
  id
  expediente_id, comision_id
  tipo (mayoria, minoria, unico)
  fecha
  texto_url
  firmantes (FK a legislador)

tramite                          -- append-only, fuente de verdad
  id
  expediente_id
  fecha
  evento        -- ingreso, giro, dictamen, OD, sancion, archivo, etc.
  detalle (JSONB)
  fuente_url

-- ---- Multi-tenancy ----

despacho
  id
  nombre        -- ej. "Despacho Dip. X" / "Bloque Y"
  legislador_titular_id (nullable: puede ser de bloque)
  configuracion (JSONB)

usuario
  id
  email, nombre
  auth_provider_id (Clerk u otro)

membresia_despacho
  usuario_id, despacho_id
  rol (jefe_asesores | asesor | lector)
  activo

seguimiento_expediente
  despacho_id, expediente_id
  responsable_id (usuario)
  prioridad (alta | media | baja)
  fecha_inicio_seguimiento
  archivado

alerta
  id
  despacho_id, usuario_id (creador)
  scope (expediente | tema | autor | comision)
  scope_id (polimórfico según scope)
  eventos[] (cambio_estado, nuevo_dictamen, ingreso_OD, votacion)
  canales[] (in_app, email)
  activa

nota_interna
  id
  despacho_id, expediente_id, usuario_id
  contenido (cifrado en reposo)
  fecha

audit_log
  id
  despacho_id, usuario_id
  accion, entidad, entidad_id
  diff (JSONB)
  timestamp, ip
```

## Multi-tenancy

- **Shared database, shared schema, tenant column** (`despacho_id`).
- Política a nivel ORM: middleware que inyecta `despacho_id` en sesión, y `Query.filter(despacho_id=current)` automático para entidades tenant-scoped.
- Datos públicos (expedientes, legisladores, comisiones, trámites) son globales: NO tienen `despacho_id`.
- Datos del despacho (`seguimiento_*`, `nota_interna`, `alerta`, `membresia_*`, `audit_log`) sí lo tienen.
- Tests específicos para verificar aislamiento (un despacho no ve datos de otro).

## Ingesta de datos parlamentarios

### Estrategia

- **Workers Celery** programados con Celery Beat.
- Frecuencia inicial: cada 30 min en días de sesión, cada 2 hs en días normales, cada 6 hs en receso.
- **Diff incremental**: comparar hash del payload contra última ingesta; solo procesar cambios.
- Cada cambio genera un **evento de dominio** (`ExpedienteIngresado`, `ExpedienteCambioEstado`, `NuevoDictamen`, etc.) que el sistema de alertas consume.

### Adaptadores

- `HcdnScraper`: implementa `FuenteExpedientes` para Diputados.
- `HsnScraper`: implementa `FuenteExpedientes` para Senado.
- Cada uno responsable de transformar HTML/JSON crudo en el modelo de dominio común.
- Tests de contrato: snapshot del payload real, parser debe producir output esperado.
- Monitoreo: si un scrape falla X veces consecutivas, alerta a equipo (no al cliente).

## Sistema de alertas

```
[ingesta] → [evento de dominio] → [EventBus] → [matcher de alertas] → [notification sender]
```

- `EventBus` es un puerto; implementación inicial: tabla `domain_events` + worker que la procesa.
- Matching: por cada evento, buscar alertas cuyo scope coincida y disparar notificaciones según canales configurados.
- Idempotencia: cada notificación tiene `idempotency_key` para no duplicar.

## Autenticación y autorización

- **Autenticación**: delegada a Clerk inicialmente (puerto `AuthProvider`).
- **Autorización**: hecha en casos de uso. Cada caso de uso recibe `UsuarioActual` y `Despacho` y valida permisos.
- Roles del MVP:
  - `jefe_asesores`: todo dentro del despacho.
  - `asesor`: lee todo del despacho, escribe en sus propios seguimientos/notas.
  - `lector`: solo lectura del despacho.

## Observabilidad

- **Logs estructurados** (JSON) con contexto: `request_id`, `usuario_id`, `despacho_id`.
- **Tracing** con OpenTelemetry (opcional inicial, recomendado).
- **Errors** a Sentry.
- **Métricas de producto** a Posthog (anonimizadas: features usadas, no contenido de notas).
- **Health checks**: `/health` (liveness), `/ready` (readiness, chequea DB y dependencias).

## Seguridad

- TLS en todo tránsito externo.
- Cifrado en reposo: a nivel de DB (provider) + a nivel de columna para `nota_interna.contenido`.
- Secrets: nunca en repo; en variables/secret manager por entorno.
- Dependencias: `pip-audit` y `npm audit` en CI.
- Rate limiting por usuario y por IP en endpoints públicos.
- CSRF: tokens en cookies para frontend; headers para API directa.
- CORS estricto.

## Riesgos técnicos abiertos

1. **Estabilidad de portales oficiales**: mitigación con tests de contrato + alertas.
2. **Cumplimiento Ley 25.326**: documentar formalmente antes de primer cliente real.
3. **Sin DevOps dedicado**: aceptar Railway/Render hasta que escale.
4. **Sin equipo senior**: revisar arquitectura con un dev senior externo al menos una vez antes de producción.
