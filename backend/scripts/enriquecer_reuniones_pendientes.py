"""Enriquece todas las reuniones de comisión que están sin analizar.

Pensado para correrse:
- A demanda (después del seed inicial).
- Idealmente desde Celery beat con cadencia diaria.

Por cada reunión sin `enriquecida_en`:
- Baja PDF de citación.
- Llama al LLM con el perfil opositor del despacho.
- Persiste tema, oportunidad política, acción sugerida.

Costo aprox: $0.05 por reunión nueva. Las que ya están enriquecidas se
saltan (idempotente).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.application.use_cases.enriquecer_reunion_comision import (
    EnriquecerReunionComision,
)
from praxis.config import get_settings
from praxis.domain import Camara
from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.llm.fake import FakeLlmProvider
from praxis.infrastructure.persistence.models import (
    ComisionHcdnOrm,
    DespachoOrm,
    ReunionComisionOrm,
)
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyComisionHcdnRepository,
    SqlAlchemyPerfilOpositorRepository,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("enriquecer-reuniones-pendientes")


async def enriquecer_reuniones_pendientes(
    *,
    despacho_id: UUID | None = None,
    dias: int = 30,
) -> tuple[int, int]:
    """API pública: enriquece todas las reuniones futuras del despacho
    que no tengan `enriquecida_en`. Devuelve (enriquecidas, fallidas).

    Usar desde scripts (seed) o tasks Celery. Idempotente.
    """
    return await _enriquecer_todas_impl(despacho_id=despacho_id, dias=dias)


async def _resolver_despacho_si_falta(despacho_id: UUID | None) -> UUID:
    if despacho_id is not None:
        return despacho_id
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        stmt = (
            select(DespachoOrm)
            .where(DespachoOrm.legislador_titular_slug.is_not(None))
            .limit(1)
        )
        d = (await session.execute(stmt)).scalar_one_or_none()
        if d is None:
            raise SystemExit(
                "No hay despachos con legislador_titular_slug. Configurá uno.",
            )
        return d.id


async def _enriquecer_todas_impl(
    *, despacho_id: UUID | None, dias: int,
) -> tuple[int, int]:
    despacho_id = await _resolver_despacho_si_falta(despacho_id)
    settings = get_settings()
    if settings.anthropic_api_key:
        from praxis.infrastructure.llm.anthropic_provider import (
            AnthropicLlmProvider,
        )

        llm = AnthropicLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
        log.info("LLM real (Anthropic) habilitado: %s", llm.nombre_modelo)
    else:
        llm = FakeLlmProvider()
        log.info("LLM FAKE (sin API key configurada)")

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    hoy = date.today()
    hasta = hoy + timedelta(days=dias)

    async with sessionmaker() as session:
        # Reuniones futuras del rango, sin enriquecer.
        stmt = (
            select(ReunionComisionOrm)
            .where(
                ReunionComisionOrm.fecha >= hoy,
                ReunionComisionOrm.fecha <= hasta,
                ReunionComisionOrm.enriquecida_en.is_(None),
            )
            .order_by(ReunionComisionOrm.fecha)
        )
        pendientes = (await session.execute(stmt)).scalars().all()
        log.info("Pendientes: %d reuniones", len(pendientes))

    repo_factory = SqlAlchemyComisionHcdnRepository
    perfiles_factory = SqlAlchemyPerfilOpositorRepository

    enriquecidas = 0
    fallidas = 0
    for orm in pendientes:
        async with sessionmaker() as session:
            repo = repo_factory(session)
            reunion = await repo.buscar_reunion_por_id(orm.id)
            if reunion is None:
                continue
            com_orm = (
                await session.execute(
                    select(ComisionHcdnOrm).where(
                        ComisionHcdnOrm.id == orm.comision_id,
                    ),
                )
            ).scalar_one_or_none()
            if com_orm is None:
                continue
            comision = await repo.buscar_por_slug(
                camara=Camara(com_orm.camara), slug=com_orm.slug,
            )
            assert comision is not None

            perfiles = perfiles_factory(session)
            uc = EnriquecerReunionComision(
                llm=llm, perfiles=perfiles, comisiones=repo,
            )
            try:
                resultado = await uc.ejecutar(
                    despacho_id=despacho_id,
                    reunion=reunion,
                    comision=comision,
                )
            except Exception as exc:
                log.warning(
                    "Reunión %s falló: %s", reunion.id, exc,
                )
                fallidas += 1
                continue

            await repo.actualizar_enriquecimiento_reunion(
                reunion_id=orm.id,
                tema_corto=resultado.tema_corto,
                tipo_reunion=resultado.tipo_reunion,
                convocada_por=resultado.convocada_por,
                expedientes_citados=resultado.expedientes_citados,
                oportunidad_politica=resultado.oportunidad_politica,
                accion_sugerida=resultado.accion_sugerida,
                huella_historica=None,
                enriquecida_en=datetime.now(UTC),
            )
            await session.commit()
            enriquecidas += 1
            log.info(
                "OK [%d/%d] %s (%s): %s",
                enriquecidas + fallidas,
                len(pendientes),
                comision.nombre[:40],
                reunion.fecha,
                resultado.tema_corto[:80],
            )

    log.info(
        "Listo. Enriquecidas: %d, fallidas: %d", enriquecidas, fallidas,
    )
    return enriquecidas, fallidas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--despacho",
        type=str,
        default=None,
        help="UUID del despacho. Default: primero con legislador_titular_slug.",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=30,
        help="Ventana futura para enriquecer (default 30).",
    )
    args = parser.parse_args()
    despacho_id = UUID(args.despacho) if args.despacho else None
    asyncio.run(
        enriquecer_reuniones_pendientes(
            despacho_id=despacho_id, dias=args.dias,
        ),
    )


if __name__ == "__main__":
    main()
