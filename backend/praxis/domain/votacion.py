"""Entidades de dominio para votaciones nominales del recinto.

Modelo aprobado por ADR 0005 y validado contra el portal real por el
spike feat/26.1 (ver docs/spikes/26-votaciones-hcdn.md).

Una `Votacion` es **el acto del recinto**: una decisión nominal sobre
un asunto en un día y hora específicos, con un resultado agregado.

Un `VotoLegislador` es **cómo votó UN legislador en UNA votación**.
Identificamos al legislador por nombre + bloque + provincia como string
hasta que tengamos `Legislador` canónico (deuda asumida en ADR 0005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from praxis.domain.value_objects import Camara


class VotoTipo(StrEnum):
    """Cómo votó un legislador en una votación nominal.

    Mapea 1:1 con los valores que devuelve el portal HCDN:
    AFIRMATIVO, NEGATIVO, ABSTENCION, SIN VOTAR, AUSENTE.
    """

    AFIRMATIVO = "afirmativo"
    NEGATIVO = "negativo"
    ABSTENCION = "abstencion"
    SIN_VOTAR = "sin_votar"
    AUSENTE = "ausente"


class TipoVotacion(StrEnum):
    """Naturaleza de la votación.

    El portal distingue 'Votación Nominal' como tipo principal, pero
    el contenido varía: voto en general de un proyecto, moción de
    apartamiento de reglamento, moción de orden, capítulo de un
    dictamen, etc. Aproximación inicial: agrupamos en buckets útiles.
    """

    GENERAL = "general"          # voto en general de un proyecto/dictamen
    PARTICULAR = "particular"    # voto en particular (capítulo, artículo)
    MOCION = "mocion"            # moción sobre el reglamento
    OTRO = "otro"


@dataclass(frozen=True, slots=True)
class Votacion:
    """Una votación nominal del recinto.

    Frozen: lo que viene del portal es snapshot, no se muta.

    `expediente_id` es opcional: el portal HCDN no expone el número de
    expediente del proyecto votado de forma estructurada. El cruce se
    intenta vía `titulo_od` (parseado del asunto) → `OrdenDelDia` →
    expedientes incluidos (cruce diferido a spec 14, feat/29).

    `acta_id_hcdn` es el identificador propio del portal (ej 5937). Lo
    persistimos como UNIQUE para evitar duplicados y permitir links
    bidireccionales con el PDF oficial.
    """

    id: UUID | None
    camara: Camara
    fecha: date
    sesion: str               # ej "Período 144 - Reunión 3 - Acta 20"
    asunto: str               # texto libre del portal — el qué se votó
    tipo: TipoVotacion
    resultado_afirmativos: int
    resultado_negativos: int
    resultado_abstenciones: int
    resultado_sin_votar: int
    resultado_ausentes: int
    aprobada: bool
    presidida_por: str | None = None      # nombre del presidente de la sesión
    expediente_id: UUID | None = None
    titulo_od: str | None = None          # ej "O.D. 84"
    acta_id_hcdn: int | None = None       # id del portal
    acta_pdf_url: str | None = None
    fuente_url: str | None = None

    def __post_init__(self) -> None:
        if not self.sesion.strip():
            raise ValueError("Votacion.sesion no puede ser vacío")
        if not self.asunto.strip():
            raise ValueError("Votacion.asunto no puede ser vacío")
        if any(
            n < 0
            for n in (
                self.resultado_afirmativos,
                self.resultado_negativos,
                self.resultado_abstenciones,
                self.resultado_sin_votar,
                self.resultado_ausentes,
            )
        ):
            raise ValueError(
                "Votacion: conteos no pueden ser negativos "
                f"(af={self.resultado_afirmativos}, "
                f"neg={self.resultado_negativos}, "
                f"abs={self.resultado_abstenciones}, "
                f"sv={self.resultado_sin_votar}, "
                f"aus={self.resultado_ausentes})"
            )

    @property
    def total_votantes(self) -> int:
        """Cantidad de votos efectivos (no ausentes ni 'sin votar')."""
        return (
            self.resultado_afirmativos
            + self.resultado_negativos
            + self.resultado_abstenciones
        )


@dataclass(frozen=True, slots=True)
class VotoLegislador:
    """Cómo votó UN legislador en UNA votación.

    Sin FK a `Legislador` por ahora — el catálogo no existe todavía.
    Persistimos nombre/bloque/provincia como string. Cuando se construya
    el catálogo, una migración resolverá las FKs por matching de nombre.

    `legislador_hcdn_id` es el identificador estable del portal
    (ej "A51126" del URL /assets/diputados/A51126). Lo persistimos como
    string opcional — es la mejor llave de joineo futura al catálogo.
    """

    legislador_nombre: str            # APELLIDO, NOMBRE (formato del portal)
    voto: VotoTipo
    bloque: str | None = None
    distrito: str | None = None       # "provincia" en el portal
    que_dijo: str | None = None       # texto de la columna "¿QUÉ DIJO?"
    legislador_hcdn_id: str | None = None

    def __post_init__(self) -> None:
        if not self.legislador_nombre.strip():
            raise ValueError("VotoLegislador.legislador_nombre no puede ser vacío")
