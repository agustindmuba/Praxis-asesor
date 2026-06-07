"""Embebe expedientes con sentence-transformers local (feat-48.5).

Para cada expediente con embedding NULL, construye un texto canónico
`<titulo>\\n\\n<sumario>\\n\\n<texto_completo[:8000]>` y lo pasa por
el modelo `paraphrase-multilingual-MiniLM-L12-v2` (384 dims). El
resultado se persiste en la columna `expediente.embedding`.

Procesamos en BATCHES de 32 (el modelo es eficiente paralelizando)
para que sea rápido aun en CPU.

$0 — corre 100% local, sin tocar ninguna API paga.

Uso:
    # Ver universo
    uv run python -m scripts.embeber_expedientes --dry-run

    # Probar con 10
    uv run python -m scripts.embeber_expedientes --limite 10

    # Lanzar para todos los pendientes
    uv run python -m scripts.embeber_expedientes

Idempotente: un expediente con embedding != NULL se saltea. Si
querés re-embebir todo (ej. cambiaste el modelo), pasá --reset (borra
los embeddings primero).

Tiempo estimado: con 384 dims + MiniLM en CPU consumer,
~50 textos/seg. 441 expedientes ≈ 10s.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import suppress

# Forzar UTF-8 en stdout para que los símbolos unicode no exploten en
# Windows con codepage cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.infrastructure.rag.embedder import embeber_textos

log = structlog.get_logger()


# Cuánto del texto_completo metemos en el embedding. El modelo
# trunca a ~512 tokens igual; cortamos antes para no transferir
# texto innecesario al modelo.
MAX_CHARS_TEXTO = 8000

BATCH_SIZE = 32


_SELECT_PENDIENTES = text("""
    SELECT id, titulo, COALESCE(sumario, '') AS sumario,
           COALESCE(texto_completo, '') AS texto_completo
    FROM expediente
    WHERE embedding IS NULL
      AND camara = :camara
    ORDER BY anio DESC, numero ASC
""")


# Pasamos el vector como STRING en formato pgvector ("[0.1,0.2,...]").
# asyncpg + pgvector aceptan ese formato.
_UPDATE_EMBEDDING = text("""
    UPDATE expediente
    SET embedding = CAST(:emb AS vector),
        actualizado_en = now()
    WHERE id = :id
""")


_RESET_EMBEDDINGS = text("""
    UPDATE expediente SET embedding = NULL WHERE camara = :camara
""")


def _construir_texto_canonico(
    titulo: str, sumario: str, texto_completo: str
) -> str:
    """Texto que se va al embedder. Mismo formato siempre, así
    el espacio vectorial es consistente."""
    partes = [titulo.strip()]
    if sumario.strip():
        partes.append(sumario.strip())
    if texto_completo.strip() and texto_completo != "__NO_DISPONIBLE__":
        partes.append(texto_completo[:MAX_CHARS_TEXTO].strip())
    return "\n\n".join(partes)


def _vector_a_pgvector(v: list[float]) -> str:
    """Convierte [0.1, 0.2, ...] a '[0.1,0.2,...]' (formato pgvector)."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[embeber] DB: {settings.database_url}")
    print(f"[embeber] Cámara: {args.camara}")
    if args.limite:
        print(f"[embeber] Límite: {args.limite}")
    print()

    # Reset opcional
    if args.reset:
        if not args.yes:
            print("[embeber] --reset borra todos los embeddings.")
            print("[embeber] Pasá también --yes para confirmar.")
            await engine.dispose()
            return 1
        async with sm() as session:
            await session.execute(
                _RESET_EMBEDDINGS, {"camara": args.camara}
            )
            await session.commit()
        print("[embeber] Todos los embeddings borrados.")

    # Leer pendientes
    async with sm() as session:
        result = await session.execute(
            _SELECT_PENDIENTES, {"camara": args.camara}
        )
        pendientes = [
            {
                "id": row[0],
                "titulo": row[1],
                "sumario": row[2],
                "texto_completo": row[3],
            }
            for row in result.all()
        ]

    total = len(pendientes)
    print(f"[embeber] Pendientes: {total}")
    if args.limite and args.limite < total:
        pendientes = pendientes[: args.limite]
        print(f"[embeber] Procesando primeros {len(pendientes)}")
    print()

    if args.dry_run:
        for p in pendientes[:5]:
            txt = _construir_texto_canonico(
                p["titulo"], p["sumario"], p["texto_completo"]
            )
            print(f"  - {p['id']}: {len(txt)} chars")
            if args.verbose:
                print(f"     {txt[:120]}...")
        if len(pendientes) > 5:
            print(f"  ... y {len(pendientes) - 5} más")
        await engine.dispose()
        return 0

    if not pendientes:
        print("[embeber] Nada para hacer.")
        await engine.dispose()
        return 0

    print("[embeber] Cargando modelo (primera vez: ~120MB de descarga si no está cacheado)...")
    started_at = time.monotonic()

    procesados = 0
    errores = 0

    try:
        for i in range(0, len(pendientes), BATCH_SIZE):
            chunk = pendientes[i : i + BATCH_SIZE]
            textos = [
                _construir_texto_canonico(
                    p["titulo"], p["sumario"], p["texto_completo"]
                )
                for p in chunk
            ]

            try:
                vectores = embeber_textos(textos)
            except Exception as exc:
                errores += len(chunk)
                print(
                    f"  ✗ batch de {len(chunk)}: error embebiendo "
                    f"({type(exc).__name__}: {exc})"
                )
                continue

            async with sm() as session:
                try:
                    for p, v in zip(chunk, vectores, strict=True):
                        await session.execute(
                            _UPDATE_EMBEDDING,
                            {"id": p["id"], "emb": _vector_a_pgvector(v)},
                        )
                    await session.commit()
                    procesados += len(chunk)
                except Exception as exc:
                    await session.rollback()
                    errores += len(chunk)
                    print(f"  ✗ batch persistiendo: {exc}")

            elapsed = time.monotonic() - started_at
            rate = procesados / elapsed if elapsed > 0 else 0
            print(
                f"  ─ progreso: {procesados}/{len(pendientes)} "
                f"({rate:.1f} emb/s · {elapsed:.0f}s)"
            )

    except KeyboardInterrupt:
        print()
        print("[embeber] Interrumpido. Lo commiteado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Procesados:  {procesados}")
    print(f"  Errores:     {errores}")
    print(f"  Tiempo:      {elapsed:.1f}s")
    print("=" * 60)
    return 0 if errores == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Embebe expedientes localmente")
    p.add_argument("--camara", default="HCDN")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reset", action="store_true",
                   help="Borra TODOS los embeddings primero (requiere --yes)")
    p.add_argument("--yes", action="store_true",
                   help="Confirma --reset destructivo")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
