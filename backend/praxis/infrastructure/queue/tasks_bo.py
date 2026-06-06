"""Tasks Celery del pipeline BO nocturno (spec 15).

3 tasks programadas por Beat:

- `praxis.bo.ingestar_diario` (05:00 ART): baja PDFs del día y
  persiste NormaBO + NormaBOTexto.
- `praxis.bo.clasificar_pendientes` (05:30 ART): clasifica con LLM
  todas las normas del día sin cache de ClasificacionNormaBO.
- `praxis.bo.evaluar_accionables_por_despacho` (06:00 ART): para
  cada despacho activo, calcula y persiste NormaBOAccionable top-N.

Las tasks son wrappers thinkos del use case correspondiente. Cada una
arma su propia sesión SQLAlchemy + adaptadores y la cierra al final.

Cada task es idempotente: re-ejecutar la misma fecha no duplica.

Sync wrappers porque Celery está pensado sync; usamos `asyncio.run()`
para llamar al pipeline async.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.application.ports import LlmProvider
from praxis.application.use_cases.evaluar_accionabilidad_bo import (
    EvaluarAccionabilidadPorDespacho,
)
from praxis.application.use_cases.ingestar_bo import IngestarBoletinOficial
from praxis.config import get_settings
from praxis.domain import BO_PROMPT_VERSION, ClasificacionNormaBO
from praxis.infrastructure.bo import BoletinOficialPdfClient
from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.llm import FakeLlmProvider
from praxis.infrastructure.llm.anthropic_provider import AnthropicLlmProvider
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyNormaBOTextoRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)
from praxis.infrastructure.queue._async_runtime import run_task_async
from praxis.infrastructure.queue.celery_app import celery_app

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1: ingestar
# ---------------------------------------------------------------------------


@celery_app.task(name="praxis.bo.ingestar_diario")  # type: ignore[untyped-decorator]
def ingestar_diario_task() -> int:
    """Baja PDFs del BO del día corriente y persiste normas + textos."""
    return run_task_async(_ingestar_diario_async())


async def _ingestar_diario_async() -> int:
    fecha = datetime.now(UTC).date()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    cliente = BoletinOficialPdfClient()
    try:
        async with sessionmaker() as session:
            uc = IngestarBoletinOficial(
                fuente=cliente,
                normas=SqlAlchemyNormaBORepository(session),
                textos=SqlAlchemyNormaBOTextoRepository(session),
            )
            n = await uc.execute(fecha=fecha)
            await session.commit()
            log.info("bo.ingestar_diario: %d normas para %s", n, fecha)
            return n
    finally:
        await cliente.aclose()


# ---------------------------------------------------------------------------
# Task 2: clasificar pendientes
# ---------------------------------------------------------------------------


@celery_app.task(name="praxis.bo.clasificar_pendientes")  # type: ignore[untyped-decorator]
def clasificar_pendientes_task() -> int:
    """Clasifica con LLM todas las normas del día sin cache."""
    return run_task_async(_clasificar_pendientes_async())


async def _clasificar_pendientes_async() -> int:
    fecha = datetime.now(UTC).date()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    llm = _construir_llm()

    async with sessionmaker() as session:
        normas_repo = SqlAlchemyNormaBORepository(session)
        textos_repo = SqlAlchemyNormaBOTextoRepository(session)
        clasifs_repo = SqlAlchemyClasificacionNormaBORepository(session)

        normas = await normas_repo.listar_por_fecha(fecha)
        clasificadas = 0
        for norma in normas:
            assert norma.id is not None
            existente = await clasifs_repo.buscar_por_norma(norma.id)
            if existente is not None:
                continue
            texto_obj = await textos_repo.buscar_por_norma(norma.id)
            texto = texto_obj.texto if texto_obj is not None else None
            result = await llm.clasificar_norma_bo(norma, texto=texto)
            from uuid import uuid4
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
        await session.commit()
        log.info(
            "bo.clasificar_pendientes: %d clasificaciones nuevas para %s",
            clasificadas, fecha,
        )
        return clasificadas


# ---------------------------------------------------------------------------
# Task 3: evaluar accionables por despacho
# ---------------------------------------------------------------------------


@celery_app.task(name="praxis.bo.evaluar_accionables_por_despacho")  # type: ignore[untyped-decorator]
def evaluar_accionables_por_despacho_task() -> int:
    """Para cada despacho con perfil, calcula y persiste accionables."""
    return run_task_async(_evaluar_accionables_async())


async def _evaluar_accionables_async() -> int:
    fecha = datetime.now(UTC).date()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    llm = _construir_llm()

    async with sessionmaker() as session:
        despachos_repo = SqlAlchemyDespachoRepository(session)
        despachos = await despachos_repo.listar()
        total = 0
        for despacho in despachos:
            uc = EvaluarAccionabilidadPorDespacho(
                perfiles=SqlAlchemyPerfilInteresDespachoRepository(session),
                normas=SqlAlchemyNormaBORepository(session),
                textos=SqlAlchemyNormaBOTextoRepository(session),
                clasificaciones=SqlAlchemyClasificacionNormaBORepository(
                    session,
                ),
                accionables=SqlAlchemyNormaBOAccionableRepository(session),
                llm=llm,
            )
            creadas = await uc.execute(
                despacho_id=despacho.id, fecha=fecha,
            )
            total += len(creadas)
        await session.commit()
        log.info(
            "bo.evaluar_accionables: %d accionables totales para %d despachos",
            total, len(despachos),
        )
        return total


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _construir_llm() -> LlmProvider:
    """Mismo selector que `praxis.api.deps.get_llm_provider` pero
    sin FastAPI."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    return FakeLlmProvider()


# Export para que `_norma_id` (UUID) sirva como discriminador en logs
# si es necesario; placeholder reservado.

_unused: date | None = None
