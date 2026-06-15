"""Generador de feeds iCal RFC 5545 puro — sin librerías externas.

iCal es un formato textual simple. Lo generamos a mano para evitar
dependencias innecesarias y poder controlar exactamente cada campo.

Compatible con Google Calendar, Apple Calendar, Outlook, Thunderbird,
y cualquier cliente que respete el RFC.

Reglas duras del RFC:
- Líneas con CRLF (\\r\\n) — no LF solo.
- Cada propiedad va en una línea, sin partir.
- Strings con comas, punto y coma o backslash deben escaparse.
- Newlines dentro de strings: como `\\n` (literal).
- Fechas de día completo: `VALUE=DATE:YYYYMMDD`.
- Datetimes: `YYYYMMDDTHHMMSSZ` para UTC.

Sin TZ awareness por simplicidad — usamos UTC para datetimes y
DATE para días completos. El calendario del usuario los muestra
en su zona local automáticamente.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from praxis.domain.evento_agenda import EventoAgenda

CRLF = "\r\n"

# Identificador único del producto que genera el feed (RFC requiere PRODID).
PRODID = "-//Praxis Asesor//Calendario despacho 1.0//ES"


def generar_ical(
    eventos: list[EventoAgenda],
    *,
    nombre_calendario: str = "Praxis Asesor — Despacho",
    descripcion_calendario: str | None = None,
) -> str:
    """Serializa una lista de eventos al formato iCal completo.

    Output válido para servir directamente como `text/calendar` desde
    un endpoint HTTP. Los clientes lo procesan tal cual.
    """
    lineas: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(nombre_calendario)}",
    ]
    if descripcion_calendario:
        lineas.append(f"X-WR-CALDESC:{_escape(descripcion_calendario)}")

    timestamp_now = _format_datetime_utc(datetime.now(timezone.utc))

    for ev in eventos:
        lineas.append("BEGIN:VEVENT")
        lineas.append(f"UID:{ev.uid}")
        lineas.append(f"DTSTAMP:{timestamp_now}")
        lineas.append(f"SUMMARY:{_escape(ev.summary)}")

        if ev.es_dia_completo:
            # Día completo: solo DATE.
            lineas.append(f"DTSTART;VALUE=DATE:{_format_date(ev.fecha_inicio)}")
            if ev.fecha_fin is not None:
                # iCal: DTEND para día completo es EXCLUSIVO — agregar 1 día
                # si el usuario nos pasó la fecha del último día.
                from datetime import timedelta as _td
                fin_d = ev.fecha_fin if isinstance(ev.fecha_fin, date) else ev.fecha_fin.date()
                lineas.append(
                    f"DTEND;VALUE=DATE:{_format_date(fin_d + _td(days=1))}"
                )
        else:
            assert isinstance(ev.fecha_inicio, datetime)
            lineas.append(f"DTSTART:{_format_datetime_utc(ev.fecha_inicio)}")
            if isinstance(ev.fecha_fin, datetime):
                lineas.append(f"DTEND:{_format_datetime_utc(ev.fecha_fin)}")

        if ev.descripcion:
            lineas.append(f"DESCRIPTION:{_escape(ev.descripcion)}")
        if ev.ubicacion:
            lineas.append(f"LOCATION:{_escape(ev.ubicacion)}")
        if ev.url_relacionada:
            lineas.append(f"URL:{ev.url_relacionada}")
        if ev.categorias:
            # RFC: CATEGORIES separadas por coma.
            cats = ",".join(_escape(c) for c in ev.categorias)
            lineas.append(f"CATEGORIES:{cats}")

        lineas.append("END:VEVENT")

    lineas.append("END:VCALENDAR")
    return CRLF.join(lineas) + CRLF


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Escapa caracteres especiales de iCal (RFC 5545 §3.3.11).

    Orden importa: backslash primero para no doblescapar.
    """
    return (
        s.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _format_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def _format_datetime_utc(dt: datetime) -> str:
    """Formato UTC: YYYYMMDDTHHMMSSZ. Si dt no tiene tz, asume UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")
