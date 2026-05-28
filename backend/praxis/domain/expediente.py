"""Entidades de dominio: Expediente, Firmante, Giro, TramiteEvento.

Ver `docs/adr/0002-modelo-expediente.md` para la justificación del modelo.
Sin dependencias externas — solo stdlib. Tipado estricto (mypy --strict).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    TipoExpediente,
)


@dataclass(frozen=True, slots=True)
class Firmante:
    """Firmante de un expediente.

    `nombre` es texto libre del portal hasta que se mapee a `Legislador`
    (feature 5).
    """

    nombre: str
    distrito: str | None = None
    bloque: str | None = None
    orden: int = 1

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("Firmante.nombre no puede ser vacío")
        if self.orden < 1:
            raise ValueError(f"Firmante.orden debe ser >= 1, fue {self.orden}")


@dataclass(frozen=True, slots=True)
class Giro:
    """Giro del expediente a una comisión.

    `comision` es texto libre del portal hasta que se mapee a `Comision`
    (feature 6).
    """

    comision: str
    fecha_ingreso: date | None = None
    fecha_egreso: date | None = None
    orden: int | None = None

    def __post_init__(self) -> None:
        if not self.comision.strip():
            raise ValueError("Giro.comision no puede ser vacío")
        if (
            self.fecha_ingreso is not None
            and self.fecha_egreso is not None
            and self.fecha_egreso < self.fecha_ingreso
        ):
            raise ValueError(
                f"Giro: fecha_egreso ({self.fecha_egreso}) < fecha_ingreso ({self.fecha_ingreso})"
            )


@dataclass(frozen=True, slots=True)
class TramiteEvento:
    """Evento en el trámite de un expediente.

    Event-log uniforme entre cámaras. El campo `fuente` deja trazabilidad
    de si el evento vino directo del portal (HCDN) o fue derivado de
    timestamps de etapas (HSN). Ver ADR 0002.
    """

    fecha: date | None
    camara: Camara
    evento: str
    detalle: str | None = None
    fuente: str | None = None

    def __post_init__(self) -> None:
        if not self.evento.strip():
            raise ValueError("TramiteEvento.evento no puede ser vacío")


@dataclass(slots=True)
class Expediente:
    """Snapshot de un expediente parlamentario.

    Mutable: un caso de uso puede enriquecerlo (vincular firmantes con
    legisladores, inferir estado, etc.). Pero las listas internas se
    construyen con `field(default_factory=list)`, no mutamos defaults.
    """

    numero: NumeroExpediente
    tipo: TipoExpediente
    titulo: str
    # ID interno de persistencia (UUID v7). None hasta que el expediente
    # se persiste por primera vez. Ver ADR 0003 §1.
    id: UUID | None = None
    sumario: str | None = None
    fecha_ingreso: date | None = None
    estado: EstadoExpediente = EstadoExpediente.DESCONOCIDO
    firmantes: list[Firmante] = field(default_factory=list)
    giros: list[Giro] = field(default_factory=list)
    tramite: list[TramiteEvento] = field(default_factory=list)
    texto_url: str | None = None
    fuente_url: str | None = None

    # Amendment 1 del ADR 0002 (2026-05-27):
    # Vínculo informativo y unidireccional con otro expediente (caso típico:
    # CD/CS, mismo proyecto que cruza entre cámaras). No hay garantía de
    # consistencia bidireccional: si A apunta a B, B no necesariamente
    # apunta a A. El matching automático es feature futura.
    expediente_relacionado: NumeroExpediente | None = None

    # Caducidad parlamentaria (Ley 13.640). Modelo listo para alertas;
    # la lógica de cálculo entra en una feature posterior. El campo
    # `original` permite mostrar "vence el X, originalmente vencía el Y"
    # cuando hubo prórroga.
    fecha_caducidad: date | None = None
    fecha_caducidad_original: date | None = None
    prorrogado: bool = False

    def __post_init__(self) -> None:
        if not self.titulo.strip():
            raise ValueError("Expediente.titulo no puede ser vacío")

    @property
    def camara(self) -> Camara:
        """Atajo: la cámara donde se tramita."""
        return self.numero.camara

    @property
    def autor_principal(self) -> Firmante | None:
        """Devuelve el firmante con orden=1, o None si no hay firmantes."""
        for f in sorted(self.firmantes, key=lambda x: x.orden):
            return f
        return None

    def tramite_ordenado(self) -> list[TramiteEvento]:
        """Devuelve el trámite ordenado por fecha ascendente; eventos sin fecha al final."""
        con_fecha = [t for t in self.tramite if t.fecha is not None]
        sin_fecha = [t for t in self.tramite if t.fecha is None]
        # MyPy no infiere que después del filtro `fecha` es no-None, así que key con guard.
        con_fecha.sort(key=lambda t: t.fecha if t.fecha is not None else date.max)
        return con_fecha + sin_fecha
