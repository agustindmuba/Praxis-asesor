"""Caso de uso: clasificar tematicamente un expediente.

Idempotente: si ya hay cache de clasificación, lo devuelve sin llamar al
LLM. Si no, llama al `LlmProvider.clasificar_area_tematica()`, persiste
y devuelve.

Ver `docs/specs/14-briefing-pre-sesion.md` §"Algoritmos · Clasificación
temática".
"""

from __future__ import annotations

from uuid import UUID, uuid4

from praxis.application.ports import (
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
    LlmProvider,
)
from praxis.domain import (
    CLASIFICACION_PROMPT_VERSION,
    ExpedienteAreaTematica,
    ExpedienteNoEncontrado,
)


class ClasificarExpedienteTematicamente:
    """Orquesta cache + provider para devolver una clasificación temática.

    Flujo:
    1. Si hay cache para `expediente_id` → devolverlo.
    2. Sino, buscar el expediente (404 si no existe).
    3. Llamar al provider → obtener AreaTematica.
    4. Persistir el cache + devolverlo.
    """

    def __init__(
        self,
        *,
        expedientes: ExpedienteRepository,
        clasificaciones: ExpedienteAreaTematicaRepository,
        llm: LlmProvider,
    ) -> None:
        self._expedientes = expedientes
        self._clasificaciones = clasificaciones
        self._llm = llm

    async def execute(self, expediente_id: UUID) -> ExpedienteAreaTematica:
        cacheado = await self._clasificaciones.buscar_por_expediente(expediente_id)
        if cacheado is not None:
            return cacheado

        expediente = await self._expedientes.buscar_por_id(expediente_id)
        if expediente is None:
            raise ExpedienteNoEncontrado(str(expediente_id), fuente="DB")

        area = await self._llm.clasificar_area_tematica(expediente)

        cache = ExpedienteAreaTematica(
            id=uuid4(),
            expediente_id=expediente_id,
            area=area,
            modelo=self._llm.nombre_modelo,
            prompt_version=CLASIFICACION_PROMPT_VERSION,
        )
        return await self._clasificaciones.crear(cache)
