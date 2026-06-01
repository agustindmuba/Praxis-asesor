"""Caso de uso: buscar el antecedente histórico más parecido.

Spec 14 §"Algoritmos · Antecedente más parecido". Dado un expediente E
del despacho, devuelve el expediente histórico de misma área temática +
mismo tipo + estado terminal (sancionado, caduco, archivado) con mayor
similitud Jaccard sobre los tokens del título.

El cálculo de similitud es puro Python sobre títulos cargados de DB.
SQL solo trae candidatos pre-filtrados por área+tipo+estado.

Diseño: igual que `SugerirCofirmantes`, recibe `AsyncSession` directo.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
)
from praxis.domain import (
    JACCARD_UMBRAL,
    AntecedenteParecido,
    Camara,
    EstadoExpediente,
    ExpedienteNoEncontrado,
    NumeroExpediente,
    OrigenExpediente,
    jaccard,
    tokenizar_titulo,
)

# Estados que consideramos "terminales" (el expediente cerró su ciclo).
_ESTADOS_TERMINALES = [
    EstadoExpediente.SANCIONADO.value,
    EstadoExpediente.MEDIA_SANCION_HCDN.value,
    EstadoExpediente.MEDIA_SANCION_HSN.value,
    EstadoExpediente.CADUCO.value,
    EstadoExpediente.ARCHIVADO.value,
]

# Cuántos candidatos cargamos antes de hacer Jaccard. SQL trae los más
# recientes; Python rankea por similitud.
_CANDIDATOS_MAX = 50


class BuscarAntecedenteParecido:
    """Devuelve el antecedente más parecido o None."""

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
    ) -> AntecedenteParecido | None:
        expediente = await self._expedientes.buscar_por_id(expediente_id)
        if expediente is None:
            raise ExpedienteNoEncontrado(str(expediente_id), fuente="DB")

        clasif = await self._clasificaciones.buscar_por_expediente(expediente_id)
        if clasif is None:
            # Sin área no podemos rankear por tema.
            return None

        sql = text(
            """
            SELECT
                e.id AS id,
                e.numero AS numero,
                e.origen AS origen,
                e.anio AS anio,
                e.camara AS camara,
                e.titulo AS titulo,
                e.estado AS estado,
                e.fecha_ingreso AS fecha_ingreso
            FROM expediente e
            JOIN expediente_area_tematica eat ON eat.expediente_id = e.id
            WHERE eat.area = :area
              AND e.tipo = :tipo
              AND e.estado IN :estados
              AND e.id != :propio_id
            ORDER BY e.anio DESC, e.numero DESC
            LIMIT :limit
            """
        ).bindparams(
            bindparam("area", value=clasif.area.value),
            bindparam("tipo", value=expediente.tipo.value),
            bindparam("estados", value=_ESTADOS_TERMINALES, expanding=True),
            bindparam("propio_id", value=expediente_id),
            bindparam("limit", value=_CANDIDATOS_MAX),
        )

        result = await self._session.execute(sql)
        propios_tokens = tokenizar_titulo(expediente.titulo)
        if not propios_tokens:
            return None

        mejor: AntecedenteParecido | None = None
        for row in result:
            candidato_tokens = tokenizar_titulo(row.titulo or "")
            score = jaccard(propios_tokens, candidato_tokens)
            if score < JACCARD_UMBRAL:
                continue
            if mejor is not None and score <= mejor.similitud:
                continue
            try:
                numero = NumeroExpediente(
                    numero=row.numero,
                    origen=OrigenExpediente(row.origen),
                    anio=row.anio,
                    camara=Camara(row.camara),
                )
            except ValueError:
                continue
            mejor = AntecedenteParecido(
                numero=numero,
                titulo=row.titulo or "",
                estado_terminal=EstadoExpediente(row.estado),
                similitud=score,
            )

        return mejor
