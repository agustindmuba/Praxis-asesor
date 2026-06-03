"""Caso de uso: procesar un payload de webhook Meta WhatsApp (feat-41.3).

Recibe el payload ya parseado (status updates + mensajes inbound) y:

1. Por cada status update:
   - `EnvioWhatsAppRepository.actualizar_por_message_id` con el
     nuevo estado. Si Meta no nos reconoce el message_id (envío
     borrado por purga, etc.), simplemente loguea.
2. Por cada mensaje inbound:
   - Clasifica el body (opt_in / opt_out / None).
   - Si es opt_in: busca el destinatario por `(despacho_id implícito
     buscando en todos los despachos, telefono_e164)`. Si lo
     encuentra, actualiza con `opt_in_en=ahora` + `activo=True`.
   - Si es opt_out: mismo lookup, actualiza con `opt_out_en=ahora` +
     `activo=False`.
   - Si no encuentra destinatario, loguea (el number puede ser
     spam, o de un despacho que no existe).
   - Si no es opt_in/opt_out: loguea y sigue (en v1 no respondemos).

El caller (router HTTP) ya verificó la firma HMAC; este caso de uso
asume el payload es legítimo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from praxis.application.ports import (
    DespachoRepository,
    DestinatarioRepository,
    EnvioWhatsAppRepository,
)
from praxis.domain import Destinatario
from praxis.infrastructure.whatsapp.webhooks import (
    WebhookEvento,
    clasificar_inbound,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoWebhook:
    """Estadísticas para logging del endpoint."""

    statuses_actualizados: int
    statuses_desconocidos: int  # message_id no reconocido
    opt_ins_aplicados: int
    opt_outs_aplicados: int
    mensajes_ignorados: int  # no opt_in/opt_out o destinatario no encontrado
    errores: list[str] = field(default_factory=list)


class ProcesarWebhookWhatsApp:
    """Orquesta el procesamiento del webhook ya parseado y firmado."""

    def __init__(
        self,
        *,
        envios: EnvioWhatsAppRepository,
        destinatarios: DestinatarioRepository,
        despachos: DespachoRepository,
    ) -> None:
        self._envios = envios
        self._destinatarios = destinatarios
        self._despachos = despachos

    async def ejecutar(
        self,
        evento: WebhookEvento,
        *,
        ahora: datetime | None = None,
    ) -> ResultadoWebhook:
        ts = ahora or datetime.now(UTC)

        statuses_ok = 0
        statuses_desconocidos = 0
        opt_ins = 0
        opt_outs = 0
        ignorados = 0
        errores: list[str] = []

        # 1. Status updates.
        for s in evento.statuses:
            try:
                actualizado = await self._envios.actualizar_por_message_id(
                    message_id_meta=s.message_id_meta,
                    nuevo_estado=s.nuevo_estado.value,
                    error=s.error,
                )
                if actualizado is None:
                    statuses_desconocidos += 1
                    log.info(
                        "Status meta para mid=%s desconocido (envío purgado?)",
                        s.message_id_meta,
                    )
                else:
                    statuses_ok += 1
            except Exception as exc:
                errores.append(f"status {s.message_id_meta}: {exc}")
                log.warning(
                    "Falló actualizar status %s: %s",
                    s.message_id_meta, exc,
                )

        # 2. Inbound messages → opt-in/opt-out.
        for m in evento.mensajes:
            clasif = clasificar_inbound(m.body)
            if clasif is None:
                ignorados += 1
                log.info(
                    "Inbound de %s sin opt_in/opt_out: %s",
                    m.from_e164, m.body[:50],
                )
                continue
            dest = await self._buscar_destinatario_en_cualquier_despacho(
                telefono=m.from_e164,
            )
            if dest is None:
                ignorados += 1
                log.info(
                    "Inbound de %s clasificado como %s pero el "
                    "destinatario no existe en ningún despacho.",
                    m.from_e164, clasif,
                )
                continue
            try:
                if clasif == "opt_in":
                    await self._aplicar_opt_in(dest, ts=ts)
                    opt_ins += 1
                else:
                    await self._aplicar_opt_out(dest, ts=ts)
                    opt_outs += 1
            except Exception as exc:
                errores.append(
                    f"{clasif} {m.from_e164}: {exc}",
                )
                log.warning(
                    "Falló %s para %s: %s", clasif, m.from_e164, exc,
                )

        return ResultadoWebhook(
            statuses_actualizados=statuses_ok,
            statuses_desconocidos=statuses_desconocidos,
            opt_ins_aplicados=opt_ins,
            opt_outs_aplicados=opt_outs,
            mensajes_ignorados=ignorados,
            errores=errores,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _buscar_destinatario_en_cualquier_despacho(
        self, *, telefono: str,
    ) -> Destinatario | None:
        """v1: lookup linear sobre todos los despachos.

        Para volúmenes bajos (< 100 despachos) es OK. Si crece, agregar
        un puerto `buscar_destinatario_global_por_telefono` que use
        un índice sobre `telefono_e164` (no es UNIQUE global, pero
        hay índice compuesto que ayuda).
        """
        todos = await self._despachos.listar()
        for d in todos:
            dest = await self._destinatarios.buscar_por_telefono(
                despacho_id=d.id, telefono_e164=telefono,
            )
            if dest is not None:
                return dest
        return None

    async def _aplicar_opt_in(
        self, dest: Destinatario, *, ts: datetime,
    ) -> None:
        nuevo = Destinatario(
            id=dest.id,
            despacho_id=dest.despacho_id,
            usuario_id=dest.usuario_id,
            nombre=dest.nombre,
            rol_interno=dest.rol_interno,
            telefono_e164=dest.telefono_e164,
            recibe_briefing_diario=dest.recibe_briefing_diario,
            recibe_alertas_menciones=dest.recibe_alertas_menciones,
            recibe_alertas_otras=dest.recibe_alertas_otras,
            opt_in_en=ts,
            # Limpia opt_out anterior si lo había → reactivación.
            opt_out_en=None,
            activo=True,
        )
        await self._destinatarios.actualizar(nuevo)

    async def _aplicar_opt_out(
        self, dest: Destinatario, *, ts: datetime,
    ) -> None:
        # Si nunca hubo opt_in, ponemos uno fake en el mismo momento
        # para preservar la invariante (opt_out_en > opt_in_en).
        opt_in_en = dest.opt_in_en or ts
        nuevo = Destinatario(
            id=dest.id,
            despacho_id=dest.despacho_id,
            usuario_id=dest.usuario_id,
            nombre=dest.nombre,
            rol_interno=dest.rol_interno,
            telefono_e164=dest.telefono_e164,
            recibe_briefing_diario=dest.recibe_briefing_diario,
            recibe_alertas_menciones=dest.recibe_alertas_menciones,
            recibe_alertas_otras=dest.recibe_alertas_otras,
            opt_in_en=opt_in_en,
            opt_out_en=ts,
            activo=False,
        )
        await self._destinatarios.actualizar(nuevo)
