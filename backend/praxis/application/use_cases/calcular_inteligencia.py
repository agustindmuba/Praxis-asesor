"""Caso de uso: calcular el panel de Inteligencia de un expediente.

Diseño (anti-pattern controlado): este caso de uso recibe `AsyncSession`
directo en lugar de un puerto repo dedicado. Justificación:

- Es lógica de read-only puro, no muta nada.
- Las queries son ad-hoc y combinan agregaciones (PERCENTILE_CONT,
  EXTRACT, etc.) que no calzan en una interfaz de repo "ortodoxa".
- Crear un puerto `InteligenciaRepository` con un único método que
  encapsula 3 queries sería más prolijo pero también más opaco.

Si en el futuro hay 3+ consumidores de las mismas queries, refactoreamos
a puerto.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import ExpedienteRepository
from praxis.domain import (
    ComparacionPeers,
    EstadoExpediente,
    EtapaPipeline,
    EtapaProgreso,
    Expediente,
    ExpedienteNoEncontrado,
    InteligenciaExpediente,
    ProgresoTramite,
    TramiteEvento,
)

# Mapeo EstadoExpediente → EtapaPipeline para la barra visual.
_ESTADO_A_ETAPA: dict[EstadoExpediente, EtapaPipeline | None] = {
    EstadoExpediente.INGRESADO: EtapaPipeline.INGRESADO,
    EstadoExpediente.EN_COMISION: EtapaPipeline.EN_COMISION,
    EstadoExpediente.CON_DICTAMEN: EtapaPipeline.CON_DICTAMEN,
    EstadoExpediente.MEDIA_SANCION_HCDN: EtapaPipeline.MEDIA_SANCION,
    EstadoExpediente.MEDIA_SANCION_HSN: EtapaPipeline.MEDIA_SANCION,
    EstadoExpediente.SANCIONADO: EtapaPipeline.SANCIONADO,
    EstadoExpediente.CADUCO: None,
    EstadoExpediente.ARCHIVADO: None,
    EstadoExpediente.DESCONOCIDO: None,
}

# Etapas en orden de pipeline, con label legible.
_ETAPAS_ORDEN: list[tuple[EtapaPipeline, str]] = [
    (EtapaPipeline.INGRESADO, "Ingresado"),
    (EtapaPipeline.EN_COMISION, "En comisión"),
    (EtapaPipeline.CON_DICTAMEN, "Con dictamen"),
    (EtapaPipeline.MEDIA_SANCION, "Media sanción"),
    (EtapaPipeline.SANCIONADO, "Sancionado"),
]


# Palabras que sugieren cada etapa cuando aparecen en el `evento` del trámite.
# Se buscan case-insensitive vía LOWER en SQL.
_PATRONES_ETAPA: dict[EtapaPipeline, list[str]] = {
    EtapaPipeline.INGRESADO: ["ingreso", "presentaci"],
    EtapaPipeline.EN_COMISION: ["giro", "comisi"],
    EtapaPipeline.CON_DICTAMEN: ["dictamen"],
    EtapaPipeline.MEDIA_SANCION: ["sanci"],
    EtapaPipeline.SANCIONADO: ["sanci"],
}


class CalcularInteligenciaExpediente:
    """Devuelve `InteligenciaExpediente` con progreso + peers."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        expedientes: ExpedienteRepository,
    ) -> None:
        self._session = session
        self._expedientes = expedientes

    async def execute(self, expediente_id: UUID) -> InteligenciaExpediente:
        expediente = await self._expedientes.buscar_por_id(expediente_id)
        if expediente is None:
            raise ExpedienteNoEncontrado(str(expediente_id), fuente="DB")

        progreso = _calcular_progreso(expediente)
        peers = await self._calcular_peers(expediente, progreso)
        return InteligenciaExpediente(progreso=progreso, peers=peers)

    async def _calcular_peers(
        self,
        expediente: Expediente,
        progreso: ProgresoTramite,
    ) -> ComparacionPeers:
        """Compara contra peers: mismo tipo + cámara + estado."""
        criterio = "Mismo tipo y cámara, mismo estado"

        # Si no hay etapa actual (caducó/archivó/desconocido) no comparamos.
        if progreso.etapa_actual is None or progreso.dias_en_etapa_actual is None:
            return ComparacionPeers(
                peer_count=0,
                mediana_dias=None,
                diferencia_porcentual=None,
                criterio=criterio,
            )

        # Query: para cada expediente del mismo tipo+cámara+estado, días desde
        # el último evento de trámite (proxy de "tiempo en este estado").
        # Excluimos el expediente actual.
        # Nota: PERCENTILE_CONT 0.5 = mediana.
        sql = text(
            """
            WITH peers AS (
                SELECT
                    e.id AS exp_id,
                    MAX(t.fecha) AS ultimo_evento
                FROM expediente e
                LEFT JOIN tramite_evento t ON t.expediente_id = e.id
                WHERE e.tipo = :tipo
                  AND e.camara = :camara
                  AND e.estado = :estado
                  AND e.id != :propio_id
                GROUP BY e.id
            ),
            con_dias AS (
                SELECT
                    exp_id,
                    -- Postgres: date - date devuelve integer (días) directo,
                    -- no un interval, así que NO usar EXTRACT.
                    (CURRENT_DATE - ultimo_evento)::INT AS dias
                FROM peers
                WHERE ultimo_evento IS NOT NULL
            )
            SELECT
                COUNT(*)::INT AS peer_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dias)::INT AS mediana_dias
            FROM con_dias
            """
        ).bindparams(
            bindparam("tipo", value=expediente.tipo.value),
            bindparam("camara", value=expediente.numero.camara.value),
            bindparam("estado", value=expediente.estado.value),
            bindparam("propio_id", value=expediente.id),
        )

        result = await self._session.execute(sql)
        row = result.one()
        peer_count: int = row.peer_count or 0
        mediana_dias: int | None = row.mediana_dias

        diferencia: float | None = None
        if peer_count >= 3 and mediana_dias is not None and mediana_dias > 0:
            # Días propios vs mediana: <0 más rápido, >0 más lento.
            propios = progreso.dias_en_etapa_actual
            diferencia = ((propios - mediana_dias) / mediana_dias) * 100.0

        return ComparacionPeers(
            peer_count=peer_count,
            mediana_dias=mediana_dias if peer_count >= 3 else None,
            diferencia_porcentual=diferencia,
            criterio=criterio,
        )


# ---------------------------------------------------------------------------
# Cálculo de progreso (sin DB — solo el expediente)
# ---------------------------------------------------------------------------


def _calcular_progreso(expediente: Expediente) -> ProgresoTramite:
    """Devuelve la pipeline visual + días en la etapa actual."""
    etapa_actual = _ESTADO_A_ETAPA.get(expediente.estado)

    # Estados terminales sin éxito.
    terminado = False
    motivo_terminacion: str | None = None
    if expediente.estado == EstadoExpediente.CADUCO:
        terminado = True
        motivo_terminacion = "Caducó por Ley 13.640"
    elif expediente.estado == EstadoExpediente.ARCHIVADO:
        terminado = True
        motivo_terminacion = "Archivado sin sanción"
    elif expediente.estado == EstadoExpediente.SANCIONADO:
        terminado = True
        motivo_terminacion = "Sancionado (trámite cerrado con éxito)"

    fechas_por_etapa = _fechas_etapas_alcanzadas(expediente)

    etapas: list[EtapaProgreso] = []
    for etapa, label in _ETAPAS_ORDEN:
        alcanzada = _etapa_alcanzada(etapa, etapa_actual, expediente.estado)
        etapas.append(
            EtapaProgreso(
                etapa=etapa,
                label=label,
                alcanzada=alcanzada,
                fecha=fechas_por_etapa.get(etapa),
            )
        )

    dias_en_etapa_actual = _calcular_dias_en_etapa_actual(
        expediente, etapa_actual, fechas_por_etapa
    )

    return ProgresoTramite(
        etapa_actual=etapa_actual,
        etapas=etapas,
        dias_en_etapa_actual=dias_en_etapa_actual,
        terminado=terminado,
        motivo_terminacion=motivo_terminacion,
    )


def _etapa_alcanzada(
    etapa: EtapaPipeline,
    actual: EtapaPipeline | None,
    estado: EstadoExpediente,
) -> bool:
    """Una etapa está alcanzada si es <= la actual en el orden de pipeline.

    Si el expediente está sancionado, todas las etapas anteriores están
    también alcanzadas.
    """
    orden_etapa = [e for e, _ in _ETAPAS_ORDEN].index(etapa)
    if estado == EstadoExpediente.SANCIONADO:
        return True  # Sancionado significa que pasó por todas.
    if actual is None:
        # Caduco/archivado/desconocido: solo Ingresado se considera alcanzada.
        return etapa == EtapaPipeline.INGRESADO
    orden_actual = [e for e, _ in _ETAPAS_ORDEN].index(actual)
    return orden_etapa <= orden_actual


def _fechas_etapas_alcanzadas(expediente: Expediente) -> dict[EtapaPipeline, date]:
    """Devuelve la fecha en que cada etapa fue alcanzada por primera vez.

    Heurística: busca en `tramite` el primer evento cuyo texto matchee un
    patrón conocido para cada etapa. Si no encuentra, omite la entrada.
    """
    fechas: dict[EtapaPipeline, date] = {}

    # Fecha de ingreso = etapa Ingresado.
    if expediente.fecha_ingreso is not None:
        fechas[EtapaPipeline.INGRESADO] = expediente.fecha_ingreso

    eventos_ordenados = sorted(
        (t for t in expediente.tramite if t.fecha is not None),
        key=lambda t: t.fecha or date.min,
    )

    for evento in eventos_ordenados:
        evento_lower = evento.evento.lower()
        for etapa, patrones in _PATRONES_ETAPA.items():
            if etapa in fechas:
                continue
            if any(p in evento_lower for p in patrones):
                if evento.fecha is not None:
                    fechas[etapa] = evento.fecha
                break

    return fechas


def _calcular_dias_en_etapa_actual(
    expediente: Expediente,
    etapa_actual: EtapaPipeline | None,
    fechas_por_etapa: dict[EtapaPipeline, date],
) -> int | None:
    """Días desde que entró a la etapa actual hasta hoy.

    Estrategia:
    1. Si tenemos la fecha de inicio de la etapa actual → usar eso.
    2. Sino, usar el último evento del trámite.
    3. Sino, usar fecha_ingreso.
    """
    if etapa_actual is None:
        return None

    inicio: date | None = fechas_por_etapa.get(etapa_actual)
    if inicio is None:
        inicio = _ultimo_evento_fecha(expediente.tramite) or expediente.fecha_ingreso
    if inicio is None:
        return None

    hoy = datetime.now(UTC).date()
    return max((hoy - inicio).days, 0)


def _ultimo_evento_fecha(eventos: list[TramiteEvento]) -> date | None:
    con_fecha = [e.fecha for e in eventos if e.fecha is not None]
    return max(con_fecha) if con_fecha else None
