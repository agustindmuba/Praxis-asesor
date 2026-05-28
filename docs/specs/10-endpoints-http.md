# Spec 10 — Endpoints HTTP del MVP

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/15-ficha-http`

## Contexto

Tenemos todas las piezas: dominio, persistencia tenant-scoped, búsqueda
filtrada, auth + multi-tenancy. Falta exponer una API HTTP que el frontend
pueda consumir.

Esta feature mete los primeros endpoints útiles para el flujo central del
asesor:

1. **Saber quién soy** (`/me`).
2. **Buscar expedientes** (`/expedientes` con filtros).
3. **Ver la ficha de un expediente** (`/expedientes/{id}`).
4. **Manipular seguimientos del despacho** (`POST /seguimientos`, etc).

## Decisiones (chat 2026-05-28)

1. **DTOs**: Pydantic v2 separados del dominio. Carpeta `api/schemas/`.
   `model_config = ConfigDict(from_attributes=True)` para mappear desde
   los dataclasses del dominio. Mantiene el dominio puro.
2. **Filtros de query string**: modelo Pydantic recibido vía
   `Annotated[Filtros, Query()]`. FastAPI parsea, valida y documenta.
3. **Auth**: todos los endpoints excepto `/health`, `/ready` y `/docs`
   van detrás del dep `current_context` (de feat/14).

## Endpoints

### `GET /me`

Devuelve el `RequestContext` resuelto.

Response 200:

```json
{
  "usuario": {"id": "...", "email": "...", "nombre": "..."},
  "despacho": {"id": "...", "nombre": "..."},
  "rol": "asesor"
}
```

### `GET /expedientes`

Búsqueda + filtros + paginación. Wraps `ExpedienteRepository.buscar(query)`.

Query params (todos opcionales):

- `texto`, `anio`, `tipo`, `camara`, `origen`, `estado`
- `autor_nombre`, `comision`
- `fecha_ingreso_desde`, `fecha_ingreso_hasta`
- `limit` (1..200, default 50), `offset` (>=0, default 0)

Response 200:

```json
{
  "items": [
    {"id": "...", "numero": {"numero": 100, "origen": "D", "anio": 2024, "camara": "HCDN"},
     "titulo": "...", "estado": "en_comision", ... }
  ],
  "total": 234,
  "limit": 50,
  "offset": 0
}
```

Decisión: la respuesta NO incluye `firmantes/giros/tramite` para ahorrar
payload — eso vive en la ficha individual.

### `GET /expedientes/{id}`

Ficha completa con relaciones. Si el despacho activo sigue ese expediente,
incluye el `seguimiento` embebido (id, prioridad, responsable, archivado).

Response 200:

```json
{
  "id": "...",
  "numero": {...},
  "titulo": "...",
  "sumario": "...",
  "estado": "en_comision",
  "fecha_ingreso": "2024-05-01",
  "fecha_caducidad": "2026-04-30",
  "firmantes": [...],
  "giros": [...],
  "tramite": [...],
  "seguimiento": {
    "id": "...",
    "prioridad": "alta",
    "responsable_id": "...",
    "archivado": false
  } | null
}
```

Si el expediente no existe → 404.

### `POST /seguimientos`

Body: `{"expediente_id": UUID, "prioridad": "alta|media|baja"?}`.

Crea un `SeguimientoExpediente` con `despacho_id = ctx.despacho.id`.

Response 201 con el seguimiento creado.

Errores:
- 404 si el expediente_id no existe.
- 409 si el despacho ya sigue ese expediente (UNIQUE constraint).

### `PATCH /seguimientos/{id}`

Body: `{"responsable_id": UUID | null}` o `{"archivado": true}`.

Tenant isolation: si el seguimiento_id no pertenece al despacho activo,
devolvemos 404 (no leakemos existencia).

Response 200 con el seguimiento actualizado.

### `DELETE /seguimientos/{id}`

Por ahora **archivamos** en lugar de borrar (soft delete = mismo comportamiento
que PATCH archivado=true). Esto preserva historial.

Response 204.

## Estructura del código

```
backend/praxis/api/
├── main.py                # FastAPI app + lifespan
├── deps.py                # current_context, get_session, ...
├── schemas/
│   ├── __init__.py        # re-exports
│   ├── auth.py            # MeResponse
│   ├── expediente.py      # ExpedienteResumen, ExpedienteFicha, NumeroExpedienteDTO, ...
│   ├── seguimiento.py     # SeguimientoDTO, CrearSeguimientoBody, ActualizarSeguimientoBody
│   └── busqueda.py        # FiltrosExpediente (query model), ResultadoBusquedaDTO
└── routers/
    ├── __init__.py
    ├── auth.py            # /me
    ├── expedientes.py     # /expedientes, /expedientes/{id}
    └── seguimientos.py    # /seguimientos
```

## Convenciones

- Errores de auth → ya manejados por `current_context` (401/403).
- Recursos no encontrados → 404 con body `{"detail": "expediente no encontrado"}`.
- Conflictos de unicidad → 409.
- Validación Pydantic → 422 (default FastAPI).
- Headers: respuesta JSON, sin cookies (auth via Bearer).

## Out of scope

- Endpoints de admin (crear despacho, invitar usuario): vienen con el
  webhook + onboarding.
- Listar/agregar notas internas (notas son feature aparte).
- Endpoints de alertas / suscripciones.
- WebSocket / SSE para notificaciones live.

## Tests

Por endpoint:
- 1 happy con auth y tenant correctos.
- 1 error de auth (sin token, o token mal).
- 1 error de tenant si aplica (despacho B accediendo a recurso de A).
- Casos específicos: 404, 409, validaciones.

Con `TestClient` + override de `get_session` y `get_auth_provider` (igual
que en feat/14 `test_auth_dep.py`).
