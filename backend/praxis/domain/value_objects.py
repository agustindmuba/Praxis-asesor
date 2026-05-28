"""Value objects del dominio parlamentario.

Inmutables (`frozen=True`), con `slots=True` para prevenir typos y ahorrar
memoria. Sin dependencias externas — solo stdlib.

Definiciones formales y justificación: ver `docs/adr/0002-modelo-expediente.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Camara(StrEnum):
    """Cámara donde el expediente se tramita.

    No confundir con `OrigenExpediente`, que es quién lo presenta.
    """

    HCDN = "HCDN"
    HSN = "HSN"


class OrigenExpediente(StrEnum):
    """Origen del expediente (quién lo presenta).

    Ampliado en Amendment 1 del ADR 0002 (2026-05-27) con CD/CS/P/OV.
    `JEFATURA_GABINETE` renombrado desde `JEFATURA` para desambiguar.
    """

    DIPUTADO = "D"
    SENADOR = "S"
    EJECUTIVO = "PE"
    JEFATURA_GABINETE = "JGM"
    REVISION_DIPUTADOS = "CD"
    REVISION_SENADO = "CS"
    PARTICULAR = "P"
    OFICIAL_VARIOS = "OV"
    OTRO = "OTRO"

    @classmethod
    def from_code(cls, code: str) -> OrigenExpediente:
        """Convierte un código de origen tal como aparece en los portales."""
        code_upper = code.upper().strip()
        for member in cls:
            if member.value == code_upper:
                return member
        return cls.OTRO


class TipoExpediente(StrEnum):
    """Tipo de expediente parlamentario.

    Amendment 1 del ADR 0002 (2026-05-27): prefijo `PROYECTO_*` para enfatizar
    que trabajamos con expedientes en trámite (no normas sancionadas), y nuevo
    `MENSAJE_PE` para mensajes del Poder Ejecutivo.
    """

    PROYECTO_LEY = "proyecto_ley"
    PROYECTO_RESOLUCION = "proyecto_resolucion"
    PROYECTO_DECLARACION = "proyecto_declaracion"
    PROYECTO_COMUNICACION = "proyecto_comunicacion"
    MENSAJE_PE = "mensaje_pe"
    DECRETO = "decreto"
    OTRO = "otro"

    @classmethod
    def from_text(cls, text: str) -> TipoExpediente:
        """Mapea desde un texto libre del portal (ej. 'Proyecto De Ley').

        Para distinción contextual mensaje-vs-proyecto cuando el origen
        es PE/JGM, usar el parser HCDN (`_inferir_tipo`) que considera
        también el `OrigenExpediente`.
        """
        t = text.lower().strip()
        if "mensaje" in t:
            return cls.MENSAJE_PE
        if "ley" in t:
            return cls.PROYECTO_LEY
        if "resoluci" in t:
            return cls.PROYECTO_RESOLUCION
        if "declaraci" in t:
            return cls.PROYECTO_DECLARACION
        if "comunicaci" in t:
            return cls.PROYECTO_COMUNICACION
        if "decreto" in t:
            return cls.DECRETO
        return cls.OTRO


class EstadoExpediente(StrEnum):
    """Estado conocido del expediente.

    `DESCONOCIDO` es el default cuando el scraper no puede inferirlo desde
    el portal. La inferencia desde trámite/dictámenes va en una feature aparte
    (ver propuesta "inferencia de estado parlamentario desde trámite" en
    PRODUCT.md bloque 2).

    Amendment 1 del ADR 0002 (2026-05-27): `APROBADO_PARCIAL` se desdobla en
    `MEDIA_SANCION_HCDN` y `MEDIA_SANCION_HSN` para que el asesor sepa en
    qué cámara debe actuar a continuación. Las siglas (HCDN/HSN) preservan
    consistencia con el enum `Camara`.
    """

    INGRESADO = "ingresado"
    EN_COMISION = "en_comision"
    CON_DICTAMEN = "con_dictamen"
    MEDIA_SANCION_HCDN = "media_sancion_hcdn"
    MEDIA_SANCION_HSN = "media_sancion_hsn"
    SANCIONADO = "sancionado"
    ARCHIVADO = "archivado"
    CADUCO = "caduco"
    DESCONOCIDO = "desconocido"


# Regex para parsear "1497-D-2024" (HCDN) y "239/24" (HSN).
_HCDN_NUM_RE = re.compile(r"^\s*(\d{1,5})\s*-\s*([A-Z]+)\s*-\s*(\d{4})\s*$")
_HSN_NUM_RE = re.compile(r"^\s*(\d{1,5})\s*/\s*(\d{2}|\d{4})\s*$")


@dataclass(frozen=True, slots=True)
class NumeroExpediente:
    """Identificador único de un expediente dentro de una cámara y año."""

    numero: int
    origen: OrigenExpediente
    anio: int
    camara: Camara

    def __post_init__(self) -> None:
        if self.numero <= 0:
            raise ValueError(f"numero debe ser positivo, fue {self.numero}")
        if self.anio < 1983 or self.anio > 2100:
            raise ValueError(f"anio fuera de rango histórico razonable: {self.anio}")

    @classmethod
    def parse_hcdn(cls, raw: str) -> NumeroExpediente:
        """Parsea 'NNNN-X-YYYY' (estilo HCDN). Lanza ValueError si no matchea."""
        m = _HCDN_NUM_RE.match(raw)
        if not m:
            raise ValueError(f"Formato HCDN inválido: '{raw}' (esperado 'NNNN-X-YYYY')")
        return cls(
            numero=int(m.group(1)),
            origen=OrigenExpediente.from_code(m.group(2)),
            anio=int(m.group(3)),
            camara=Camara.HCDN,
        )

    @classmethod
    def parse_hsn(
        cls, raw: str, *, origen: OrigenExpediente = OrigenExpediente.SENADOR
    ) -> NumeroExpediente:
        """Parsea 'NNNN/YY' (estilo HSN).

        HSN no embebe el origen en el número (viene aparte en la URL).
        Default: SENADOR. El caller puede pasar otro si sabe que es CD/PE.
        """
        m = _HSN_NUM_RE.match(raw)
        if not m:
            raise ValueError(f"Formato HSN inválido: '{raw}' (esperado 'NNNN/YY')")
        anio_raw = int(m.group(2))
        # YY ambiguo: 00-49 -> 20XX, 50-99 -> 19XX. Heuristica estandar.
        anio = 2000 + anio_raw if anio_raw < 50 else 1900 + anio_raw if anio_raw < 100 else anio_raw
        return cls(numero=int(m.group(1)), origen=origen, anio=anio, camara=Camara.HSN)

    def format_hcdn(self) -> str:
        """Devuelve la forma canónica HCDN: 'NNNN-X-YYYY'."""
        return f"{self.numero:04d}-{self.origen.value}-{self.anio}"

    def format_hsn(self) -> str:
        """Devuelve la forma canónica HSN: 'NNNN/YY'."""
        return f"{self.numero}/{self.anio % 100:02d}"

    def __str__(self) -> str:
        return self.format_hcdn() if self.camara == Camara.HCDN else self.format_hsn()
