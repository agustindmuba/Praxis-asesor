"""FakeWhatsAppSender — implementación in-memory para dev / tests.

No hace red. Devuelve `message_id` sintético, registra cada envío en
una lista interna para inspección desde los tests, y permite simular
errores controlando `forzar_*` desde el constructor.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from praxis.application.ports import ResultadoEnvioWhatsApp, WhatsAppSender

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnvioRegistrado:
    """Snapshot de cada envío que el fake aceptó. Los tests inspeccionan
    `sender.envios` para verificar qué se mandó."""

    telefono_e164: str
    plantilla_name: str
    idioma: str
    body_params_ordered: list[str]
    message_id_sintetico: str


class FakeWhatsAppSender(WhatsAppSender):
    """Stub sin red. Configurable para devolver éxito / fallo / rechazo.

    Defaults a éxito siempre. Para forzar un tipo de respuesta:

        sender = FakeWhatsAppSender(modo_fallo="rechazado", error="opt_out")

    Modos disponibles:
    - "exitoso" (default): devuelve message_id sintético.
    - "fallido": exitoso=False, rechazado=False, error="fake_fallo".
    - "rechazado": exitoso=False, rechazado=True, error="fake_rechazado".
    """

    def __init__(
        self,
        *,
        modo_fallo: str = "exitoso",
        error: str | None = None,
        error_meta_code: int | None = None,
    ) -> None:
        self._modo = modo_fallo
        self._error = error
        self._error_meta_code = error_meta_code
        self._envios: list[EnvioRegistrado] = []

    @property
    def envios(self) -> list[EnvioRegistrado]:
        return list(self._envios)

    async def enviar(
        self,
        *,
        telefono_e164: str,
        plantilla_name: str,
        idioma: str,
        body_params_ordered: list[str],
    ) -> ResultadoEnvioWhatsApp:
        msg_id = f"wamid.fake.{uuid.uuid4().hex[:16]}"
        registro = EnvioRegistrado(
            telefono_e164=telefono_e164,
            plantilla_name=plantilla_name,
            idioma=idioma,
            body_params_ordered=list(body_params_ordered),
            message_id_sintetico=msg_id,
        )
        self._envios.append(registro)
        log.info(
            "FakeWhatsAppSender[%s] → %s %s (%d params)",
            self._modo, plantilla_name, telefono_e164,
            len(body_params_ordered),
        )

        if self._modo == "exitoso":
            return ResultadoEnvioWhatsApp(
                exitoso=True, message_id_meta=msg_id,
            )
        if self._modo == "rechazado":
            return ResultadoEnvioWhatsApp(
                exitoso=False,
                error=self._error or "fake_rechazado",
                rechazado=True,
                error_meta_code=self._error_meta_code,
            )
        return ResultadoEnvioWhatsApp(
            exitoso=False,
            error=self._error or "fake_fallo",
            rechazado=False,
            error_meta_code=self._error_meta_code,
        )
