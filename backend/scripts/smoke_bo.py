"""Smoke real end-to-end del pipeline feat-39.

Corre el pipeline completo:

1. **Ingesta:** lee el PDF fixture local (NO baja del BO; reproducible
   sin red) y persiste NormaBO + NormaBOTexto en SQLite local.
2. **Clasificación:** llama al LLM real (Anthropic si hay API key, sino
   FakeLlm) para clasificar las primeras N normas. Cap default 5 normas
   para limitar gasto.
3. **Scoring:** crea un despacho de prueba con perfil "Juliano DPS"
   (educacion, justicia, Buenos Aires) y corre
   EvaluarAccionabilidadPorDespacho.
4. Imprime accionables resultantes con score + razón + tipo + número.

DB de prueba: archivo SQLite local (`tmp_smoke_bo.db`). Borralo a mano
si querés repetir desde cero.

Uso:
    PYTHONUTF8=1 uv run python -m scripts.smoke_bo
    PYTHONUTF8=1 uv run python -m scripts.smoke_bo --max-normas 10
    PYTHONUTF8=1 uv run python -m scripts.smoke_bo --fake-llm   # sin gasto

Salida: tabla en STDOUT + exit code 0 si todo ok.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pdfplumber
from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.application.ports import FuenteBO
from praxis.application.use_cases.evaluar_accionabilidad_bo import (
    EvaluarAccionabilidadPorDespacho,
)
from praxis.application.use_cases.ingestar_bo import IngestarBoletinOficial
from praxis.config import get_settings
from praxis.domain import (
    BO_PROMPT_VERSION,
    ClasificacionNormaBO,
    Despacho,
    NormaBO,
    PerfilInteresDespacho,
    SeccionBO,
)
from praxis.infrastructure.bo.parser import extraer_normas_bo
from praxis.infrastructure.llm import FakeLlmProvider
from praxis.infrastructure.llm.anthropic_provider import AnthropicLlmProvider
from praxis.infrastructure.persistence.base import Base
from praxis.infrastructure.persistence.models import NormaBOOrm
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyNormaBOTextoRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s %(message)s",
)
log = logging.getLogger("smoke_bo")
log.setLevel(logging.INFO)


FIXTURE_PDF = (
    Path(__file__).resolve().parent.parent
    / "spikes" / "bo" / "pdf_del_dia__primera.pdf"
)
DB_FILE = Path(__file__).resolve().parent.parent / "tmp_smoke_bo.db"


class FuenteBOFixturePdf(FuenteBO):
    """`FuenteBO` que devuelve normas parseando un PDF local.

    Útil para smoke + tests sin depender de la red. Reusa el parser real
    `extraer_normas_bo`.
    """

    def __init__(self, pdf_path: Path, fecha) -> None:  # type: ignore[no-untyped-def]
        self._pdf_path = pdf_path
        self._fecha = fecha
        self._cache_textos: dict[str, str] = {}

    async def listar_normas_del_dia(
        self, fecha, seccion: SeccionBO,
    ) -> list[NormaBO]:  # type: ignore[override]
        if seccion != SeccionBO.LEGISLACION:
            return []
        with pdfplumber.open(self._pdf_path) as pdf:
            normas, textos = extraer_normas_bo(
                pdf,
                fecha_publicacion=self._fecha,
                seccion=seccion,
            )
        # Cacheamos texto por hash para obtener_texto_completo.
        for n, t in zip(normas, textos, strict=True):
            self._cache_textos[n.hash_sumario] = t.texto
        return normas

    async def obtener_texto_completo(
        self, norma: NormaBO,
    ) -> str | None:
        return self._cache_textos.get(norma.hash_sumario)


def _construir_llm(usar_fake: bool):  # type: ignore[no-untyped-def]
    if usar_fake:
        log.info("Usando FakeLlmProvider (sin gasto).")
        return FakeLlmProvider()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY no seteada → cayendo a FakeLlmProvider.")
        return FakeLlmProvider()
    log.info("Usando AnthropicLlmProvider con %s", settings.anthropic_model)
    return AnthropicLlmProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )


def _enable_fk(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


async def main(args: argparse.Namespace) -> int:
    if not FIXTURE_PDF.exists():
        print(f"ERROR: falta {FIXTURE_PDF}", file=sys.stderr)
        return 1

    # Fecha "del fixture" — usamos la fecha real del PDF para no chocar
    # con la heuristica de FuenteBOPdfClient. El parser usa esta fecha
    # como fecha_publicacion.
    fecha_fixture = datetime(2026, 6, 1, tzinfo=UTC).date()

    # DB SQLite local. Si existe, sigue donde quedó (idempotente).
    db_url = f"sqlite+aiosqlite:///{DB_FILE.as_posix()}"
    log.info("DB de smoke: %s", DB_FILE)
    engine = create_async_engine(db_url, echo=False)
    event.listen(engine.sync_engine, "connect", _enable_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    fuente = FuenteBOFixturePdf(FIXTURE_PDF, fecha_fixture)
    llm = _construir_llm(args.fake_llm)

    # ----- 1. Ingesta -----
    log.info("=" * 60)
    log.info("PASO 1 — Ingesta del PDF fixture")
    async with sessionmaker() as session:
        uc_ingesta = IngestarBoletinOficial(
            fuente=fuente,
            normas=SqlAlchemyNormaBORepository(session),
            textos=SqlAlchemyNormaBOTextoRepository(session),
        )
        n_ingestadas = await uc_ingesta.execute(fecha=fecha_fixture)
        await session.commit()
        log.info("→ %d normas persistidas", n_ingestadas)

    # ----- 2. Clasificación (top max_normas) -----
    #
    # Importante: el caso de uso EvaluarAccionabilidadPorDespacho del
    # paso 3 también clasifica las normas sin cache. Para limitar el
    # gasto de Anthropic, borramos las normas que no entran en
    # max_normas antes del paso 3.
    log.info("=" * 60)
    log.info("PASO 2 — Clasificación con LLM (cap: %d normas)", args.max_normas)
    async with sessionmaker() as session:
        normas_repo = SqlAlchemyNormaBORepository(session)
        textos_repo = SqlAlchemyNormaBOTextoRepository(session)
        clasifs_repo = SqlAlchemyClasificacionNormaBORepository(session)
        normas_todas = await normas_repo.listar_por_fecha(fecha_fixture)
        normas = normas_todas[: args.max_normas]
        # Borrar las que no procesamos para que el paso 3 no las toque.
        ids_a_borrar = [n.id for n in normas_todas[args.max_normas:]]
        if ids_a_borrar:
            await session.execute(
                delete(NormaBOOrm).where(NormaBOOrm.id.in_(ids_a_borrar)),
            )
            log.info(
                "  Borradas %d normas no procesadas (limitar gasto LLM).",
                len(ids_a_borrar),
            )

        clasificadas = 0
        for norma in normas:
            assert norma.id is not None
            existente = await clasifs_repo.buscar_por_norma(norma.id)
            if existente is not None:
                continue
            texto_obj = await textos_repo.buscar_por_norma(norma.id)
            texto = texto_obj.texto if texto_obj is not None else None
            result = await llm.clasificar_norma_bo(norma, texto=texto)
            clasif = ClasificacionNormaBO(
                id=uuid4(),
                norma_id=norma.id,
                area_tematica=result.area_tematica,
                palabras_clave=list(result.palabras_clave),
                afecta_expedientes_hcdn=result.afecta_expedientes_hcdn,
                referencias_legales=list(result.referencias_legales),
                modelo=llm.nombre_modelo,
                prompt_version=BO_PROMPT_VERSION,
            )
            await clasifs_repo.crear(clasif)
            clasificadas += 1
            log.info(
                "  → %-12s %-12s → %s (refs=%d)",
                norma.tipo_norma, norma.numero_norma,
                result.area_tematica.value, len(result.referencias_legales),
            )
        await session.commit()
        log.info("→ %d clasificaciones nuevas", clasificadas)

    # ----- 3. Setup despacho + perfil + scoring -----
    log.info("=" * 60)
    log.info("PASO 3 — Despacho de prueba + perfil + scoring")
    async with sessionmaker() as session:
        despachos_repo = SqlAlchemyDespachoRepository(session)
        perfiles_repo = SqlAlchemyPerfilInteresDespachoRepository(session)

        # Reusar despacho si ya existe (idempotente).
        despachos = await despachos_repo.listar()
        if despachos:
            despacho = despachos[0]
            log.info("Reusando despacho existente %s", despacho.nombre)
        else:
            despacho = await despachos_repo.crear(
                Despacho(id=uuid4(), nombre="Despacho smoke (Juliano DPS)"),
            )
            log.info("Creé despacho %s (%s)", despacho.nombre, despacho.id)

        # Perfil hardcodeado tipo Juliano.
        await perfiles_repo.upsert(
            PerfilInteresDespacho(
                despacho_id=despacho.id,
                areas_tematicas=["educacion", "justicia", "salud"],
                distritos_observados=["Buenos Aires"],
                aliases_legislador=["Pablo Juliano", "Juliano"],
                sembrado_at=datetime.now(UTC),
            ),
        )

        uc_scoring = EvaluarAccionabilidadPorDespacho(
            perfiles=perfiles_repo,
            normas=SqlAlchemyNormaBORepository(session),
            textos=SqlAlchemyNormaBOTextoRepository(session),
            clasificaciones=SqlAlchemyClasificacionNormaBORepository(session),
            accionables=SqlAlchemyNormaBOAccionableRepository(session),
            llm=llm,
        )
        accionables = await uc_scoring.execute(
            despacho_id=despacho.id, fecha=fecha_fixture, top_n=10,
        )
        await session.commit()

    # ----- 4. Reporte -----
    log.info("=" * 60)
    log.info("PASO 4 — Resultados")
    if not accionables:
        log.info("Sin accionables para el perfil (puede pasar si el LLM no")
        log.info("clasificó normas en las áreas del perfil). Probá con un")
        log.info("perfil más amplio o más normas con --max-normas.")
    else:
        print()
        print(f"{'PRIORIDAD':<8} {'SCORE':<6} {'TIPO+NUM':<25}  RAZÓN")
        print("-" * 100)
        async with sessionmaker() as session:
            normas_repo = SqlAlchemyNormaBORepository(session)
            for a in accionables:
                n = await normas_repo.buscar_por_id(a.norma_id)
                tn = f"{n.tipo_norma} {n.numero_norma}" if n else str(a.norma_id)
                print(
                    f"{a.prioridad.value:<8} {a.score:<6} {tn:<25}  {a.razon}"
                )
        print()

    await engine.dispose()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-normas",
        type=int,
        default=5,
        help="Cap de normas a clasificar con LLM (default 5).",
    )
    p.add_argument(
        "--fake-llm",
        action="store_true",
        help="Forzar FakeLlmProvider (sin gasto).",
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
