"""Generar el feed iCal del despacho (feat-54.2).

Junta eventos de múltiples fuentes en una sola lista de
`EventoAgenda` y delega la serialización a `infrastructure.calendar.ical`.

Fuentes incluidas hoy:
1. **Efemérides** próximas (60 días) con relevancia ≥ media.
2. **Sesiones del Congreso** detectadas (OD con fecha_sesion futura).
3. **Vencimientos por caducidad** de proyectos seguidos por el despacho
   (recordatorios 30 / 7 / 1 día antes).

Diseñado para correr en cada GET del feed (~100ms — el corpus es chico).
No cachea — el cliente del calendario respeta el HTTP Cache-Control que
seteamos en el router.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import EfemerideRepository
from praxis.domain import EventoAgenda, TipoEventoAgenda

log = logging.getLogger(__name__)

VENTANA_DIAS_EFEMERIDES = 60
RECORDATORIOS_CADUCIDAD = (30, 7, 1)


@dataclass(frozen=True, slots=True)
class CalendarioGenerado:
    eventos: list[EventoAgenda]
    nombre: str
    descripcion: str


class GenerarCalendarioDespacho:
    """Use case que arma el feed iCal de UN despacho."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        efemerides: EfemerideRepository,
    ) -> None:
        self._session = session
        self._efemerides = efemerides

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        nombre_despacho: str,
    ) -> CalendarioGenerado:
        eventos: list[EventoAgenda] = []
        eventos.extend(await self._eventos_efemerides())
        eventos.extend(await self._eventos_sesiones())
        eventos.extend(await self._eventos_caducidad(despacho_id))

        log.info(
            "calendario.generado",
            despacho_id=str(despacho_id),
            eventos=len(eventos),
        )

        return CalendarioGenerado(
            eventos=eventos,
            nombre=f"Praxis Asesor — {nombre_despacho}",
            descripcion=(
                "Sesiones del Congreso, vencimientos de proyectos del "
                "despacho y efemérides relevantes. Actualizado en tiempo "
                "real desde Praxis."
            ),
        )

    # ------------------------------------------------------------------
    # Fuente 1: efemérides próximas
    # ------------------------------------------------------------------
    async def _eventos_efemerides(self) -> list[EventoAgenda]:
        hoy = date.today()
        efs = await self._efemerides.proximas(
            desde_mes=hoy.month,
            desde_dia=hoy.day,
            dias=VENTANA_DIAS_EFEMERIDES,
            relevancia_minima="media",
        )
        eventos: list[EventoAgenda] = []
        for ef in efs:
            # Las efemérides recurrentes usan el AÑO ACTUAL (o el
            # siguiente si ya pasaron) — para que el calendario las
            # muestre en el futuro inmediato.
            anio = ef.anio_unico or _proxima_ocurrencia(hoy, ef.mes, ef.dia).year
            fecha_ev = date(anio, ef.mes, ef.dia)
            eventos.append(
                EventoAgenda(
                    uid=f"praxis-efemeride-{ef.id}@praxis-asesor.com",
                    summary=f"📅 {ef.titulo}",
                    fecha_inicio=fecha_ev,
                    tipo=TipoEventoAgenda.EFEMERIDE,
                    descripcion=ef.descripcion,
                    categorias=["Efeméride", *ef.areas_tematicas],
                )
            )
        return eventos

    # ------------------------------------------------------------------
    # Fuente 2: sesiones detectadas
    # ------------------------------------------------------------------
    async def _eventos_sesiones(self) -> list[EventoAgenda]:
        """Sesiones con fecha_sesion >= hoy, fuente scraping."""
        r = await self._session.execute(text("""
            SELECT id, titulo, fecha_sesion
            FROM orden_del_dia
            WHERE fecha_sesion >= CURRENT_DATE
              AND fuente = 'scraping_hcdn'
            ORDER BY fecha_sesion ASC
            LIMIT 100
        """))
        eventos: list[EventoAgenda] = []
        for row in r.all():
            od_id, titulo, fecha_sesion = row
            eventos.append(
                EventoAgenda(
                    uid=f"praxis-sesion-{od_id}@praxis-asesor.com",
                    summary=f"🏛️ {titulo or 'Sesión del Congreso'}",
                    fecha_inicio=fecha_sesion,
                    tipo=TipoEventoAgenda.SESION_CONGRESO,
                    descripcion=(
                        f"Sesión detectada por Praxis Asesor. "
                        f"Ver briefing en la app para el detalle del OD."
                    ),
                    ubicacion="Honorable Cámara de Diputados de la Nación",
                    categorias=["Sesión Congreso"],
                )
            )
        return eventos

    # ------------------------------------------------------------------
    # Fuente 3: vencimientos por caducidad
    # ------------------------------------------------------------------
    async def _eventos_caducidad(self, despacho_id: UUID) -> list[EventoAgenda]:
        """Recordatorios 30/7/1 días antes de la caducidad de proyectos
        seguidos por el despacho."""
        r = await self._session.execute(text("""
            SELECT e.id, e.numero, e.origen, e.anio, e.titulo, e.fecha_caducidad
            FROM expediente e
            JOIN seguimiento_expediente se ON se.expediente_id = e.id
            WHERE se.despacho_id = :d
              AND se.archivado = false
              AND e.fecha_caducidad IS NOT NULL
              AND e.fecha_caducidad >= CURRENT_DATE
        """), {"d": despacho_id})
        eventos: list[EventoAgenda] = []
        for row in r.all():
            exp_id, numero, origen, anio, titulo, fecha_cad = row
            etiqueta = f"{numero:04d}-{origen}-{anio}"
            for dias_antes in RECORDATORIOS_CADUCIDAD:
                fecha_reminder = fecha_cad - timedelta(days=dias_antes)
                if fecha_reminder < date.today():
                    continue
                eventos.append(
                    EventoAgenda(
                        uid=f"praxis-caducidad-{exp_id}-{dias_antes}@praxis-asesor.com",
                        summary=(
                            f"⏰ {etiqueta} vence en {dias_antes} día"
                            + ("s" if dias_antes != 1 else "")
                        ),
                        fecha_inicio=fecha_reminder,
                        tipo=TipoEventoAgenda.VENCIMIENTO_CADUCIDAD,
                        descripcion=(
                            f"{titulo[:200]}\n\n"
                            f"Caduca el {fecha_cad.strftime('%d/%m/%Y')} "
                            f"por inactividad (Ley 13.640)."
                        ),
                        categorias=["Caducidad", "Expediente"],
                    )
                )
        return eventos


def _proxima_ocurrencia(hoy: date, mes: int, dia: int) -> date:
    """Si MM-DD ya pasó este año, devuelve la del año siguiente."""
    candidato = date(hoy.year, mes, dia)
    if candidato < hoy:
        return date(hoy.year + 1, mes, dia)
    return candidato
