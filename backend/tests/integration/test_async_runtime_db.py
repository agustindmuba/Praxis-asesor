"""Test de integración del fix de event loop (feat-42.11 / regresión de feat-42.9).

Reproduce el bug original: dos tasks Celery seguidas que tocan la DB
async rompían con `'NoneType' object has no attribute 'send'` porque
el `engine` global quedaba atado al loop de la primera task.

Si este test falla con ese error, alguien rompió el helper
`run_task_async`. Necesita Postgres up (docker compose).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.queue._async_runtime import run_task_async

pytestmark = pytest.mark.integration


async def _query_simple() -> int:
    """Toca la DB de forma representativa: abre sesión, ejecuta query."""
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        result = await session.execute(text("SELECT 1"))
        return int(result.scalar() or 0)


def test_dos_invocaciones_consecutivas_con_db_no_rompen() -> None:
    """**Test del bug feat-42.9.** Antes de `run_task_async`, esto
    rompía en la 2ª llamada con `AttributeError: 'NoneType' object
    has no attribute 'send'`. Si vuelve a romper, alguien tocó el
    helper sin entender el invariant."""
    a = run_task_async(_query_simple())
    b = run_task_async(_query_simple())
    assert a == 1
    assert b == 1


def test_tres_invocaciones_consecutivas_con_db() -> None:
    """3+ invocaciones para confirmar que no es solo coincidencia."""
    valores = [run_task_async(_query_simple()) for _ in range(3)]
    assert valores == [1, 1, 1]


def test_invocacion_con_excepcion_no_envenena_la_siguiente() -> None:
    """Si una task tira excepción, la siguiente debe poder ejecutar
    una query nueva sin colgar conexiones del loop anterior."""
    async def _que_tira() -> int:
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            raise RuntimeError("simulando fallo en task")

    with pytest.raises(RuntimeError, match="simulando fallo"):
        run_task_async(_que_tira())

    # Después del fallo, la siguiente task debe poder hablarle a la DB.
    assert run_task_async(_query_simple()) == 1
