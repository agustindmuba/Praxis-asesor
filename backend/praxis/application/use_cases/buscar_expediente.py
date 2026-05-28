"""Caso de uso: buscar un expediente por número, rutando automáticamente
a la fuente correspondiente según la cámara.

Ver `docs/specs/03-normalizacion-modelo.md` para contexto y criterios.
"""

from __future__ import annotations

from praxis.application.ports import FuenteExpedientes
from praxis.domain import (
    Camara,
    Expediente,
    NumeroExpediente,
    TipoExpediente,
)


class BuscarExpediente:
    """Orquestador cámara-agnóstico sobre dos `FuenteExpedientes`.

    El llamador no necesita saber qué adaptador concreto usar: se le pasa
    el `NumeroExpediente` y el caso de uso despacha al puerto que
    corresponde según `numero.camara`.

    Args:
        hcdn: Puerto para expedientes de HCDN.
        hsn:  Puerto para expedientes de HSN.

    Errores propagados:
        - `ExpedienteNoEncontrado`, `FuenteNoDisponible`: tal cual del adaptador.
        - `ValueError`: si la cámara no es ni HCDN ni HSN.
    """

    def __init__(self, *, hcdn: FuenteExpedientes, hsn: FuenteExpedientes) -> None:
        self._hcdn = hcdn
        self._hsn = hsn

    async def execute(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        """Devuelve el `Expediente` desde la fuente que corresponde a `numero.camara`.

        Args:
            numero: Identificador del expediente.
            tipo: Tipo del expediente. Requerido por HSN, ignorado por HCDN.
                Ver `praxis.application.ports.FuenteExpedientes`.

        Raises:
            ValueError: si la cámara no es HCDN ni HSN, o si la fuente
                exige `tipo` y no se proveyó.
        """
        if numero.camara == Camara.HCDN:
            return await self._hcdn.buscar_por_numero(numero, tipo)
        if numero.camara == Camara.HSN:
            return await self._hsn.buscar_por_numero(numero, tipo)
        raise ValueError(f"Cámara no soportada por BuscarExpediente: {numero.camara}")
