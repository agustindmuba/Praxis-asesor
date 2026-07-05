# Backend Praxis Asesor — imagen multiproceso (uvicorn + celery).
#
# El mismo Dockerfile sirve para 3 servicios distintos vía CMD override
# en docker-compose.prod.yml:
#   - api:    uvicorn praxis.api.main:app --host 0.0.0.0 --port 8000
#   - worker: celery -A praxis.infrastructure.queue.celery_app worker
#   - beat:   celery -A praxis.infrastructure.queue.celery_app beat
#
# uv como package manager (mismo que en local). Se instala vía imagen
# oficial en la stage builder y se copia al runtime.

# ---------- builder ----------
FROM python:3.12-slim AS builder

# uv oficial standalone binary.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema para paquetes que compilan C (pdfplumber via
# pdfminer no compila, pero psycopg2 sí en algunas plataformas; asyncpg
# viene wheel puro, pero mantengo build-essential por seguridad).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala deps primero, sin código, para maximizar cache.
# README.md hace falta porque pyproject.toml lo referencia como `readme`
# y hatchling lo lee al resolver metadata del propio proyecto.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Ahora sí el código, para invalidar cache solo cuando cambia.
COPY praxis ./praxis
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

# libpq5 = runtime de Postgres client (asyncpg no la usa, pero psycopg
# sí si aparece). curl para healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 praxis

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copiamos el venv preparado + código de la stage builder.
COPY --from=builder --chown=praxis:praxis /app /app

USER praxis

EXPOSE 8000

# Default: API. worker/beat overriden en compose.
CMD ["uvicorn", "praxis.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
