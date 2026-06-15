"""EventoAgenda — eventos del despacho para el feed iCal (feat-54.1).

Representa un evento abstracto que terminará en el calendario del
asesor (Google / Apple / Outlook / etc.). Las fuentes posibles son:

- Sesiones del Congreso (detectadas por feat-45)
- Vencimientos por caducidad de proyectos vivos del despacho
- Efemérides relevantes según el perfil del despacho
- Reuniones de comisión (cuando las tengamos)
- Cualquier otro hito agendable

El generador iCal vive en `infrastructure.calendar.ical` — el dominio
solo describe QUÉ se agenda, no CÓMO se serializa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class TipoEventoAgenda(StrEnum):
    """Categoriza el evento para que el calendario lo coloree consistente."""

    SESION_CONGRESO = "sesion_congreso"
    REUNION_COMISION = "reunion_comision"
    VENCIMIENTO_CADUCIDAD = "vencimiento_caducidad"
    EFEMERIDE = "efemeride"
    RECORDATORIO = "recordatorio"


# Etiquetas legibles para usar en el SUMMARY de iCal cuando hace falta
# prefijar el título con el tipo.
EVENTO_AGENDA_PREFIX: dict[TipoEventoAgenda, str] = {
    TipoEventoAgenda.SESION_CONGRESO: "Sesión",
    TipoEventoAgenda.REUNION_COMISION: "Comisión",
    TipoEventoAgenda.VENCIMIENTO_CADUCIDAD: "Vence",
    TipoEventoAgenda.EFEMERIDE: "Efeméride",
    TipoEventoAgenda.RECORDATORIO: "Recordatorio",
}


@dataclass(frozen=True, slots=True)
class EventoAgenda:
    """Un evento atómico para el calendario del despacho.

    Identidad: `uid` — usado como UID en el iCal para que el calendario
    distinga updates de eventos repetidos vs eventos nuevos. Por
    convención: `praxis-<tipo>-<source_id>@praxis-asesor.com`.

    Eventos de día completo: dejar `fecha_inicio: date` y
    `fecha_fin: date` (o None — usa fecha_inicio + 1 día implícito).
    Eventos con hora: usar datetime para ambos.

    Triplete obligatorio: uid + summary + fecha_inicio.
    """

    uid: str
    summary: str                              # título del evento (corto, sin newlines)
    fecha_inicio: date | datetime
    tipo: TipoEventoAgenda
    fecha_fin: date | datetime | None = None  # None ⇒ día completo, 1 día
    descripcion: str | None = None            # cuerpo, puede ser multilínea
    url_relacionada: str | None = None        # ej. link al briefing / al expediente
    ubicacion: str | None = None              # para reuniones (Congreso, comisión X)
    categorias: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.uid.strip():
            raise ValueError("EventoAgenda.uid no puede estar vacío")
        if not self.summary.strip():
            raise ValueError("EventoAgenda.summary no puede estar vacío")
        # Si ambos son datetime, fecha_fin >= fecha_inicio
        if isinstance(self.fecha_fin, datetime) and isinstance(self.fecha_inicio, datetime):
            if self.fecha_fin < self.fecha_inicio:
                raise ValueError(
                    f"EventoAgenda.fecha_fin ({self.fecha_fin}) < fecha_inicio "
                    f"({self.fecha_inicio})"
                )

    @property
    def es_dia_completo(self) -> bool:
        return isinstance(self.fecha_inicio, date) and not isinstance(
            self.fecha_inicio, datetime
        )
