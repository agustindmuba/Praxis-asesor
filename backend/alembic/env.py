"""Entorno de Alembic — configurado para SQLAlchemy 2.0 async.

Se ejecuta vía `uv run alembic upgrade head` (o cualquier otro comando alembic)
desde la carpeta `backend/`.

La URL de la DB se toma de `praxis.config.get_settings().database_url`, NO de
`alembic.ini`. Esto centraliza la configuración y respeta el .env.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from praxis.config import get_settings

# Acceso al config de alembic.ini.
config = context.config

# Override de la URL con la del .env (vía pydantic-settings).
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# target_metadata: se rellena cuando existan modelos SQLAlchemy declarados.
# Ejemplo futuro:
#   from praxis.infrastructure.db.models import Base
#   target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo 'offline' (sin engine real, emite SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Ejecuta migraciones sobre una conexión sync (envuelta dentro del async)."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crea un engine async, ejecuta migraciones, dispose."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Punto de entrada estándar — usa el engine async."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
