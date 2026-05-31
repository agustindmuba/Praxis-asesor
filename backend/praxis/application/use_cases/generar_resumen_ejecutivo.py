"""Caso de uso: generar el resumen ejecutivo de un expediente.

Idempotente: si ya hay resumen cacheado en DB, lo devuelve sin llamar al
LLM. Si no, llama al `LlmProvider`, persiste y devuelve.

Ver `docs/specs/13-resumen-ejecutivo-ia.md`.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from praxis.application.ports import (
    ExpedienteRepository,
    LlmProvider,
    ResumenEjecutivoRepository,
)
from praxis.domain import (
    ExpedienteNoEncontrado,
    ResumenEjecutivo,
)


class GenerarResumenEjecutivo:
    """Orquesta cache + provider para devolver un ResumenEjecutivo.

    Flujo:
    1. Si hay resumen cacheado para `expediente_id` → devolverlo.
    2. Sino, buscar el expediente (404 si no existe).
    3. Llamar al provider → obtener contenido_md.
    4. Persistir el resumen + devolverlo.
    """

    def __init__(
        self,
        *,
        expedientes: ExpedienteRepository,
        resumenes: ResumenEjecutivoRepository,
        llm: LlmProvider,
    ) -> None:
        self._expedientes = expedientes
        self._resumenes = resumenes
        self._llm = llm

    async def execute(self, expediente_id: UUID) -> ResumenEjecutivo:
        cacheado = await self._resumenes.buscar_por_expediente(expediente_id)
        if cacheado is not None:
            return cacheado

        expediente = await self._expedientes.buscar_por_id(expediente_id)
        if expediente is None:
            raise ExpedienteNoEncontrado(str(expediente_id), fuente="DB")

        contenido_md = await self._llm.generar_resumen_ejecutivo(expediente)

        resumen = ResumenEjecutivo(
            id=uuid4(),
            expediente_id=expediente_id,
            contenido_md=contenido_md,
            modelo=self._llm.nombre_modelo,
        )
        return await self._resumenes.crear(resumen)
