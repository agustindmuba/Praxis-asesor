"""Embedder local con sentence-transformers (feat-42.6).

Carga lazy del modelo. Modelo elegido:
`paraphrase-multilingual-MiniLM-L12-v2` (384 dims, ~120MB).
Suporta ES nativo, performance adecuada para corpus jurídico de
~5000 chunks. Sin dependencia de API externa.

Singleton por proceso: el modelo se baja la primera vez (~120MB)
desde HuggingFace, después queda en cache local.

**IMPORTANTE — Issue conocido (feat-42.6 v1)**:
PyTorch instala hilos OpenMP/MKL al cargarse, lo cual choca con
los greenlets de asyncpg/SQLAlchemy en el mismo proceso. Después
de la primera llamada a `embeber_textos` o `cargar_modelo`, otros
endpoints async pueden romperse con `MissingGreenlet`.

**Resolución (feat-42.8)**: el código async del API NUNCA llama a
`embeber_textos` directamente. Usa el wrapper
`praxis.infrastructure.rag.embedder_async.embeber_textos_async`, que
despacha al worker Celery `tasks_rag.embeber_textos_task`. Sólo el
worker carga PyTorch.

Este módulo (`embedder.py`) sigue existiendo para:
- Scripts CLI sin async loop (ej. `scripts/cargar_corpus_normativo.py`).
- El proceso worker Celery, que lo importa de forma aislada.

Workaround heredado: limitamos threads de OpenMP/MKL/torch a 1 ANTES
de importar PyTorch (defense-in-depth, por si alguien lo importa en
un contexto no esperado).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

# ---- Pinear concurrencia ANTES de cargar torch ----
# Estas variables tienen que estar seteadas antes del primer `import
# torch` para que el subsistema OpenMP/MKL respete el límite. Si
# alguien importa torch antes que este módulo, queda inefectivo.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

MODELO_DEFAULT = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_lock = threading.Lock()
_modelo: "SentenceTransformer | None" = None


def cargar_modelo(nombre: str = MODELO_DEFAULT) -> "SentenceTransformer":
    """Devuelve el modelo singleton, lo carga lazy si hace falta."""
    global _modelo
    if _modelo is not None:
        return _modelo
    with _lock:
        if _modelo is not None:
            return _modelo
        # Pinear torch threading ANTES del import.
        try:
            import torch
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        from sentence_transformers import SentenceTransformer
        log.info("Cargando modelo de embeddings %s ...", nombre)
        _modelo = SentenceTransformer(nombre)
        log.info("Modelo cargado.")
        return _modelo


def embeber_textos(textos: list[str]) -> list[list[float]]:
    """Devuelve embeddings normalizados (cosine-ready) para cada texto."""
    if not textos:
        return []
    modelo = cargar_modelo()
    arr = modelo.encode(
        textos,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [v.tolist() for v in arr]
