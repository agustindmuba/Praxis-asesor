"""Tareas Celery del subsistema RAG (feat-42.8).

Aísla la carga de PyTorch / sentence-transformers en un proceso worker
separado del API FastAPI. Esto resuelve el conflicto documentado en
feat-42.6: PyTorch instala hilos OpenMP/MKL al cargarse y choca con
los greenlets de asyncpg en el mismo proceso, rompiendo endpoints
async siguientes con `MissingGreenlet`.

Ejecutar el worker RAG (recomendado en dev y prod):

    uv run celery -A praxis.infrastructure.queue.celery_app worker \\
        --loglevel=info --pool=solo --queues=rag

`--pool=solo` mantiene 1 sólo proceso (carga del modelo es ~120MB —
no queremos N réplicas) y `--queues=rag` permite dedicar workers
distintos para RAG vs scraping/BO/noticias si la carga lo justifica.

La task se encolará en queue `rag`; si no especificamos queue distinto,
Celery la encolará en `celery` (default) y cualquier worker la
consume — útil para entornos chicos donde un único worker hace todo.
"""

from __future__ import annotations

import logging

from praxis.infrastructure.queue.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="praxis.rag.embeber_textos",
    bind=True,
    autoretry_for=(),       # PyTorch errors no son transitorios
    max_retries=0,
)
def embeber_textos_task(  # type: ignore[no-untyped-def]
    self, textos: list[str],
) -> list[list[float]]:
    """Ejecuta `embeber_textos` en el proceso worker.

    El import de `embeber_textos` se hace ACÁ adentro (no en el módulo)
    para que el API FastAPI nunca cargue PyTorch — solo el worker lo
    importa la primera vez que se despacha esta task.
    """
    # Import lazy: solo dentro del worker se carga sentence-transformers.
    from praxis.infrastructure.rag.embedder import embeber_textos

    if not textos:
        return []
    log.info("embeber_textos: procesando %d textos", len(textos))
    return embeber_textos(textos)
