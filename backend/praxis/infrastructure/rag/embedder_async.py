"""Wrapper async del embedder (feat-42.8).

Despacha `embeber_textos` a un worker Celery dedicado y await el
resultado en un thread, para que el event loop del API FastAPI NO
cargue PyTorch.

Por qué este wrapper existe:
- `embeber_textos` carga sentence-transformers, que instala hilos
  OpenMP/MKL al ejecutarse. Esos hilos chocan con los greenlets de
  asyncpg/SQLAlchemy en el mismo proceso → siguiente endpoint async
  rompe con `MissingGreenlet`. Documentado en feat-42.6.
- Mover la inferencia a un worker Celery aislado resuelve el conflicto:
  el API queda libre de PyTorch.
- `task.delay().get()` es bloqueante. Usamos `asyncio.to_thread` para
  que el await no bloquee el event loop del API.

Para tests: monkeypatchear el símbolo `embeber_textos_task` en este
módulo con un fake que devuelve un handle `.delay() / .get()` con
vectores determinísticos (ver `tests/unit/infrastructure/test_embedder_async.py`).
No hace falta levantar Celery ni PyTorch.
"""

from __future__ import annotations

import asyncio
import logging

from praxis.infrastructure.queue.tasks_rag import embeber_textos_task

log = logging.getLogger(__name__)

# Timeout amplio: la primera llamada baja ~120MB de HuggingFace si el
# cache no existe. Llamadas siguientes son ~50-200ms para corpus chico.
EMBEDDER_TIMEOUT_SEG = 120


async def embeber_textos_async(textos: list[str]) -> list[list[float]]:
    """Despacha la inferencia al worker Celery `rag` y devuelve los
    embeddings normalizados (cosine-ready).

    Bloqueo: el `.get()` síncrono de Celery se ejecuta en un thread
    via `asyncio.to_thread` para que el event loop del API no se
    detenga. El timeout (`EMBEDDER_TIMEOUT_SEG`) protege contra el
    caso "no hay worker corriendo".
    """
    if not textos:
        return []

    log.debug("embeber_textos_async: despachando %d textos", len(textos))
    # `.delay()` y `.get()` son síncronos. `to_thread` los corre fuera
    # del event loop.
    result_handle = embeber_textos_task.delay(textos)
    return await asyncio.to_thread(
        result_handle.get,
        timeout=EMBEDDER_TIMEOUT_SEG,
    )
