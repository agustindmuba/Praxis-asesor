# `backend/tests`

Suite de tests del backend. Estructura por tipo de test.

## Layout

```
tests/
├── conftest.py          # bootstrap de env vars + fixtures globales
├── unit/                # tests puros, sin I/O
│   └── test_*.py
├── integration/         # tests con servicios reales (DB, Redis, HTTP)
│   └── test_*.py
└── README.md
```

## Convenciones

- **Markers**: cada test declara `@pytest.mark.unit` o `@pytest.mark.integration`. Definidos en `pyproject.toml`.
- **Tests unitarios**: no tocan red ni DB. Usan fakes/mocks si necesitan dependencias. Cobertura objetivo: 80% en `domain/` y `application/`.
- **Tests de integración**: requieren `docker compose up -d` corriendo. Usan la base `praxis_test` para no ensuciar `praxis`.
- **Async**: por default todos los tests son async (`asyncio_mode = "auto"` en pytest config).
- **Fixtures globales** en `conftest.py`; fixtures específicas en `conftest.py` por subdirectorio.

## Comandos

```bash
# Todos los tests
uv run pytest

# Solo unitarios
uv run pytest -m unit

# Solo integración
uv run pytest -m integration

# Con coverage
uv run pytest --cov

# Un test puntual
uv run pytest tests/unit/test_config.py::test_settings_loads_from_env -v
```

## Convención para futuros tests

- **Tests de contrato de scrapers** (HCDN, HSN): viven en `tests/integration/scrapers/` con fixtures de HTML/JSON real capturado. Se actualizan cuando cambia el portal oficial.
- **Tests de migraciones**: comprobar que `alembic upgrade head` aplica y `downgrade base` revierte limpio. Se agrega en cuanto haya migraciones reales.
- **Tests de aislamiento multi-tenant**: verificar que un despacho NO ve datos de otro. Crítico para seguridad.
