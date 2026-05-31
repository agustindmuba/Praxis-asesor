"""Value objects para el Panel de Inteligencia de un expediente.

El panel responde una sola pregunta: ¿qué le digo al asesor sobre este
expediente que no podría ver en el portal HCDN?

Por ahora cubre:
- `ProgresoTramite`: dónde está en la pipeline y hace cuánto.
- `ComparacionPeers`: cómo se compara con otros del mismo tipo+cámara
  en el mismo estado.

Las otras 3 secciones (historial autor, relacionados, acciones) entrarán
en iteraciones siguientes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class EtapaPipeline(StrEnum):
    """Etapas resumidas del trámite parlamentario.

    Mapeamos los `EstadoExpediente` del modelo a 5 etapas visuales:
    Ingresado → En comisión → Con dictamen → Media sanción → Sancionado.
    Caduco/archivado salen de la pipeline (terminales sin éxito).
    """

    INGRESADO = "ingresado"
    EN_COMISION = "en_comision"
    CON_DICTAMEN = "con_dictamen"
    MEDIA_SANCION = "media_sancion"
    SANCIONADO = "sancionado"


@dataclass(frozen=True, slots=True)
class EtapaProgreso:
    """Una etapa de la pipeline visual."""

    etapa: EtapaPipeline
    label: str
    alcanzada: bool
    fecha: date | None = None


@dataclass(frozen=True, slots=True)
class ProgresoTramite:
    """Dónde está el expediente en la pipeline + hace cuánto."""

    etapa_actual: EtapaPipeline | None
    """Etapa que está atravesando. None si caducó/archivó/desconocido."""

    etapas: list[EtapaProgreso]
    """Las 5 etapas con flag de alcanzada (para pintar la barra)."""

    dias_en_etapa_actual: int | None
    """Días desde que entró a la etapa actual. None si no se puede calcular."""

    terminado: bool = False
    """True si el expediente terminó su trámite (sancionado/caduco/archivado)."""

    motivo_terminacion: str | None = None
    """Si terminado=True, breve mensaje (sancionado / caduco / archivado)."""


@dataclass(frozen=True, slots=True)
class ComparacionPeers:
    """Cómo se compara con otros expedientes 'peers'.

    Peer = mismo tipo + misma cámara + misma etapa actual.

    Los valores se miden sobre `dias_en_etapa_actual`. Si no hay peers
    suficientes (< 3), devolvemos `peer_count` pero no calculamos
    mediana/diferencia.
    """

    peer_count: int
    """Cuántos peers se compararon (excluyendo el propio)."""

    mediana_dias: int | None
    """Mediana de días en etapa de los peers. None si peer_count < 3."""

    diferencia_porcentual: float | None
    """Cuánto más rápido/lento que la mediana. Negativo = más rápido.

    Ej. -50.0 = el doble de rápido que la mediana.
    +100.0 = el doble de lento.
    None si no hay datos suficientes.
    """

    criterio: str
    """Texto humano del criterio: 'Mismo tipo y cámara'."""


@dataclass(frozen=True, slots=True)
class InteligenciaExpediente:
    """Bundle de inteligencia que devuelve el caso de uso."""

    progreso: ProgresoTramite
    peers: ComparacionPeers
