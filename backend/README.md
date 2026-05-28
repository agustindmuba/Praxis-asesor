# backend

Servicio Python del Praxis Asesor. Arquitectura hexagonal (ver [`../ARCHITECTURE.md`](../ARCHITECTURE.md)). Stack confirmado en [`../docs/adr/0001-stack-inicial.md`](../docs/adr/0001-stack-inicial.md).

## Estructura

```
backend/
├── pyproject.toml          # deps + config ruff/mypy/pytest/coverage
├── .python-version         # 3.12 (consumido por uv)
├── .env.example            # plantilla de variables (copiar a .env, gitignored)
├── praxis/
│   ├── __init__.py
│   ├── config.py           # Settings con pydantic-settings
│   ├── domain/             # entidades, value objects, reglas puras
│   ├── application/        # casos de uso, puertos
│   ├── infrastructure/     # adaptadores (DB, scrapers, email, queue, ...)
│   └── api/                # endpoints FastAPI
├── tests/                  # unit + integration
└── alembic/                # migraciones (se agrega en task #8)
```

Cada capa tiene su propio `README.md` con responsabilidades y restricciones de dependencias.

## Bootstrap

### 1. Instalar uv

`uv` es el gestor de paquetes y entornos. Reemplaza pip, virtualenv y Poetry.

**Windows (PowerShell)**:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**O vía winget**:
```powershell
winget install --id=astral-sh.uv -e
```

**Verificar**:
```bash
uv --version
```

### 2. Instalar dependencias

Desde la carpeta `backend/`:
```bash
uv sync
```

Esto:
- Crea un virtualenv en `backend/.venv` (no versionado).
- Instala todas las dependencias (producción + desarrollo).
- Genera `backend/uv.lock` (sí versionado).
- Instala el paquete `praxis` en modo editable.

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con valores reales si hace falta.
```

Los defaults del `.env.example` apuntan al `docker-compose.yml` local: Postgres en `localhost:5432`, Redis en `localhost:6379`.

### 4. Levantar servicios de infraestructura

Desde la raíz del repo (no desde `backend/`):
```bash
docker compose up -d
```

Levanta Postgres 16 (con pgvector) y Redis 7 en background.

### 5. Sanity check

```bash
uv run python -c "from praxis.config import get_settings; print(get_settings().env)"
# debe imprimir: dev
```

## Comandos habituales

| Acción | Comando |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy praxis` |
| Tests | `uv run pytest` |
| Tests con coverage | `uv run pytest --cov` |
| Levantar API en dev | `uv run uvicorn praxis.api.main:app --reload` |
| Worker Celery | `uv run celery -A praxis.infrastructure.queue.celery_app worker` |

## Notas

- **Async-first**: todo I/O es asíncrono. No mezclar funciones `def` y `async def` para acceso a DB.
- **Tipado estricto** en `praxis.domain` y `praxis.application` (ver `pyproject.toml`).
- **Cómo agregar una dependencia**: `uv add <paquete>`. Para dev: `uv add --dev <paquete>`.
