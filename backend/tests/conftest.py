"""Fixtures globales y bootstrap de tests.

Este archivo se ejecuta ANTES de cualquier import de `praxis.*`. Aprovechamos
eso para fijar variables de entorno de prueba sin depender de un `.env` real.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

# --- Bootstrap del entorno de tests --------------------------------------------------
# Settings tiene campos required (DATABASE_URL, REDIS_URL). Si no están seteados,
# importar praxis.config falla. Los seteamos a valores que funcionan contra el
# docker-compose local. Para tests que NO requieren los servicios reales, los
# valores existen para que las imports pasen; los tests con marker `integration`
# son los que efectivamente los usan.

os.environ.setdefault("ENV", "dev")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://praxis:praxis@localhost:5432/praxis_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# --- Fixtures comunes ----------------------------------------------------------------

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Cliente HTTP async apuntando a la app FastAPI en proceso (sin servidor)."""
    from praxis.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
