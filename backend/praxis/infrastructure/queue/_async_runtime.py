"""Runtime helper para correr corutinas dentro de tasks Celery (feat-42.9).

Por qué existe:
- El `engine` async global de SQLAlchemy queda atado al primer event
  loop que lo usa. Al usar `asyncio.run` en una task Celery con pool
  `solo`, el siguiente run crea un loop NUEVO pero el pool de
  conexiones de asyncpg quedó atado al anterior. En Windows esto se
  manifiesta como `AttributeError: 'NoneType' object has no
  attribute 'send'` (proactor del loop anterior, ya cerrado).
- Solución: cada task corre en su propio loop nuevo, y al terminar
  dispose el engine para que sus conexiones se cierren limpias en
  ese loop. El próximo run crea engine implícitamente al volver a
  abrir una sesión.

Uso desde las tasks:

    from praxis.infrastructure.queue._async_runtime import run_task_async

    @celery_app.task(name="praxis.x.y")
    def mi_task() -> int:
        return run_task_async(_mi_task_async())

`run_task_async` toma una corutina y la ejecuta. Garantiza:
1. Loop nuevo por invocación.
2. `engine.dispose()` en el finally (limpia el pool en este loop).
3. Loop cerrado al final.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def run_task_async(coro: Coroutine[object, object, T]) -> T:
    """Corre `coro` en un event loop nuevo + dispose del engine al final.

    Pensado específicamente para tasks Celery sobre Windows/solo pool,
    donde el engine global se atasca al primer loop. En Linux/forking
    el efecto es transparente (el dispose es no-op si no hay
    conexiones abiertas).
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            # Import lazy para evitar import cycles (engine importa este
            # módulo? — no, pero por las dudas).
            from praxis.infrastructure.db.engine import engine
            loop.run_until_complete(engine.dispose())
        except Exception as exc:    # noqa: BLE001
            log.warning("engine.dispose falló: %s", exc)
        asyncio.set_event_loop(None)
        loop.close()
