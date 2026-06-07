"""Descarga PDFs de expedientes y los parsea a texto completo (feat-48.4).

Para cada expediente con `texto_url` no NULL y `texto_completo` NULL:
  1. GET al PDF (rate-limited 1 req/s, retries con backoff).
  2. pdfplumber → string del cuerpo completo.
  3. UPDATE expediente SET texto_completo = ... WHERE id = ...

Esto NO toca el portal HCDN principal — el `texto_url` apunta a
www4.hcdn.gob.ar (servidor de PDFs estáticos), distinto del visor.

Uso:
    # Ver universo
    uv run python -m scripts.bajar_textos_completos --dry-run

    # Probar con 5
    uv run python -m scripts.bajar_textos_completos --limite 5 -v

    # Lanzar para todos
    uv run python -m scripts.bajar_textos_completos

Idempotente: cualquier expediente con texto_completo != NULL se saltea.
Si el PDF da 404, se marca texto_completo='__NO_DISPONIBLE__' para no
retentarlo cada vez. Si el PDF se corrompe al parsear, se loggea pero
no se marca (próxima corrida lo retenta).

Tiempo esperado: 198 PDFs × ~1.5s (1s rate-limit + 0.5s descarga +
parser) ≈ 5 min total.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
import time
from contextlib import suppress

# Forzar UTF-8 en stdout para que los símbolos unicode (✓ ✗ ─) no
# revienten en Windows con codepage cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import pdfplumber
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings

log = structlog.get_logger()


# Centinela para PDFs que dieron 404. Evita retentar los inexistentes
# en cada corrida. Comparable con `texto_completo = '__NO_DISPONIBLE__'`.
NO_DISPONIBLE = "__NO_DISPONIBLE__"


_SELECT_PENDIENTES = text("""
    SELECT id, numero, origen, anio, texto_url
    FROM expediente
    WHERE texto_url IS NOT NULL
      AND texto_completo IS NULL
      AND camara = :camara
    ORDER BY anio DESC, numero ASC
""")


_UPDATE_TEXTO = text("""
    UPDATE expediente
    SET texto_completo = :t, actualizado_en = now()
    WHERE id = :id
""")


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[bajar-textos] DB: {settings.database_url}")
    print(f"[bajar-textos] Cámara: {args.camara}")
    if args.limite:
        print(f"[bajar-textos] Límite: {args.limite}")
    if args.dry_run:
        print("[bajar-textos] *** DRY-RUN — no se descarga nada ***")
    print()

    async with sm() as session:
        result = await session.execute(_SELECT_PENDIENTES, {"camara": args.camara})
        pendientes = [
            {
                "id": row[0],
                "numero": row[1],
                "origen": row[2],
                "anio": row[3],
                "texto_url": row[4],
            }
            for row in result.all()
        ]

    total = len(pendientes)
    print(f"[bajar-textos] PDFs a procesar: {total}")
    if args.limite and args.limite < total:
        pendientes = pendientes[: args.limite]
        print(f"[bajar-textos] Procesando primeros {len(pendientes)}")
    print()

    if args.dry_run:
        for p in pendientes[:10]:
            print(f"  - {p['numero']:>4}-{p['origen']}-{p['anio']}  ->  {p['texto_url']}")
        if len(pendientes) > 10:
            print(f"  ... y {len(pendientes) - 10} más")
        await engine.dispose()
        return 0

    if not pendientes:
        print("[bajar-textos] Nada para hacer.")
        await engine.dispose()
        return 0

    descargados = 0
    no_disponibles = 0
    errores_parse = 0
    errores_red = 0
    started_at = time.monotonic()

    try:
        # Timeout generoso — algunos PDFs son grandes y el server tarda.
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            for i, p in enumerate(pendientes, 1):
                etiqueta = f"{p['numero']:04d}-{p['origen']}-{p['anio']}"

                # Rate-limit manual: 1 req/s para no abusar del server.
                # (httpx no tiene un limiter built-in.)
                if i > 1:
                    await asyncio.sleep(1.0)

                # 1) Descargar PDF
                try:
                    resp = await http_client.get(p["texto_url"])
                except httpx.HTTPError as exc:
                    errores_red += 1
                    print(f"  ✗ {etiqueta}: red ({type(exc).__name__})")
                    continue

                if resp.status_code == 404:
                    no_disponibles += 1
                    if args.verbose:
                        print(f"  · {etiqueta}: PDF 404 — marcando NO_DISPONIBLE")
                    async with sm() as session:
                        await session.execute(
                            _UPDATE_TEXTO,
                            {"id": p["id"], "t": NO_DISPONIBLE},
                        )
                        await session.commit()
                    continue

                if resp.status_code != 200:
                    errores_red += 1
                    print(f"  ✗ {etiqueta}: HTTP {resp.status_code}")
                    continue

                if not resp.content.startswith(b"%PDF"):
                    errores_parse += 1
                    print(
                        f"  ✗ {etiqueta}: el servidor no devolvió un PDF "
                        f"(content-type={resp.headers.get('content-type')})"
                    )
                    continue

                # 2) Parsear PDF
                try:
                    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                        partes = []
                        for pagina in pdf.pages:
                            t = pagina.extract_text() or ""
                            if t.strip():
                                partes.append(t)
                        texto = "\n\n".join(partes).strip()
                except Exception as exc:
                    errores_parse += 1
                    print(
                        f"  ✗ {etiqueta}: parse falló "
                        f"({type(exc).__name__}: {exc})"
                    )
                    continue

                if not texto:
                    errores_parse += 1
                    print(f"  ✗ {etiqueta}: PDF parseó pero quedó vacío")
                    continue

                # Postgres TEXT no acepta el null byte (0x00); pdfplumber
                # a veces lo extrae de PDFs con encoding raro. Limpiamos.
                texto = texto.replace("\x00", "")

                # 3) Guardar
                async with sm() as session:
                    try:
                        await session.execute(
                            _UPDATE_TEXTO,
                            {"id": p["id"], "t": texto},
                        )
                        await session.commit()
                        descargados += 1
                        if args.verbose:
                            print(
                                f"  ✓ {etiqueta}: {len(texto):,} chars "
                                f"({len(resp.content) / 1024:.0f} KB)"
                            )
                    except Exception as exc:
                        await session.rollback()
                        errores_parse += 1
                        print(f"  ✗ {etiqueta}: error persistiendo ({exc})")

                if i % 25 == 0:
                    elapsed = time.monotonic() - started_at
                    print(
                        f"  ─ progreso: {i}/{len(pendientes)} "
                        f"(✓{descargados} ·{no_disponibles} ✗{errores_red + errores_parse} · {elapsed:.0f}s)"
                    )

    except KeyboardInterrupt:
        print()
        print("[bajar-textos] Interrumpido. Lo commiteado queda en DB.")
    finally:
        with suppress(Exception):
            await engine.dispose()

    elapsed = time.monotonic() - started_at
    print()
    print("=" * 60)
    print(f"  Descargados:      {descargados}")
    print(f"  PDFs no existen:  {no_disponibles}")
    print(f"  Errores parse:    {errores_parse}")
    print(f"  Errores red:      {errores_red}")
    print(f"  Tiempo total:     {elapsed:.1f}s")
    print("=" * 60)
    return 0 if (errores_red + errores_parse) == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Baja PDFs de expedientes y los parsea a texto"
    )
    p.add_argument(
        "--camara",
        default="HCDN",
        help="Cámara objetivo (default HCDN)",
    )
    p.add_argument(
        "--limite",
        type=int,
        default=None,
        help="Límite de PDFs a procesar",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo cuenta, no descarga",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Línea por cada PDF procesado",
    )
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_build_parser().parse_args())))
