"""Caso de uso: sugerir cofirmantes naturales para un expediente.

Spec 14 §"Algoritmos · Cofirmantes naturales". Para un proyecto E del
despacho, devuelve los legisladores que con más frecuencia firmaron
proyectos del mismo área temática + mismo tipo en el último año.

Diseño (anti-pattern documentado, igual que `CalcularInteligenciaExpediente`):
recibe `AsyncSession` directo en lugar de un puerto repo dedicado, porque:
- Es lógica read-only que combina agregaciones SQL.
- Crear un puerto con un único método sería más prolijo pero más opaco.

Si en el futuro hay 3+ consumidores de la misma query, refactoreamos.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
)
from praxis.domain import (
    CofirmanteSugerido,
    ExpedienteNoEncontrado,
)

# Ventana de tiempo para considerar "actividad reciente". 18 meses
# captura cofirmantes activos sin diluir con expedientes muy viejos.
_VENTANA_DIAS = 18 * 30
# Cantidad de sugerencias devueltas al briefing.
_TOP_N = 5
# Mínimo de proyectos similares firmados para sumar al ranking.
_MIN_PROYECTOS = 2


class SugerirCofirmantes:
    """Para un expediente del despacho, devuelve cofirmantes potenciales."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        expedientes: ExpedienteRepository,
        clasificaciones: ExpedienteAreaTematicaRepository,
    ) -> None:
        self._session = session
        self._expedientes = expedientes
        self._clasificaciones = clasificaciones

    async def execute(
        self,
        expediente_id: UUID,
        *,
        excluir_bloques: Iterable[str] = (),
        excluir_firmantes: Iterable[str] = (),
    ) -> list[CofirmanteSugerido]:
        """Devuelve hasta `_TOP_N` cofirmantes ordenados por proyectos similares.

        Args:
            expediente_id: el proyecto del despacho para el que pedimos sugerencias.
            excluir_bloques: nombres de bloques a excluir (típicamente el bloque
                propio del despacho).
            excluir_firmantes: nombres de firmantes a excluir (típicamente el
                legislador titular del despacho — sus propias firmas no
                aportan).
        """
        expediente = await self._expedientes.buscar_por_id(expediente_id)
        if expediente is None:
            raise ExpedienteNoEncontrado(str(expediente_id), fuente="DB")

        # Necesitamos el área temática del proyecto. Si no está cacheada,
        # devolvemos vacío (no rompemos el briefing — el caller decide
        # mostrar "sin sugerencias" en el PDF).
        clasif = await self._clasificaciones.buscar_por_expediente(expediente_id)
        if clasif is None:
            return []

        hoy = date.today()
        desde = hoy - timedelta(days=_VENTANA_DIAS)

        excluir_bloques_list = [b.lower() for b in excluir_bloques if b]
        excluir_firmantes_list = [f.lower() for f in excluir_firmantes if f]

        sql = text(
            """
            SELECT
                f.nombre AS nombre,
                f.bloque AS bloque,
                f.distrito AS distrito,
                COUNT(DISTINCT e.id) AS proyectos
            FROM firmante f
            JOIN expediente e ON e.id = f.expediente_id
            JOIN expediente_area_tematica eat ON eat.expediente_id = e.id
            WHERE eat.area = :area
              AND e.tipo = :tipo
              AND e.fecha_ingreso >= :desde
              AND e.id != :propio_id
            GROUP BY f.nombre, f.bloque, f.distrito
            HAVING COUNT(DISTINCT e.id) >= :min_proyectos
            ORDER BY COUNT(DISTINCT e.id) DESC, f.nombre ASC
            LIMIT 50
            """
        ).bindparams(
            bindparam("area", value=clasif.area.value),
            bindparam("tipo", value=expediente.tipo.value),
            bindparam("desde", value=desde),
            bindparam("propio_id", value=expediente_id),
            bindparam("min_proyectos", value=_MIN_PROYECTOS),
        )

        result = await self._session.execute(sql)
        sugerencias: list[CofirmanteSugerido] = []
        for row in result:
            nombre_lower = (row.nombre or "").lower()
            bloque_lower = (row.bloque or "").lower()
            # Filtros locales (más fácil que parametrizarlos por SQL con
            # ANY/IN dinámico).
            if nombre_lower in excluir_firmantes_list:
                continue
            if bloque_lower and bloque_lower in excluir_bloques_list:
                continue
            sugerencias.append(
                CofirmanteSugerido(
                    nombre=row.nombre,
                    bloque=row.bloque,
                    distrito=row.distrito,
                    proyectos_similares_firmados=row.proyectos,
                    razon=_construir_razon(
                        row.proyectos, clasif.area.value, expediente.tipo.value
                    ),
                )
            )
            if len(sugerencias) >= _TOP_N:
                break

        return sugerencias


def _construir_razon(n: int, area: str, tipo: str) -> str:
    """Texto legible para el PDF del briefing."""
    plural = "proyecto" if n == 1 else "proyectos"
    tipo_legible = tipo.replace("_", " ")
    return (
        f"Firmó {n} {plural} similar{'es' if n != 1 else ''} de "
        f"{tipo_legible} sobre {area} en los últimos 18 meses."
    )
