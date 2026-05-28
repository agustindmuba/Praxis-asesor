"""Caso de uso: enriquecer un `Expediente` con estado y caducidad inferidos.

Wrapper trivial sobre `praxis.domain.inferencia_estado.inferir_estado_y_caducidad`
que muta los campos correspondientes del `Expediente` y lo devuelve para
permitir chaining.

Ver `docs/specs/07-inferencia-estado.md`.
"""

from __future__ import annotations

from datetime import date

from praxis.domain import Expediente
from praxis.domain.inferencia_estado import inferir_estado_y_caducidad


class EnriquecerExpediente:
    """Aplica la inferencia de estado + caducidad sobre un `Expediente`.

    Sin estado interno; instanciarlo es opcional (sirve solo para satisfacer
    el contrato del puerto si en el futuro hay alternativas).
    """

    def execute(
        self,
        expediente: Expediente,
        *,
        hoy: date | None = None,
    ) -> Expediente:
        """Muta `expediente` con los campos derivados y lo devuelve.

        Args:
            expediente: snapshot a enriquecer. Se muta in-place.
            hoy: inyección para tests (default `date.today()`).

        Returns:
            El mismo `expediente` (chaining-friendly).
        """
        inf = inferir_estado_y_caducidad(expediente, hoy=hoy)
        expediente.estado = inf.estado
        expediente.fecha_caducidad = inf.fecha_caducidad
        expediente.fecha_caducidad_original = inf.fecha_caducidad_original
        expediente.prorrogado = inf.prorrogado
        return expediente
