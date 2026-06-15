"""Tests del generador iCal (feat-54.1)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from praxis.domain import EventoAgenda, TipoEventoAgenda
from praxis.infrastructure.calendar.ical import generar_ical

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Estructura mínima del feed
# ---------------------------------------------------------------------------


def test_feed_vacio_genera_estructura_minima() -> None:
    ical = generar_ical([])
    assert "BEGIN:VCALENDAR" in ical
    assert "END:VCALENDAR" in ical
    assert "VERSION:2.0" in ical
    assert "PRODID:-//Praxis Asesor" in ical
    assert "BEGIN:VEVENT" not in ical


def test_lineas_terminan_con_crlf() -> None:
    ical = generar_ical([])
    # RFC 5545 exige CRLF, no LF solo.
    assert "\r\n" in ical
    # Cada línea con CRLF (no debería haber LF solo).
    sin_crlf = ical.replace("\r\n", "")
    assert "\n" not in sin_crlf


def test_un_evento_dia_completo() -> None:
    ev = EventoAgenda(
        uid="praxis-efemeride-123@praxis-asesor.com",
        summary="Día de la Memoria",
        fecha_inicio=date(2026, 3, 24),
        tipo=TipoEventoAgenda.EFEMERIDE,
    )
    ical = generar_ical([ev])
    assert "UID:praxis-efemeride-123@praxis-asesor.com" in ical
    assert "SUMMARY:Día de la Memoria" in ical
    assert "DTSTART;VALUE=DATE:20260324" in ical
    # DTEND no se setea para día completo sin fecha_fin explícita.
    assert "DTEND" not in ical


def test_evento_con_hora_usa_utc() -> None:
    ev = EventoAgenda(
        uid="praxis-sesion-456@praxis-asesor.com",
        summary="Sesión Especial HCDN",
        fecha_inicio=datetime(2026, 5, 20, 14, 0, tzinfo=timezone.utc),
        fecha_fin=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
        tipo=TipoEventoAgenda.SESION_CONGRESO,
    )
    ical = generar_ical([ev])
    assert "DTSTART:20260520T140000Z" in ical
    assert "DTEND:20260520T180000Z" in ical


def test_evento_con_descripcion_y_url() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="Cita con bloque",
        fecha_inicio=date(2026, 6, 14),
        tipo=TipoEventoAgenda.REUNION_COMISION,
        descripcion="Reunión informal con jefa de bloque.",
        url_relacionada="https://app.praxis-asesor.com/briefings/123",
        ubicacion="Anexo C, Diputados",
    )
    ical = generar_ical([ev])
    assert "DESCRIPTION:Reunión informal con jefa de bloque." in ical
    assert "URL:https://app.praxis-asesor.com/briefings/123" in ical
    assert "LOCATION:Anexo C\\, Diputados" in ical  # coma escapada


def test_categorias_se_unen_por_coma() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="X",
        fecha_inicio=date(2026, 1, 1),
        tipo=TipoEventoAgenda.RECORDATORIO,
        categorias=["Salud", "Ambiente"],
    )
    ical = generar_ical([ev])
    assert "CATEGORIES:Salud,Ambiente" in ical


# ---------------------------------------------------------------------------
# Escape de caracteres especiales
# ---------------------------------------------------------------------------


def test_comma_en_summary_se_escapa() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="Día del padre, abuelo y mentor",
        fecha_inicio=date(2026, 6, 21),
        tipo=TipoEventoAgenda.EFEMERIDE,
    )
    ical = generar_ical([ev])
    assert "SUMMARY:Día del padre\\, abuelo y mentor" in ical


def test_semicolon_se_escapa() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="Sesión; con dictamen",
        fecha_inicio=date(2026, 6, 21),
        tipo=TipoEventoAgenda.SESION_CONGRESO,
    )
    ical = generar_ical([ev])
    assert "SUMMARY:Sesión\\; con dictamen" in ical


def test_newline_en_descripcion_se_convierte_a_literal() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="X",
        fecha_inicio=date(2026, 6, 21),
        tipo=TipoEventoAgenda.RECORDATORIO,
        descripcion="Línea 1\nLínea 2",
    )
    ical = generar_ical([ev])
    assert r"DESCRIPTION:Línea 1\nLínea 2" in ical


def test_backslash_se_dobla() -> None:
    ev = EventoAgenda(
        uid="x@x",
        summary="ruta C:\\proyectos",
        fecha_inicio=date(2026, 6, 21),
        tipo=TipoEventoAgenda.RECORDATORIO,
    )
    ical = generar_ical([ev])
    assert r"SUMMARY:ruta C:\\proyectos" in ical


# ---------------------------------------------------------------------------
# Validaciones del dominio
# ---------------------------------------------------------------------------


def test_uid_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="uid"):
        EventoAgenda(
            uid="",
            summary="X",
            fecha_inicio=date(2026, 1, 1),
            tipo=TipoEventoAgenda.RECORDATORIO,
        )


def test_summary_vacio_lanza() -> None:
    with pytest.raises(ValueError, match="summary"):
        EventoAgenda(
            uid="x@x",
            summary="   ",
            fecha_inicio=date(2026, 1, 1),
            tipo=TipoEventoAgenda.RECORDATORIO,
        )


def test_fin_antes_de_inicio_lanza() -> None:
    with pytest.raises(ValueError, match="fecha_fin"):
        EventoAgenda(
            uid="x@x",
            summary="X",
            fecha_inicio=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            fecha_fin=datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
            tipo=TipoEventoAgenda.RECORDATORIO,
        )


# ---------------------------------------------------------------------------
# Smoke múltiples eventos
# ---------------------------------------------------------------------------


def test_feed_con_varios_eventos_mantiene_orden() -> None:
    eventos = [
        EventoAgenda(
            uid=f"x-{i}@x",
            summary=f"Evento {i}",
            fecha_inicio=date(2026, 1, i + 1),
            tipo=TipoEventoAgenda.RECORDATORIO,
        )
        for i in range(3)
    ]
    ical = generar_ical(eventos)
    assert ical.count("BEGIN:VEVENT") == 3
    assert ical.count("END:VEVENT") == 3
    # Orden respetado
    pos_0 = ical.index("Evento 0")
    pos_1 = ical.index("Evento 1")
    pos_2 = ical.index("Evento 2")
    assert pos_0 < pos_1 < pos_2


def test_nombre_calendario_aparece_en_feed() -> None:
    ical = generar_ical(
        [], nombre_calendario="Calendario de Juliano",
        descripcion_calendario="Eventos del despacho",
    )
    assert "X-WR-CALNAME:Calendario de Juliano" in ical
    assert "X-WR-CALDESC:Eventos del despacho" in ical
