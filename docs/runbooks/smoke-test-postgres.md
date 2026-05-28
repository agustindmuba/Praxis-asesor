# Runbook — Smoke test contra Postgres real

**Cuándo correrlo:** después de cambios grandes en persistencia o auth,
antes de un piloto, y al menos una vez por release.

**Por qué:** los tests del repo usan SQLite in-memory por velocidad. Hay
diferencias sutiles con Postgres (NULLS LAST, ILIKE, tipos UUID, FK
comportamiento) que solo se notan corriendo contra Postgres real.

---

## Prerequisitos

- Docker Desktop (o motor docker) instalado y corriendo.
- `uv` instalado.
- Working directory: raíz del repo `praxis-asesor`.

## Pasos

### 1. Levantar el stack local

```bash
docker compose up -d
docker compose ps
# postgres y redis deberían estar "healthy" en ~10 segundos
```

Si es la primera vez, esperá a que postgres complete el `start_period`
del healthcheck (10s). Verificá con:

```bash
docker compose logs postgres | tail -5
# debería terminar en: "database system is ready to accept connections"
```

### 2. Configurar `.env` del backend

Si no existe, crear `backend/.env` con (al menos):

```env
ENV=dev
DATABASE_URL=postgresql+asyncpg://praxis:praxis@localhost:5432/praxis
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

(`backend/.env.example` ya tiene este contenido.)

### 3. Aplicar migrations

```bash
cd backend
uv run alembic upgrade head
```

Deberías ver: `INFO  [alembic.runtime.migration] Running upgrade ... ->` por
cada migration aplicada.

Verificá las tablas:

```bash
docker compose exec postgres psql -U praxis -d praxis -c "\dt"
# Esperado: despacho, expediente, firmante, giro, membresia_despacho,
# seguimiento_expediente, tramite_evento, usuario, alembic_version
```

### 4. Correr el smoke test

```bash
cd backend
uv run python -m scripts.smoke_test
```

Salida esperada (todo verde):

```
[smoke] Conectando a localhost:5432

[smoke] Sembrando estado...
  → Despacho: <uuid>
  → Usuario:  <uuid>
  → Exp 1:    <uuid>
  → Exp 2:    <uuid>

[smoke] Ejecutando hits HTTP...
  ✓ GET /me → Smoke Test User @ Smoke Test Despacho (jefe_asesores)
  ✓ GET /expedientes → 2 expedientes
  ✓ GET /expedientes?texto=salud → 1 matches
  ✓ GET /expedientes/{id} → Smoke Test Salud, sin seguimiento
  ✓ POST /seguimientos → 201 (id=...)
  ✓ GET ficha re-check → seguimiento embebido con prioridad=alta
  ✓ Sin token → 401
  ✓ Sin X-Despacho-Id → 400
  ✓ Despacho ajeno → 403 (tenant isolation)

============================================================
  ✓ Smoke test OK — 9 checks pasaron
============================================================
```

Exit code 0. Cualquier assert que falle aborta el script con código 1.

### 5. Inspección manual (opcional)

Si querés hacer hits por tu cuenta:

```bash
# Levantar el server en otra terminal:
cd backend
uv run python -m praxis.api.main  # arranca en :8000
```

Y desde otra terminal:

```bash
# Obtener los UUIDs del seed:
cd backend
uv run python -m scripts.seed_inicial \
    --email "ana@test.local" \
    --nombre "Ana Test" \
    --clerk-id "user_ana"

# Te imprime DESPACHO_ID y USUARIO_ID.
# Para auth real necesitás un JWT de Clerk con sub=user_ana, o
# usar el approach del smoke test (override del AuthProvider).
```

---

## Reset

Para empezar de cero:

```bash
docker compose down -v   # elimina volúmenes — borra todos los datos
docker compose up -d
cd backend && uv run alembic upgrade head
uv run python -m scripts.smoke_test
```

---

## Troubleshooting

### "could not connect to server: Connection refused"

El docker-compose no está corriendo o Postgres todavía no terminó el
`start_period`. Esperá 10s y reintentá, o `docker compose logs postgres`.

### "relation \"despacho\" does not exist"

Falta correr `alembic upgrade head` después de levantar Postgres.

### El smoke test pasa los 6 primeros checks pero falla en POST

Probablemente la migration de `seguimiento_expediente` no se aplicó.
Verificá: `docker compose exec postgres psql -U praxis -d praxis -c
"\d seguimiento_expediente"`.

### Quiero correr el smoke test contra un Postgres remoto

Cambiá `DATABASE_URL` en `backend/.env` apuntando al host remoto.
El script no asume nada de docker-compose puntual — solo lee `settings`.

---

## Por qué un smoke test y no solo los tests de integración

Los tests de integración usan SQLite in-memory por velocidad (`27s` para
385 tests). Eso significa:

1. Algunos comportamientos Postgres-específicos (ILIKE genuino, NULLS LAST
   nativo, tipos UUID binarios) NO se ejercitan.
2. Los 2 tests xfailed del webhook (ver `feat/16-webhook-clerk`) no se
   pueden validar contra SQLite por un bug del bridge aiosqlite.
3. Las migrations Alembic se aplican siempre contra Postgres en CI/prod,
   no contra SQLite. Probarlas localmente cuenta.

El smoke test cubre esos 3 huecos.
