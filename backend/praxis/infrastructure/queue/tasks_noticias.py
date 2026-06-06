"""Tasks Celery del pipeline de Noticias + Menciones (spec 16, feat-40.5.D).

2 tasks programadas por Beat:

- `praxis.noticias.procesar_fuentes` (cada 15 min):
  Lista fuentes activas y, por cada una, ejecuta el caso de uso
  `ProcesarArticulosDeFuente`. Resuelve dinámicamente los `DespachoSuscrito`
  (perfil + legisladores) para cada despacho activo. La ventana es
  `(fuente.ultima_revision, ahora)` o, si nunca se revisó, las últimas
  24 horas.

- `praxis.noticias.enviar_alertas_pendientes` (cada 10 min):
  Por cada despacho activo invoca `EnviarAlertaMencion`. Aplica anti-flood
  y marca las menciones como notificadas. El envío real por WhatsApp es
  feat-41 — esta task v1 solo loguea la intención (con el log se puede
  validar el comportamiento sin gastar API de Meta).

Las tasks son wrappers sync (asyncio.run) sobre el pipeline async.
Cada una abre su propia sesión + adapters y cierra al final.
"""

from __future__ import annotations

import asyncio        # noqa: F401  — legacy, sustituido por run_task_async
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from praxis.application.ports import LlmProvider
from praxis.application.use_cases import (
    DespachoSuscrito,
    DetectarMencionesEnArticulo,
    EnviarAlertaMencion,
    LegisladorAMonitorear,
    ProcesarArticulosDeFuente,
)
from praxis.config import get_settings
from praxis.domain import Camara, Legislador, PerfilInteresDespacho
from praxis.domain.despacho import Despacho
from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.llm import FakeLlmProvider
from praxis.infrastructure.llm.anthropic_provider import AnthropicLlmProvider
from praxis.infrastructure.noticias.multi_adapter import (
    FuenteNoticiasMultiAdapter,
)
from praxis.infrastructure.padron import CsvPadronRepository
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloHashRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMencionRepository,
    SqlAlchemyPerfilInteresDespachoRepository,
)
from praxis.infrastructure.queue._async_runtime import run_task_async
from praxis.infrastructure.queue.celery_app import celery_app

log = logging.getLogger(__name__)


# Ventana default cuando una fuente nunca fue revisada (primera corrida).
VENTANA_INICIAL = timedelta(hours=24)

# Namespace UUID5 para derivar legislador_id desde el slug + cámara.
# Estable cross-corrida. El catálogo de legisladores vive en CSV
# (ADR 0005), no en DB, así que usamos un namespace acordado para
# construir el UUID que `Mencion.legislador_id` exige.
_LEGISLADOR_UUID_NS = UUID("a0c3b6fe-1d59-4e58-8a8a-000000004000")


def legislador_uuid(*, slug: str, camara: Camara) -> UUID:
    """UUID5 estable derivado del (cámara, slug) del padrón."""
    return uuid5(_LEGISLADOR_UUID_NS, f"{camara.value}:{slug}")


# ---------------------------------------------------------------------------
# Task 1: procesar fuentes
# ---------------------------------------------------------------------------


@celery_app.task(name="praxis.noticias.procesar_fuentes")  # type: ignore[untyped-decorator]
def procesar_fuentes_task() -> dict[str, int]:
    """Pollea todas las fuentes activas y procesa los artículos nuevos.

    Devuelve un agregado de contadores para verificación rápida en
    Flower. Logs detallados por fuente.
    """
    return run_task_async(_procesar_fuentes_async())


async def _procesar_fuentes_async() -> dict[str, int]:
    ahora = datetime.now(UTC)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    llm = _construir_llm()
    padron = CsvPadronRepository()
    adapter = FuenteNoticiasMultiAdapter()
    detector = DetectarMencionesEnArticulo(llm=llm)

    total_descubiertos = 0
    total_nuevos = 0
    total_menciones = 0
    fallidos = 0

    try:
        async with sessionmaker() as session:
            fuentes_repo = SqlAlchemyFuenteNoticiaRepository(session)
            fuentes = await fuentes_repo.listar_activas()
            despachos = await _resolver_despachos_suscriptos(
                session=session, padron=padron,
            )
            log.info(
                "noticias.procesar_fuentes: %d fuentes activas, %d despachos",
                len(fuentes), len(despachos),
            )

            for fuente in fuentes:
                assert fuente.id is not None
                desde = fuente.ultima_revision or (ahora - VENTANA_INICIAL)
                uc = ProcesarArticulosDeFuente(
                    fuente_adapter=adapter,
                    articulos=SqlAlchemyArticuloRepository(session),
                    hashes=SqlAlchemyArticuloHashRepository(session),
                    clasificaciones=SqlAlchemyClasificacionArticuloRepository(
                        session,
                    ),
                    menciones=SqlAlchemyMencionRepository(session),
                    relevantes=SqlAlchemyArticuloRelevanteRepository(session),
                    fuentes=fuentes_repo,
                    llm=llm,
                    detector_menciones=detector,
                )
                try:
                    resultado = await uc.ejecutar(
                        fuente,
                        desde=desde,
                        despachos=despachos,
                        ahora=ahora,
                    )
                    await session.commit()
                    total_descubiertos += resultado.articulos_descubiertos
                    total_nuevos += resultado.articulos_nuevos
                    total_menciones += resultado.menciones_creadas
                    fallidos += resultado.fallidos
                    log.info(
                        "noticias[%s]: %d desc, %d nuevos, %d clasif, "
                        "%d menciones, %d relevancias, %d fallidos",
                        fuente.dominio,
                        resultado.articulos_descubiertos,
                        resultado.articulos_nuevos,
                        resultado.clasificaciones_persistidas,
                        resultado.menciones_creadas,
                        resultado.relevancias_persistidas,
                        resultado.fallidos,
                    )
                except Exception as exc:
                    await session.rollback()
                    fallidos += 1
                    log.exception(
                        "noticias[%s] falló: %s", fuente.dominio, exc,
                    )
    finally:
        await adapter.aclose()

    return {
        "descubiertos": total_descubiertos,
        "nuevos": total_nuevos,
        "menciones": total_menciones,
        "fallidos": fallidos,
    }


# ---------------------------------------------------------------------------
# Task 2: enviar alertas pendientes
# ---------------------------------------------------------------------------


@celery_app.task(name="praxis.noticias.enviar_alertas_pendientes")  # type: ignore[untyped-decorator]
def enviar_alertas_pendientes_task() -> dict[str, int]:
    """Por cada despacho activo, evalúa si emitir alerta con anti-flood.

    El envío real por WhatsApp es feat-41. Esta task v1 solo loguea
    cuántas menciones se marcaron como notificadas por despacho. Cuando
    feat-41 esté, el sender escucha la intención y dispara la API de Meta.
    """
    return run_task_async(_enviar_alertas_async())


async def _enviar_alertas_async() -> dict[str, int]:
    ahora = datetime.now(UTC)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    enviadas = 0
    rate_limited = 0
    sin_pendientes = 0
    menciones_marcadas = 0

    async with sessionmaker() as session:
        despachos_repo = SqlAlchemyDespachoRepository(session)
        despachos = await despachos_repo.listar()
        uc = EnviarAlertaMencion(menciones=SqlAlchemyMencionRepository(session))

        for despacho in despachos:
            try:
                intencion = await uc.ejecutar(
                    despacho.id, ahora=ahora,
                )
                if intencion.motivo == "ok_enviar":
                    enviadas += 1
                    menciones_marcadas += len(intencion.menciones)
                    log.info(
                        "noticias.alerta[%s]: %d menciones marcadas. "
                        "TODO feat-41: enviar por WhatsApp.",
                        despacho.id, len(intencion.menciones),
                    )
                elif intencion.motivo == "rate_limited_hace_menos_de_la_ventana":
                    rate_limited += 1
                else:
                    sin_pendientes += 1
            except Exception as exc:
                log.exception(
                    "noticias.alerta[%s] falló: %s", despacho.id, exc,
                )
        await session.commit()

    log.info(
        "noticias.enviar_alertas_pendientes: %d enviadas, %d rate-limited, "
        "%d sin pendientes (%d menciones marcadas)",
        enviadas, rate_limited, sin_pendientes, menciones_marcadas,
    )
    return {
        "enviadas": enviadas,
        "rate_limited": rate_limited,
        "sin_pendientes": sin_pendientes,
        "menciones_marcadas": menciones_marcadas,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolver_despachos_suscriptos(
    *,
    session: AsyncSession,
    padron: CsvPadronRepository,
) -> list[DespachoSuscrito]:
    """Carga `DespachoSuscrito` por cada despacho activo.

    - `perfil_interes`: el perfil sembrado, o `None` si no hay.
    - `legisladores`: 1 entrada por el legislador titular del despacho
      resuelto contra el CSV del padrón. Si el slug no resuelve en
      ninguna cámara, se omite.
    """
    despachos_repo = SqlAlchemyDespachoRepository(session)
    perfiles_repo = SqlAlchemyPerfilInteresDespachoRepository(session)
    despachos = await despachos_repo.listar()
    out: list[DespachoSuscrito] = []
    for despacho in despachos:
        perfil = await perfiles_repo.buscar_por_despacho(despacho.id)
        legisladores = _resolver_legisladores(despacho, perfil, padron)
        out.append(
            DespachoSuscrito(
                despacho_id=despacho.id,
                perfil_interes=perfil,
                legisladores=legisladores,
            ),
        )
    return out


def _resolver_legisladores(
    despacho: Despacho,
    perfil: PerfilInteresDespacho | None,
    padron: CsvPadronRepository,
) -> list[LegisladorAMonitorear]:
    """Resuelve el legislador titular del despacho contra el padrón.

    Prueba HCDN primero, luego HSN. Si no resuelve en ninguna, el
    despacho queda sin legisladores (procesará artículos para
    clasificación, pero no detectará menciones).

    Los `aliases_extra` salen del `perfil.aliases_legislador` si lo hay.
    """
    slug = getattr(despacho, "legislador_titular_slug", None)
    if not slug:
        return []
    legislador: Legislador | None = None
    for camara in (Camara.HCDN, Camara.HSN):
        try:
            legislador = padron.buscar_por_slug(slug, camara)
            break
        except KeyError:
            continue
    if legislador is None:
        log.warning(
            "Despacho %s tiene slug '%s' que no resuelve en padrón",
            despacho.id, slug,
        )
        return []

    aliases = list(perfil.aliases_legislador) if perfil else []
    return [
        LegisladorAMonitorear(
            legislador=legislador,
            legislador_id=legislador_uuid(
                slug=legislador.slug, camara=legislador.camara,
            ),
            despacho_id=despacho.id,
            aliases_extra=aliases,
        ),
    ]


def _construir_llm() -> LlmProvider:
    """Mismo selector que `praxis.api.deps.get_llm_provider`."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    return FakeLlmProvider()
