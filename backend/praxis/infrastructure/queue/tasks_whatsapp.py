"""Celery tasks del canal WhatsApp (spec 17, feat-41.4).

1 task programada por Beat:

- `praxis.whatsapp.enviar_briefings_diarios` (07:00 ART = 10:00 UTC):
  Por cada despacho activo, dispara `EnviarBriefingDiario` con la
  fecha de HOY. Cada despacho se commitea por separado para que un
  error puntual no pierda los envíos de los otros.

El sender se selecciona según settings: si `meta_whatsapp_token` está
configurado → `WhatsAppCloudApiSender`, sino `FakeWhatsAppSender` (no
gasta API, no manda nada real).
"""

from __future__ import annotations

import asyncio        # noqa: F401  — legacy, sustituido por run_task_async
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from praxis.application.use_cases import EnviarBriefingDiario
from praxis.config import get_settings
from praxis.infrastructure.db.engine import engine
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyDespachoRepository,
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyNormaBOAccionableRepository,
)
from praxis.infrastructure.queue._async_runtime import run_task_async
from praxis.infrastructure.queue.celery_app import celery_app
from praxis.infrastructure.whatsapp import (
    FakeWhatsAppSender,
    WhatsAppCloudApiSender,
)

log = logging.getLogger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="praxis.whatsapp.enviar_briefings_diarios",
    # N despachos × M destinatarios × latencia Meta (~0.5-2s por envío).
    # En MVP con ≤100 despachos × ≤5 destinatarios ≈ ≤500 envíos × 2s
    # ≈ ~17 min. Margen 20 min hard.
    time_limit=1200,
    soft_time_limit=1080,
)
def enviar_briefings_diarios_task() -> dict[str, int]:
    """Por cada despacho activo, manda el briefing diario por
    WhatsApp.

    Devuelve un agregado de contadores para Flower."""
    return run_task_async(_enviar_briefings_diarios_async())


async def _enviar_briefings_diarios_async() -> dict[str, int]:
    ahora = datetime.now(UTC)
    fecha = ahora.date()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    sender = _construir_sender()

    total_objetivo = 0
    total_enviados = 0
    total_fallidos = 0
    total_rechazados = 0
    despachos_sin_contenido = 0

    try:
        async with sessionmaker() as session_listado:
            despachos = await SqlAlchemyDespachoRepository(
                session_listado,
            ).listar()
            log.info(
                "whatsapp.enviar_briefings_diarios: %d despachos para %s",
                len(despachos), fecha.isoformat(),
            )

        for despacho in despachos:
            try:
                async with sessionmaker() as session:
                    uc = EnviarBriefingDiario(
                        destinatarios=SqlAlchemyDestinatarioRepository(session),
                        envios=SqlAlchemyEnvioWhatsAppRepository(session),
                        accionables_bo=SqlAlchemyNormaBOAccionableRepository(
                            session,
                        ),
                        relevantes_noticias=SqlAlchemyArticuloRelevanteRepository(
                            session,
                        ),
                        sender=sender,
                    )
                    r = await uc.ejecutar(
                        despacho_id=despacho.id, fecha=fecha, ahora=ahora,
                    )
                    await session.commit()
                    total_objetivo += r.destinatarios_objetivo
                    total_enviados += r.enviados_ok
                    total_fallidos += r.fallidos_transitorios
                    total_rechazados += r.rechazados
                    if r.sin_contenido:
                        despachos_sin_contenido += 1
                    log.info(
                        "briefing[%s]: %d ok, %d fallidos, %d rechazados, "
                        "sin_contenido=%s",
                        despacho.id, r.enviados_ok,
                        r.fallidos_transitorios, r.rechazados,
                        r.sin_contenido,
                    )
            except Exception as exc:
                log.exception(
                    "briefing[%s] falló: %s", despacho.id, exc,
                )
    finally:
        # Cerrar el cliente HTTP del sender real, si aplica.
        if isinstance(sender, WhatsAppCloudApiSender):
            await sender.aclose()

    return {
        "destinatarios_objetivo": total_objetivo,
        "enviados_ok": total_enviados,
        "fallidos_transitorios": total_fallidos,
        "rechazados": total_rechazados,
        "despachos_sin_contenido": despachos_sin_contenido,
    }


def _construir_sender() -> FakeWhatsAppSender | WhatsAppCloudApiSender:
    """Mismo selector que `praxis.api.deps.get_whatsapp_sender`."""
    settings = get_settings()
    if (
        settings.meta_whatsapp_token
        and settings.meta_whatsapp_phone_number_id
    ):
        return WhatsAppCloudApiSender(
            access_token=settings.meta_whatsapp_token,
            phone_number_id=settings.meta_whatsapp_phone_number_id,
        )
    return FakeWhatsAppSender()
