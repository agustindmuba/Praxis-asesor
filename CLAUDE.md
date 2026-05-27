# CLAUDE.md — Praxis Asesor

> Este archivo es la **memoria persistente del proyecto**. Claude Code lo lee al inicio de cada sesión. Mantenerlo actualizado es responsabilidad del equipo: cada decisión arquitectónica, convención o aprendizaje relevante debe quedar acá.

---

## 1. Qué es Praxis Asesor

Praxis Asesor es un software profesional para asesores parlamentarios del Congreso Nacional Argentino (Honorable Cámara de Diputados de la Nación — HCDN — y Honorable Senado de la Nación — HSN). Cumple tres roles:

- **Organizativo**: gestiona expedientes, tareas, plazos, agenda del despacho.
- **Informativo**: provee datos confiables y actualizados de actividad parlamentaria, legisladores, comisiones, trámite de proyectos.
- **Proactivo**: sugiere acciones, anticipa eventos, asiste en redacción y análisis.

El MVP se enfoca en el rol **informativo**, específicamente en **seguimiento de expedientes + alertas de trámite**.

## 2. Usuario objetivo del MVP

**Jefe de asesores** de un despacho de legislador (diputado o senador), que coordina un equipo de 2-6 asesores junior y necesita visión transversal del despacho.

Esto implica que el sistema es **multi-usuario por despacho desde el día 1**: roles, asignación de expedientes, visibilidad jerárquica.

## 3. Alcance del MVP (qué SÍ y qué NO)

### SÍ entra en el MVP

- Ingesta automatizada de expedientes parlamentarios de HCDN y HSN.
- Búsqueda y filtrado de expedientes (por autor, comisión, estado, fecha, palabras clave, tema).
- Ficha completa por expediente: texto del proyecto, firmantes, giros, dictámenes, estado actual, historial de trámite.
- Seguimiento personalizado: "marcar" expedientes de interés del despacho.
- Alertas configurables: cambio de estado, nuevo dictamen, ingreso a orden del día, votación en recinto.
- Asignación interna: el jefe de asesores asigna expedientes a asesores junior.
- Vista de "tablero del despacho": qué está siguiendo cada miembro, plazos próximos.
- Notas internas por expediente (privadas del despacho).

### NO entra en el MVP (futuras versiones)

- Fichas de legisladores con análisis de votaciones (v2).
- Asistente de redacción con IA (v2/v3).
- Briefings automáticos pre-sesión (v3).
- Análisis predictivo (coautorías sugeridas, probabilidad de dictamen, etc.) (v3).
- Integración con calendario externo (Google/Outlook) (v2).
- App móvil (post-MVP).
- Gestión de pedidos del distrito (post-MVP).

## 4. Decisiones arquitectónicas clave

### Despliegue agnóstico (CRÍTICO)

El producto debe poder desplegarse en **SaaS cloud, SaaS con datos en Argentina, o self-hosted en infraestructura del cliente**. Esta decisión condiciona toda la arquitectura.

**Regla de oro**: la lógica de negocio NO depende de servicios cloud específicos. Toda dependencia externa (storage, queue, auth, email, secretos) se accede vía **interfaces/puertos**, con adaptadores intercambiables. Esto es arquitectura hexagonal (ports & adapters).

Ejemplo: el código de negocio llama a `EmailSender.send(...)`, no a `boto3.client("ses")`. El adaptador concreto (SES, SMTP, SendGrid) se inyecta por configuración.

### Stack inicial (sujeto a confirmación en ciclo 1)

- **Backend**: Python 3.12 + FastAPI + Pydantic v2.
- **Base de datos**: PostgreSQL 16 + pgvector (para RAG futuro).
- **ORM**: SQLAlchemy 2.0 (async) + Alembic para migraciones.
- **Cola de tareas**: Celery + Redis (scraping, alertas, ingestas).
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui.
- **Auth**: Clerk (por velocidad inicial; abstraído tras interfaz para poder migrar).
- **Despliegue dev**: Railway o Render. Producción: a definir según cliente.
- **IA**: API de Anthropic (Claude Sonnet por defecto, Opus para razonamiento complejo).

### Estructura del repo

Monorepo con dos paquetes principales:

```
praxis-asesor/
├── CLAUDE.md
├── PRODUCT.md
├── ARCHITECTURE.md
├── README.md
├── backend/
│   ├── praxis/
│   │   ├── domain/        # entidades, lógica de negocio pura
│   │   ├── application/   # casos de uso, servicios
│   │   ├── infrastructure/# adaptadores: db, scrapers, email, etc.
│   │   ├── api/           # endpoints FastAPI
│   │   └── config.py
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
└── docs/
    ├── adr/               # Architecture Decision Records
    ├── glosario.md        # términos parlamentarios
    └── data-sources.md    # documentación de fuentes de datos
```

### Modelo de datos central (esqueleto)

Entidades núcleo del MVP:

- **Camara**: HCDN | HSN.
- **Legislador**: datos personales, bloque actual, comisiones, mandato.
- **Bloque**: agrupación política en una cámara.
- **Comisión**: permanente o especial, por cámara.
- **Expediente**: proyecto de ley/resolución/declaración/comunicación. Tiene número, autor(es), fecha de ingreso, estado, giros, dictámenes, texto.
- **Trámite**: evento en la vida de un expediente (ingreso, giro a comisión, dictamen, OD, sanción, etc.). Inmutable, append-only.
- **Despacho** (tenant): unidad organizativa del cliente. Tiene legislador titular, miembros, configuración.
- **Usuario**: persona del despacho. Roles: `jefe_asesores`, `asesor`, `lector`.
- **SeguimientoExpediente**: relación despacho ↔ expediente con metadatos (responsable asignado, prioridad, notas, alertas configuradas).
- **Alerta**: regla configurada por un despacho/usuario para ser notificado de cierto evento.
- **NotaInterna**: anotación privada del despacho sobre un expediente.

### Multi-tenancy

Modelo: **shared database, shared schema, con `despacho_id` como columna discriminadora**. Todo query de aplicación filtra obligatoriamente por `despacho_id` del usuario autenticado. Implementar como middleware/policy a nivel ORM para evitar fugas.

(En el futuro, para clientes self-hosted o que exijan aislamiento físico, podemos migrar a schema-per-tenant o database-per-tenant. La abstracción debe permitirlo.)

## 5. Convenciones de código

### Python (backend)

- Formato: `ruff format` (sucesor de black).
- Lint: `ruff check` con reglas estrictas (E, F, I, N, UP, B, A, C4, SIM, RUF).
- Tipado: anotaciones obligatorias en funciones públicas. `mypy --strict` en `domain/` y `application/`.
- Tests: `pytest` + `pytest-asyncio`. Cobertura objetivo: 80% en `domain/` y `application/`, 60% global.
- Naming: snake_case. Clases: PascalCase. Constantes: UPPER_SNAKE.
- Imports: ordenados por ruff (isort-compatible). Imports absolutos siempre.
- Async-first: toda I/O es async. Excepciones documentadas.
- Sin lógica de negocio en endpoints: el endpoint orquesta, el caso de uso (en `application/`) ejecuta.

### TypeScript (frontend)

- Formato: Prettier.
- Lint: ESLint con `next/core-web-vitals` + reglas estrictas.
- Tipado: TypeScript `strict: true`. Nada de `any` salvo justificación en comentario.
- Componentes: server components por defecto; `"use client"` solo cuando necesario.
- Estado global: minimizar. Preferir URL state, React Query para data fetching.
- Naming: PascalCase para componentes, camelCase para utilidades, kebab-case para archivos de rutas.

### Git

- Ramas: `main` (protegida), `develop`, feature branches `feat/`, `fix/`, `chore/`, `docs/`.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- PRs: review obligatoria antes de merge a `develop` o `main`. CI debe pasar.
- Nada de force-push a ramas compartidas.

### Documentación

- Cada decisión arquitectónica significativa va en `docs/adr/NNNN-titulo.md` (Architecture Decision Record).
- Cada módulo de `infrastructure/` que integra una fuente externa tiene su README explicando contrato, rate limits, errores conocidos.

## 6. Glosario parlamentario (CRÍTICO para el modelo)

Estos términos tienen significados específicos. Claude Code debe usarlos con precisión:

- **Expediente**: documento parlamentario con número único por cámara y año (ej. `1234-D-2025` = Diputados, `S-456/25` = Senado).
- **Giro**: derivación de un expediente a una o más comisiones para su estudio.
- **Dictamen**: opinión escrita de una comisión sobre un expediente. Puede ser de mayoría, minoría, o único.
- **Orden del Día (OD)**: lista de asuntos a tratar en una sesión, publicada con anticipación.
- **Sesión**: reunión del cuerpo (Diputados o Senado) para tratar asuntos. Ordinaria, extraordinaria, especial, de prórroga.
- **Recinto**: ámbito donde se delibera y vota; opuesto a "comisión".
- **Sanción**: aprobación de un proyecto por una cámara (media sanción) o por ambas (sanción definitiva).
- **Insistencia**: ratificación de una cámara frente a modificación de la otra (art. 81 CN).
- **Veto**: rechazo total o parcial del PE a una ley sancionada (art. 83 CN).
- **Caducidad / pérdida de estado parlamentario**: art. 1° Ley 13.640: los proyectos caducan si no son tratados dentro de dos años (en Diputados, una vez prorrogable). Conocido coloquialmente como "el 114 bis" por el artículo del RHCDN que lo regula.
- **Bloque**: agrupación de legisladores de la misma fuerza política. Tiene presidente, secretario, asesores.
- **Interbloque**: alianza de bloques con coordinación común.
- **Mayoría / minoría / unipersonal**: tipos de dictamen según consenso en comisión.
- **Tablas**: tratamiento "sobre tablas" = sin dictamen previo, requiere mayoría calificada (2/3).
- **Moción de preferencia**: pedido de tratar un asunto en una sesión futura específica.
- **Pedido de informes**: facultad parlamentaria (arts. 71 CN y 204 RHCDN) para requerir información al PE.

Mantener este glosario sincronizado con `docs/glosario.md` (versión extendida).

## 7. Fuentes de datos

- **HCDN**: portal oficial `www.diputados.gob.ar`, sistema de información parlamentaria (SIP). Sin API pública oficial; requiere scraping respetuoso.
- **HSN**: portal oficial `www.senado.gob.ar`, sistema "Parlamentario". Mismo escenario.
- **InfoLeg**: `www.infoleg.gob.ar` (Ministerio de Justicia), normativa nacional consolidada.
- **SAIJ**: `www.saij.gob.ar`, base jurídica.

**Reglas de ingesta**:
- Respetar `robots.txt` de cada sitio.
- Rate limit conservador: máx 1 req/segundo por dominio, con backoff exponencial en errores.
- User-Agent identificable y honesto: `PraxisAsesor/0.1 (+contacto@dominio.com)`.
- Cachear agresivamente; nada de re-scrapear lo que no cambió.
- Documentar en `docs/data-sources.md` cada endpoint/página utilizada, su estructura, y los campos extraídos.

## 8. Seguridad y privacidad (decisiones iniciales)

- Datos públicos (expedientes, legisladores, trámites): sin restricción de tratamiento.
- Datos del despacho (notas internas, asignaciones, configuración): sensibles. Cifrado en reposo a nivel de columna para `NotaInterna.contenido`. TLS obligatorio en tránsito.
- Cumplimiento Ley 25.326 (Protección de Datos Personales, Argentina): documentar tratamiento, base legal, retención.
- Secretos: nunca en código ni en `.env` versionado. Usar gestor (Doppler, AWS Secrets Manager, o variables del proveedor) tras interfaz.
- Auditoría: toda acción que modifica datos del despacho se loguea en tabla `audit_log` (usuario, acción, entidad, timestamp, diff).

## 9. Cómo trabajamos (workflow Claude Code)

1. **Antes de codear una feature**: leer `PRODUCT.md` y la spec específica de la feature (vive en `docs/specs/`).
2. **Antes de modificar un módulo**: leer su README local si existe.
3. **Antes de cambiar el modelo de datos**: proponer ADR en `docs/adr/`, discutir, decidir, luego migrar con Alembic.
4. **Tests primero cuando hay lógica**: si una función tiene branching no trivial, escribir test antes.
5. **Commits pequeños y conventional**: un commit = un cambio comprensible.
6. **No tocar `main` directamente**: PR siempre.
7. **Dudas de producto o tradeoffs**: parar, preguntar (a Agustín), no improvisar.

## 10. Estado actual del proyecto

- **Ciclo**: 0 (setup).
- **Próximo hito**: ciclo 1 — confirmar stack, generar scaffolding, scraping exploratorio de HCDN y HSN.
- **Riesgos activos**:
  - Cambios estructurales en los portales oficiales de HCDN/HSN romperían scrapers. Mitigación: tests de contrato + monitoreo + adaptadores aislados.
  - Sin equipo técnico senior aún. Mitigación: arquitectura clara desde día 1, incorporar dev senior antes del primer cliente real.
  - Pérdida de estado parlamentario (Ley 13.640) afecta cómo modelamos "expediente vigente". Resolver en ciclo 1.
