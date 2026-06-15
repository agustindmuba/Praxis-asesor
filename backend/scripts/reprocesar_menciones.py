"""Re-detecta menciones en artículos ya persistidos (feat-56).

Caso: cuando se cargaron los 640 artículos el `legislador_titular_slug`
del despacho de Juliano era "JULIANO, PABLO" (formato apellido, nombre)
en vez de "pjuliano" (el slug del padrón). Eso hacía que
`_resolver_legisladores` devolviera [] y el detector se saltara.

Tras corregir el slug a "pjuliano", los artículos NUEVOS sí se procesan
correctamente, pero los 640 viejos quedaron sin detección. Este script
los re-procesa.

ADR 0006 dice que el cuerpo del artículo NO se persiste. Pero sí
tenemos `bajada_propia` (≤ 240 chars), que es la versión resumida del
LLM y suele contener las menciones políticas explícitas. Lo usamos
junto con el título como texto de búsqueda.

Uso:
    uv run python -m scripts.reprocesar_menciones

Idempotente: las menciones se insertan con upsert por
(articulo_id, legislador_id, despacho_id).
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.application.use_cases.detectar_menciones_en_articulo import (
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
)
from praxis.config import get_settings
from praxis.domain import AlcanceMedio, Articulo, Camara
from praxis.infrastructure.llm.fake import FakeLlmProvider
from praxis.infrastructure.padron.csv_repository import CsvPadronRepository
from praxis.infrastructure.persistence.models import (
    ArticuloOrm,
    FuenteNoticiaOrm,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyMencionRepository,
)

log = structlog.get_logger()


# Mapeo TipoFuente del catálogo → AlcanceMedio. Coherente con tasks_noticias.
ALCANCE_POR_NOMBRE: dict[str, AlcanceMedio] = {
    "Clarín Política": AlcanceMedio.NACIONAL,
    "La Nación Política": AlcanceMedio.NACIONAL,
    "Infobae Política": AlcanceMedio.NACIONAL,
    "TN": AlcanceMedio.NACIONAL,
    "Perfil": AlcanceMedio.NACIONAL,
    "elDiarioAR": AlcanceMedio.NACIONAL,
    "La Voz del Interior (Política)": AlcanceMedio.NACIONAL,
    "Parlamentario": AlcanceMedio.NICHO,
}


def _articulo_orm_a_domain(orm: ArticuloOrm) -> Articulo:
    return Articulo(
        id=orm.id,
        fuente_id=orm.fuente_id,
        url_canonical=orm.url_canonical,
        url_original=orm.url_original or orm.url_canonical,
        titulo=orm.titulo,
        autores=list(orm.autores or []),
        publicado_en=orm.publicado_en,
        descubierto_en=orm.descubierto_en,
        hash_dedup=orm.hash_dedup,
        bajada_propia=orm.bajada_propia,
    )


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[reprocesar-menciones] DB: {settings.database_url}")
    print()

    # 1. Cargar despachos con legislador resuelto.
    padron = CsvPadronRepository()
    despachos_resueltos: list[tuple] = []
    async with sm() as session:
        r = await session.execute(text("""
            SELECT id, nombre, legislador_titular_slug
            FROM despacho
            WHERE legislador_titular_slug IS NOT NULL
              AND legislador_titular_slug <> ''
        """))
        for row in r.all():
            despacho_id, nombre, slug = row
            legislador = None
            for camara in (Camara.HCDN, Camara.HSN):
                try:
                    legislador = padron.buscar_por_slug(slug, camara)
                    break
                except KeyError:
                    continue
            if legislador is None:
                print(f"  ! Despacho {nombre}: slug '{slug}' no resuelve en padrón. Skip.")
                continue
            despachos_resueltos.append((despacho_id, nombre, legislador))

    print(f"[reprocesar-menciones] Despachos resueltos: {len(despachos_resueltos)}")
    if not despachos_resueltos:
        print("[reprocesar-menciones] Nada para hacer.")
        await engine.dispose()
        return 0

    for _, n, leg in despachos_resueltos:
        print(f"  · {n} → {leg.nombre} {leg.apellido}")
    print()

    # 2. Iterar artículos y detectar.
    llm = FakeLlmProvider()
    detector = DetectarMencionesEnArticulo(llm=llm)

    total_articulos = 0
    total_menciones = 0
    errores = 0

    async with sm() as session:
        # Trae todos los artículos con su fuente.
        r = await session.execute(text("""
            SELECT a.id, a.fuente_id, a.url,
                   a.titulo, a.publicado_en, a.capturado_en,
                   a.hash_dedup, a.bajada_propia,
                   f.nombre
            FROM articulo a
            JOIN fuente_noticia f ON f.id = a.fuente_id
            WHERE a.bajada_propia IS NOT NULL
              AND length(a.bajada_propia) > 0
            ORDER BY a.publicado_en DESC NULLS LAST
        """))
        rows = r.all()
        print(f"[reprocesar-menciones] Artículos con bajada_propia: {len(rows)}")

        from datetime import UTC, datetime
        from uuid import UUID as _UUID
        mencion_repo = SqlAlchemyMencionRepository(session)

        for row in rows:
            total_articulos += 1
            articulo = Articulo(
                id=row[0],
                fuente_id=row[1],
                url=row[2],
                titulo=row[3],
                publicado_en=row[4],
                capturado_en=row[5],
                hash_dedup=row[6],
                bajada_propia=row[7],
            )
            fuente_nombre = row[8]
            alcance = ALCANCE_POR_NOMBRE.get(fuente_nombre, AlcanceMedio.NACIONAL)

            # Texto de búsqueda = titulo + bajada_propia.
            texto = f"{articulo.titulo}\n\n{articulo.bajada_propia or ''}"

            slots = []
            for despacho_id, _, legislador in despachos_resueltos:
                from praxis.infrastructure.queue.tasks_noticias import (
                    legislador_uuid,
                )
                slots.append(
                    LegisladorAMonitorear(
                        legislador=legislador,
                        legislador_id=legislador_uuid(
                            slug=legislador.slug, camara=legislador.camara,
                        ),
                        despacho_id=despacho_id,
                        aliases_extra=[],
                    )
                )

            try:
                menciones = await detector.ejecutar(
                    articulo=articulo,
                    texto_articulo=texto,
                    legisladores=slots,
                    alcance_medio=alcance,
                    ahora=datetime.now(UTC),
                )
            except Exception as exc:
                errores += 1
                print(f"  ✗ {articulo.titulo[:50]}: {exc}")
                continue

            if menciones:
                try:
                    await mencion_repo.crear_lote(menciones)
                    total_menciones += len(menciones)
                    print(f"  ✓ {articulo.titulo[:70]} → {len(menciones)} menciones")
                except Exception as exc:
                    errores += 1
                    print(f"  ✗ persist {articulo.titulo[:50]}: {exc}")

        await session.commit()

    await engine.dispose()
    print()
    print("=" * 60)
    print(f"  Artículos procesados: {total_articulos}")
    print(f"  Menciones creadas:    {total_menciones}")
    print(f"  Errores:              {errores}")
    print("=" * 60)
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
