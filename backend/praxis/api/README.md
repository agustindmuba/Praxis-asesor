# `praxis.api` — Capa API HTTP

Punto de entrada HTTP del backend. FastAPI.

## Qué vive acá

- `main.py`: instancia de `FastAPI`, montaje de routers, middleware, eventos de ciclo de vida.
- `routers/`: routers por recurso (`expedientes.py`, `despachos.py`, `auth.py`, etc.).
- `deps.py`: dependencias inyectables (sesión DB, usuario actual, despacho actual).
- `schemas/`: modelos Pydantic v2 para entrada y salida HTTP (separados de las entidades de dominio).

## Qué NO vive acá

- Lógica de negocio: los endpoints **orquestan**, no calculan. La regla es:

```python
@router.post("/expedientes/{eid}/seguir")
async def seguir(eid: int, ...):
    return await usecase.execute(eid, ...)  # endpoint = traductor HTTP ↔ caso de uso
```

- Acceso directo a DB, scrapers, email, etc. Todo eso va vía caso de uso, que a su vez va vía puerto.

## Restricciones de dependencias

`praxis.api` **puede** importar de `praxis.domain`, `praxis.application` e `praxis.infrastructure`.
Es la capa más externa: cablea las concretas con los casos de uso (composition root).

## Política de tipado

Modo permisivo. FastAPI + Pydantic generan tipos suficientes; el énfasis de tipado va en `domain/` y `application/`.

## Política de testing

Tests de integración con `httpx.AsyncClient` (FastAPI test client async). Probar contratos HTTP, no recalcular lógica de negocio (eso se prueba en domain/application).
