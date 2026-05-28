"""Engine + sessionmaker async de SQLAlchemy 2.0.

Instanciados a nivel de módulo. Toda capa que necesite hablar con la DB
debe pedir una `AsyncSession` vía `get_session` (dependency injection),
nunca instanciar engines propios.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from praxis.config import get_settings


def _make_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        echo=settings.is_dev,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# Instancia única por proceso. En tests, sobrescribir con un engine de SQLite
# o un Postgres test container, vía monkeypatch sobre este símbolo.
engine: AsyncEngine = _make_engine()

# Factory de sesiones async. `expire_on_commit=False` evita que los atributos
# se recarguen tras commit (útil cuando devolvemos objetos al endpoint).
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI: yield una sesión async y la cierra al final del request."""
    async with SessionLocal() as session:
        yield session
