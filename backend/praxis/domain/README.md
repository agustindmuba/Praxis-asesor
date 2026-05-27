# `praxis.domain` — Capa Domain

Núcleo del modelo de negocio de Praxis Asesor.

## Qué vive acá

- **Entidades** del dominio parlamentario: `Expediente`, `Tramite`, `Legislador`, `Comision`, `Bloque`, etc.
- **Value objects**: `NumeroExpediente`, `Camara`, `EstadoExpediente`, etc.
- **Reglas de negocio puras**: validaciones, transiciones de estado, cálculos como "fecha de pérdida de estado parlamentario" (Ley 13.640).

## Qué NO vive acá

- Persistencia (SQLAlchemy, repositorios concretos): va en `praxis.infrastructure`.
- HTTP / FastAPI / routers: van en `praxis.api`.
- Casos de uso (orquestación entre entidades): van en `praxis.application`.
- Configuración, logging, secretos.

## Restricciones de dependencias

`praxis.domain` **no puede** importar nada de `praxis.application`, `praxis.infrastructure` ni `praxis.api`. Solo dependencias estándar de Python y libs puras (ej. `pydantic` para value objects, `decimal`, `datetime`).

## Política de tipado

`mypy --strict` activado para todo este módulo (ver `pyproject.toml`). Es la capa más crítica del producto: errores acá se propagan a todo lo demás.

## Política de testing

100% testeable sin mocks ni I/O. Cobertura objetivo: 80%+.
