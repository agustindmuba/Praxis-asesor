"""Caso de uso: decidir si emitir una alerta de mención (anti-flood).

ADR 0009 §"Anti-flood" / spec 16 D6:

- Al detectar menciones nuevas (feat-40.5.B), las dejamos
  `notificada=False`.
- Periódicamente (Celery beat de 40.5.D), por cada despacho, este
  caso de uso decide si **agrupar** las pendientes en una **única**
  alerta o esperar.
- Política: **≤ 1 alerta agrupada por despacho por ventana** (default
  1 hora). Si hace < 1 hora hubo otra alerta, retenemos los pendientes
  para la próxima corrida (rate-limited).
- Cuando se decide enviar, marcamos atómicamente todos los IDs como
  `notificada=True` y devolvemos la intención al caller (el sender de
  WhatsApp en feat-41).

Importante: este caso de uso **NO realiza el envío real**. Sólo
identifica qué menciones se enviarían y mantiene el estado para
anti-flood. El envío real (HTTP a Meta) es responsabilidad de feat-41.

Limitación v1: el chequeo "hace < 1 hora hubo alerta" se aproxima
mirando `Mencion.notificada=True` con `detectado_en` dentro de la
ventana. Caso de borde: si las menciones fueron detectadas hace mucho
pero notificadas recién, el chequeo puede dar falso negativo. Cuando
se agregue `AlertaMencionEnviada` en feat-41, el caller puede mejorar
con el `enviado_en` real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from praxis.application.ports import MencionRepository
from praxis.domain import Mencion

# Default: ≤ 1 alerta agrupada por despacho por hora.
VENTANA_ANTI_FLOOD_DEFAULT = timedelta(hours=1)

# Cap de menciones por intención: si hay >N pendientes, sólo
# enviamos N en esta tanda; el resto queda para la próxima.
# Mantenemos el cap alto para no fragmentar; el envío real (WhatsApp)
# tiene su propio límite por tamaño de mensaje en feat-41.
MAX_MENCIONES_POR_INTENCION = 20

MotivoAlerta = Literal[
    "ok_enviar",
    "rate_limited_hace_menos_de_la_ventana",
    "sin_pendientes",
]


@dataclass(frozen=True, slots=True)
class IntencionDeAlerta:
    """Decisión del caso de uso sobre qué hacer con un despacho.

    - `ok_enviar`: `menciones` tiene 1+ items que el canal debería
      enviar como una **única** alerta agrupada. Las menciones ya
      fueron marcadas como `notificada=True` antes de devolverse — la
      atomicidad del repo asegura que no se manden dos veces aunque
      el caller falle el envío real (decisión consciente: preferimos
      pérdida ocasional vs. duplicado, ADR 0009).
    - `rate_limited_hace_menos_de_la_ventana`: hace < ventana hubo
      alerta. Los pendientes se quedan (no se marcan). Próxima corrida
      del Celery tick los reintenta.
    - `sin_pendientes`: no hay nada para notificar.
    """

    despacho_id: UUID
    motivo: MotivoAlerta
    menciones: list[Mencion] = field(default_factory=list)


class EnviarAlertaMencion:
    """Decisión + marcado atómico. NO realiza el envío real."""

    def __init__(self, *, menciones: MencionRepository) -> None:
        self._menciones = menciones

    async def ejecutar(
        self,
        despacho_id: UUID,
        *,
        ahora: datetime,
        ventana_anti_flood: timedelta = VENTANA_ANTI_FLOOD_DEFAULT,
        max_por_lote: int = MAX_MENCIONES_POR_INTENCION,
    ) -> IntencionDeAlerta:
        # 1. ¿Hay pendientes?
        pendientes = await self._menciones.listar_por_despacho_no_notificadas(
            despacho_id, limite=max_por_lote,
        )
        if not pendientes:
            return IntencionDeAlerta(
                despacho_id=despacho_id,
                motivo="sin_pendientes",
            )

        # 2. Chequeo anti-flood: ¿hubo alerta en la ventana?
        # Aproximación: mirar menciones con `notificada=True` y
        # `detectado_en` dentro de la ventana. Si existen → rate-limit.
        # (Cuando esté `AlertaMencionEnviada` en feat-41, el caller
        # puede pasar el `enviado_en` real al chequeo.)
        recientes = await self._menciones.listar_recientes_por_despacho(
            despacho_id,
            desde=ahora - ventana_anti_flood,
            hasta=ahora,
        )
        if any(m.notificada for m in recientes):
            return IntencionDeAlerta(
                despacho_id=despacho_id,
                motivo="rate_limited_hace_menos_de_la_ventana",
            )

        # 3. OK, mandamos. Marcado atómico antes de devolver para que
        # un fallo del canal NO duplique en la próxima corrida.
        ids = [m.id for m in pendientes if m.id is not None]
        await self._menciones.marcar_notificadas(ids)
        return IntencionDeAlerta(
            despacho_id=despacho_id,
            motivo="ok_enviar",
            menciones=pendientes,
        )
