"""Cargador del corpus normativo argentino desde InfoLEG (feat-42.6).

Baja las 15 normas del `CATALOGO_NORMAS` (Constitución + 14 leyes
estructurales), parsea por artículo, embebbe con
sentence-transformers local, y persiste en `norma_juridica_chunk`.

Idempotente: borra las filas previas de cada `fuente` antes de
re-insertar, así re-correrlo refresca el corpus sin duplicar.

Uso:
    PYTHONUTF8=1 uv run python -m scripts.cargar_corpus_normativo
    PYTHONUTF8=1 uv run python -m scripts.cargar_corpus_normativo --solo constitucion_nacional ley_25188_etica_publica

Notas:
- La primera corrida descarga el modelo de embeddings (~120MB).
- Cada norma toma ~5-15 segundos (descarga + parseo + embed).
- Total corpus: ~5-8 minutos.

Costo: $0 (todo local).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.infrastructure.rag.embedder import EMBEDDING_DIM, embeber_textos
from praxis.infrastructure.rag.infoleg_loader import (
    CATALOGO_NORMAS,
    NormaCatalogada,
    cargar_norma_completa,
)

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("cargar_corpus")


async def cargar_una_norma(
    norma: NormaCatalogada,
    http_client: httpx.AsyncClient,
    sessionmaker,
) -> tuple[str, int, int]:
    """Devuelve (fuente, chunks_extraidos, chunks_persistidos)."""
    try:
        chunks = await cargar_norma_completa(norma, http_client)
    except Exception as exc:
        log.error("Falló descarga de %s: %s", norma.fuente, exc)
        return norma.fuente, 0, 0
    if not chunks:
        return norma.fuente, 0, 0

    log.info("Embeber %d chunks de %s...", len(chunks), norma.fuente)
    textos = [c.texto for c in chunks]
    embeddings = embeber_textos(textos)

    persistidos = 0
    async with sessionmaker() as session:
        # Borrar previo (idempotencia).
        await session.execute(
            text("DELETE FROM norma_juridica_chunk WHERE fuente = :f"),
            {"f": norma.fuente},
        )
        for chunk, emb in zip(chunks, embeddings, strict=True):
            await session.execute(
                text("""
                INSERT INTO norma_juridica_chunk
                    (id, fuente, articulo_label, orden, texto, embedding,
                     modelo_embedding)
                VALUES
                    (:id, :fuente, :art, :orden, :texto, CAST(:emb AS vector),
                     :modelo)
                """),
                {
                    "id": uuid4(),
                    "fuente": chunk.fuente,
                    "art": chunk.articulo_label,
                    "orden": chunk.orden,
                    "texto": chunk.texto,
                    "emb": str(emb),  # pgvector acepta string '[...]'
                    "modelo": "paraphrase-multilingual-MiniLM-L12-v2",
                },
            )
            persistidos += 1
        await session.commit()
    return norma.fuente, len(chunks), persistidos


async def main(args: argparse.Namespace) -> int:
    db_url = str(get_settings().database_url)
    log.info("DB: %s", db_url.split("@")[-1] if "@" in db_url else db_url)
    log.info("Dim embedding esperado: %d", EMBEDDING_DIM)

    norma_a_cargar = CATALOGO_NORMAS
    if args.solo:
        sel = set(args.solo)
        norma_a_cargar = [n for n in CATALOGO_NORMAS if n.fuente in sel]
        if not norma_a_cargar:
            log.error("Ninguna norma del catálogo matchea %s", args.solo)
            return 1

    log.info("Cargar %d normas del catálogo", len(norma_a_cargar))

    engine = create_async_engine(db_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    resultados: list[tuple[str, int, int]] = []
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        for n in norma_a_cargar:
            res = await cargar_una_norma(n, http_client, sessionmaker)
            resultados.append(res)

    await engine.dispose()

    print()
    print(f"{'NORMA':<55}  CHUNKS  PERSIST")
    print("-" * 80)
    total_p = 0
    for fuente, extraidos, persistidos in resultados:
        print(f"{fuente:<55}  {extraidos:>6}  {persistidos:>7}")
        total_p += persistidos
    print("-" * 80)
    print(f"{'TOTAL':<55}  {' ' * 6}  {total_p:>7}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--solo",
        nargs="*",
        default=None,
        help=(
            "Identificadores de fuente a cargar (subset del CATALOGO). "
            "Sin este flag, carga TODO el catálogo."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
