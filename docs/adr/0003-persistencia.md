# 0003 — Persistencia con SQLAlchemy 2.0 async + multi-tenancy

- **Estado**: aceptada
- **Fecha**: 2026-05-28
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —

## Contexto

El bloque 1 del MVP entregó dominio + adaptadores read-only (scrapers, CSVs/JSON vendored). El bloque 2 introduce **persistencia**: guardar expedientes capturados para servir queries rápidas, modelar despachos y usuarios para multi-tenancy, y soportar features de seguimiento, asignación, notas y alertas.

ADR 0001 ya decidió: PostgreSQL 16 + SQLAlchemy 2.0 async + Alembic + pgvector. ADR 0002 §"Multi-tenancy" decidió: shared DB, shared schema, `despacho_id` columna discriminadora. Este ADR concreta la **forma** de esa persistencia.

Decisiones tomadas vía interacción con Agustín el 2026-05-28:
1. ID strategy: **UUID v7**.
2. Mapeo ORM ↔ dominio: **ORM models separados + mappers**.
3. Snapshots: **solo current state + audit_log**.
4. Tenancy enforcement: **filter explícito en repos**.

## Decisión

### 1. Identifiers: UUID v7 para todas las entidades públicas

Cada tabla de dominio público (Expediente, Despacho, Usuario, etc.) tiene PK `id UUID` generado como **UUID v7** (RFC 9562). Ventajas: time-sortable (mejor performance de inserción y range queries), no leakea conteos, estándar moderno, soportado natively por Postgres 16.

Implementación: `uuid.uuid7()` de Python stdlib (Python 3.13+) o `uuid6` package mientras no esté disponible en el runtime. Postgres puede generar también via `gen_random_uuid()` pero preferimos generación en aplicación para evitar round-trip.

Tablas de catálogo de referencia que ya tienen ID natural (legislador con `slug`, comisión con `comision_slug`) **mantienen su ID natural** como PK. UUID solo para entidades cuya identidad nace en este sistema.

### 2. Mapeo ORM ↔ dominio: ORM models separados + mappers

Los dataclasses de `praxis.domain` permanecen **sin acoplamiento a SQLAlchemy**. La persistencia vive en `praxis.infrastructure.persistence/`:

- `models.py`: clases `MappedAsDataclass` de SQLAlchemy 2.0 (los "ORM models").
- `mappers.py`: funciones `to_domain(orm_obj) -> DomainEntity` y `from_domain(entity) -> orm_obj`.

Justificación: preserva la regla hexagonal del ADR 0001 (dominio puro). Cuesta más boilerplate, pero protege contra leakage de detalles ORM hacia casos de uso y permite cambiar de SQLAlchemy a otro stack futuro sin tocar dominio.

### 3. Snapshots vs current-only: solo current + audit_log

**Una row por entidad con el estado actual.** Cuando el scraper trae una versión nueva de un expediente, se hace `UPSERT` sobre el current state. Cambios significativos se loguean en `audit_log` (qué campo cambió, valor previo, timestamp, fuente).

Justificación: el storage de snapshots versionados es 10-30× más caro y complica todas las queries. El MVP no requiere reconstruir el estado en cualquier punto del pasado; el audit_log cubre el caso "qué cambió desde la última vez". Si en el futuro aparece una feature que requiere historial completo (ej. "ver el expediente como estaba el 2024-03-01"), se promueve con ADR aparte.

El **trámite** SÍ es append-only por design (cada `TramiteEvento` es un row aparte que nunca se modifica; se agregan eventos nuevos al merge con el ya conocido — ver `praxis.domain.merge_tramite`).

### 4. Tenancy enforcement: filter explícito en repos

Cada repositorio que opera sobre tablas tenant-scoped recibe `despacho_id: UUID` como parámetro obligatorio en cada método. El filter `WHERE despacho_id = :despacho_id` es **explícito en cada query**, no automático.

Justificación: simpler, más testeable, más auditable. La alternativa "event listener SQLAlchemy" tiene magia de inyección automática que es difícil de debuggear; RLS de Postgres acopla a un motor y complica testing. El costo del filter explícito es una línea de código por método de repo — aceptable a cambio de claridad.

Para evitar olvidos:
- Mixin `TenantScopedRepository` que provee helpers + assertions.
- Tests obligatorios que prueban "despacho A no ve datos del despacho B".
- Type del parámetro `despacho_id` no-opcional (rompe en compile-time si se omite).

## Tablas a crear (esquema inicial)

### Catálogo global (sin `despacho_id`)

| Tabla | PK | Notas |
|---|---|---|
| `camara` | `id` (StrEnum value) | `HCDN`, `HSN`. Catálogo lookup. |
| `legislador` | `slug` | Padrón vendored del Observatorio. Refresh por reseed. |
| `bloque` | `id UUID` | Bloque por cámara. |
| `comision` | `id UUID` | Catálogo de comisiones. |
| `expediente` | `id UUID` | Con UNIQUE `(numero, origen, anio, camara)`. |
| `tramite_evento` | `id UUID` | Append-only. FK a expediente. |
| `firmante` | `id UUID` | FK a expediente + opcional legislador.slug. |
| `giro` | `id UUID` | FK a expediente + comision. |

### Tenant-scoped (con `despacho_id NOT NULL`)

| Tabla | PK | Notas |
|---|---|---|
| `despacho` | `id UUID` | El tenant en sí. Tiene `legislador_titular_slug` (FK). |
| `usuario` | `id UUID` | Usuario humano. `auth_provider_id` para Clerk. |
| `membresia_despacho` | composite `(usuario_id, despacho_id)` | Rol del usuario en el despacho. |
| `seguimiento_expediente` | `id UUID` | `(despacho_id, expediente_id)` único. |
| `nota_interna` | `id UUID` | Notas privadas. Contenido cifrado en reposo (futuro). |
| `alerta` | `id UUID` | Configuración de alerta. |
| `audit_log` | `id UUID` | Cambios en estado de seguimiento. Append-only. |

## Alternativas consideradas

### ID strategy

- **Auto-increment int**: descartado por leak de conteo (saber `id=1234` revela tamaño aproximado del sistema).
- **UUID v4**: random, no sortable por tiempo. UUID v7 es estrictamente superior para nuestros casos.
- **NanoID / ULID**: alternativas modernas; UUID v7 elegida porque tiene soporte nativo en Postgres y stdlib Python.

### Mapeo ORM

- **SQLAlchemy directo sobre el dominio**: menos boilerplate pero rompe el principio hexagonal. Si en el futuro queremos cambiar ORM o agregar otro backend (Mongo, raw SQL), el dominio cambia. Descartado.
- **Active Record**: ni siquiera considerado, rompe completamente la separación.

### Snapshots

- **Versionado completo** (cada captura del scraper = row nueva): descartado por costo de storage y complejidad de queries. Reconsiderar en v3 si aparece feature de "audit forense" o "diff temporal".

### Tenancy

- **Event listener SQLAlchemy** (`@event.listens_for(Session, "do_orm_execute")`): magia automática, difícil de debuggear. Si falla, todos los despachos ven todos los datos. Demasiado riesgo.
- **Postgres RLS**: secure pero acopla a Postgres, complica integration tests (cada test necesitaría `SET ROLE`), y reduce portabilidad. Descartado por ahora.

## Consecuencias

### Que ganamos

- Dominio sigue limpio de SQLAlchemy (regla hexagonal preservada).
- Tenancy isolation explícita y testeable.
- IDs sortables por tiempo (mejor performance).
- Audit log da trazabilidad sin costo de versionado completo.

### Que aceptamos como costo

- **Boilerplate de mappers**: para cada entidad nueva hay que escribir `to_domain` y `from_domain`. Mitigación: helper genérico cuando aparezca repetición real.
- **Riesgo de olvidar el filter de `despacho_id`** en un repo nuevo. Mitigación: linter casero + tests obligatorios de aislamiento por despacho.
- **Audit_log es solo append-only**: si un cambio se hace fuera del repo (ej. update manual en DB), no queda en audit. Aceptable: el MVP asume que todas las mutaciones pasan por la app.

### Lo que esta decisión bloquea

Cambios estructurales requieren ADR nuevo que supersede a éste:
- Cambiar de "current state + audit" a snapshots versionados.
- Cambiar de filter explícito a event listener.
- Cambiar de UUID v7 a otro ID scheme.

Cambios admitidos sin nuevo ADR:
- Agregar tablas o columnas (con su migración Alembic).
- Agregar índices.
- Refactor del código de mappers o repos (mientras preserve los principios).

## Próximos pasos

1. Implementar el infrastructure layer:
   - `praxis/infrastructure/persistence/base.py` — Base + helpers de UUID v7 + TenantScopedMixin.
   - `praxis/infrastructure/persistence/models.py` — ORM models para entidades existentes.
   - `praxis/infrastructure/persistence/mappers.py` — to/from domain.
   - `praxis/infrastructure/persistence/repositories/` — un repo por agregado.
2. Migraciones Alembic: una por feature (no monolítica).
3. Puertos en `praxis/application/ports.py`: `ExpedienteRepository`, `LegisladorRepository`, etc.
4. Tests de aislamiento por despacho como parte obligatoria de cada repo tenant-scoped.

Implementación se reparte en features 7, 12, 13 (auth+tenancy, seguimiento, asignación) y posibles features de plumbing (ej. "primer batch de migraciones") según orden que se acuerde.
