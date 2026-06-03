"""Smoke test integración: las 16 tablas nuevas (ADR 0006) crean
correctamente desde `Base.metadata` en SQLite in-memory.

No prueba mappers/repos (eso es feat-39.2.C). Solo verifica que el
schema es coherente: tablas + columnas + FKs + índices se materializan
sin errores.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.infrastructure.persistence import models as _models  # noqa: F401
from praxis.infrastructure.persistence.base import Base

pytestmark = pytest.mark.integration


# Las 16 tablas que la migración 20260602_0001 introduce.
TABLAS_NUEVAS = (
    "perfil_interes_despacho",
    "norma_bo",
    "norma_bo_texto",
    "clasificacion_norma_bo",
    "norma_bo_accionable",
    "fuente_noticia",
    "fuente_noticia_despacho",
    "articulo",
    "articulo_hash",
    "clasificacion_articulo",
    "articulo_relevante",
    "mencion",
    "destinatario",
    "plantilla_whatsapp",
    "envio_whatsapp",
    "alerta_mencion_enviada",
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def test_las_16_tablas_existen_en_metadata() -> None:
    """Hit suave: las clases ORM están registradas en Base.metadata."""
    tablas = set(Base.metadata.tables.keys())
    for nombre in TABLAS_NUEVAS:
        assert nombre in tablas, (
            f"Tabla {nombre} no está registrada en Base.metadata "
            f"(¿olvidaste agregar el ORM model?)"
        )


async def test_create_all_construye_las_16_tablas(
    session: AsyncSession,
) -> None:
    """Con la sesión ya levantada (create_all corrió en el fixture), las
    tablas existen en SQLite."""

    def _inspect(sync_conn):  # noqa: ANN001
        return inspect(sync_conn).get_table_names()

    async with session.bind.connect() as conn:   # type: ignore[union-attr]
        tablas = await conn.run_sync(_inspect)

    for nombre in TABLAS_NUEVAS:
        assert nombre in tablas, f"Tabla {nombre} no se creó en SQLite"


async def test_norma_bo_tiene_indices_unicos_clave(
    session: AsyncSession,
) -> None:
    """Confirma que los índices únicos críticos están registrados."""

    def _indexes(sync_conn):  # noqa: ANN001
        ix = inspect(sync_conn).get_indexes("norma_bo")
        return {i["name"]: i for i in ix}

    async with session.bind.connect() as conn:   # type: ignore[union-attr]
        ixs = await conn.run_sync(_indexes)

    assert "uq_norma_bo_identidad_natural" in ixs
    assert ixs["uq_norma_bo_identidad_natural"]["unique"]
    # hash_sumario es índice de búsqueda, NO único: 2 normas distintas
    # pueden tener el mismo sumario corto.
    assert "ix_norma_bo_hash_sumario" in ixs
    assert not ixs["ix_norma_bo_hash_sumario"]["unique"]


async def test_norma_bo_accionable_tiene_pk_compuesta(
    session: AsyncSession,
) -> None:
    """PK compuesta (norma_id, despacho_id) habilita tenant scoping."""

    def _pk(sync_conn):  # noqa: ANN001
        return inspect(sync_conn).get_pk_constraint("norma_bo_accionable")

    async with session.bind.connect() as conn:   # type: ignore[union-attr]
        pk = await conn.run_sync(_pk)

    assert set(pk["constrained_columns"]) == {"norma_id", "despacho_id"}


async def test_envio_whatsapp_tiene_message_id_meta_unique(
    session: AsyncSession,
) -> None:
    """Idempotencia ADR 0008: message_id_meta UNIQUE."""

    def _indexes(sync_conn):  # noqa: ANN001
        ix = inspect(sync_conn).get_indexes("envio_whatsapp")
        return {i["name"]: i for i in ix}

    async with session.bind.connect() as conn:   # type: ignore[union-attr]
        ixs = await conn.run_sync(_indexes)

    assert "ix_envio_whatsapp_message_id_meta" in ixs
    assert ixs["ix_envio_whatsapp_message_id_meta"]["unique"]
