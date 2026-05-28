"""Inferencia automática de `EstadoExpediente` y caducidad desde el trámite.

Funciones puras sin I/O. Ver `docs/specs/07-inferencia-estado.md` para la
heurística aprobada y sus limitaciones conocidas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from praxis.domain.expediente import Expediente, TramiteEvento
from praxis.domain.value_objects import Camara, EstadoExpediente

# Regex compilados al import (reusables).
_ARCHIVADO_RE = re.compile(r"\bARCHIV", re.IGNORECASE)
_CADUCO_RE = re.compile(r"\bCADUC", re.IGNORECASE)
_SANCION_RE = re.compile(r"\bSANCION", re.IGNORECASE)
_DICTAMEN_RE = re.compile(r"\bDICTAMEN", re.IGNORECASE)
_GIRO_RE = re.compile(r"\bGIRO\b|EN COMISI", re.IGNORECASE)
_INGRESO_RE = re.compile(r"INGRES", re.IGNORECASE)
_PRORROGA_RE = re.compile(r"\b(prorroga|prorrogad)\w*\b", re.IGNORECASE)

# Aproximación de "2 años parlamentarios" de la Ley 13.640.
# Limitación documentada en spec §"Limitaciones conocidas".
_DOS_ANIOS = timedelta(days=730)


@dataclass(frozen=True, slots=True)
class InferenciaResult:
    """Resultado de `inferir_estado_y_caducidad`.

    Agrupa los 4 campos derivados que se aplican a un `Expediente`.
    Frozen para que sea seguro pasar entre capas.
    """

    estado: EstadoExpediente
    fecha_caducidad: date | None
    fecha_caducidad_original: date | None
    prorrogado: bool


def _has_match(
    tramite: list[TramiteEvento],
    pattern: re.Pattern[str],
    *,
    camara: Camara | None = None,
) -> bool:
    """¿Algún evento del trámite (opcionalmente filtrado por cámara) matchea
    el patrón sobre `evento + " " + detalle`?"""
    for ev in tramite:
        if camara is not None and ev.camara != camara:
            continue
        haystack = ev.evento
        if ev.detalle:
            haystack += " " + ev.detalle
        if pattern.search(haystack):
            return True
    return False


def inferir_estado(
    *,
    tramite: list[TramiteEvento],
    fecha_caducidad: date | None,
    hoy: date,
) -> EstadoExpediente:
    """Devuelve el `EstadoExpediente` inferido según la heurística del spec
    §"Estado". Primer match gana; default `DESCONOCIDO`.
    """
    # 1. Archivado.
    if _has_match(tramite, _ARCHIVADO_RE):
        return EstadoExpediente.ARCHIVADO

    # 2. Caduco: evento explícito o fecha de caducidad vencida.
    if _has_match(tramite, _CADUCO_RE):
        return EstadoExpediente.CADUCO
    if fecha_caducidad is not None and fecha_caducidad < hoy:
        return EstadoExpediente.CADUCO

    # 3/4/5. Sanción / media sanción según cámaras.
    sancion_hcdn = _has_match(tramite, _SANCION_RE, camara=Camara.HCDN)
    sancion_hsn = _has_match(tramite, _SANCION_RE, camara=Camara.HSN)
    if sancion_hcdn and sancion_hsn:
        return EstadoExpediente.SANCIONADO
    if sancion_hcdn:
        return EstadoExpediente.MEDIA_SANCION_HCDN
    if sancion_hsn:
        return EstadoExpediente.MEDIA_SANCION_HSN

    # 6. Dictamen.
    if _has_match(tramite, _DICTAMEN_RE):
        return EstadoExpediente.CON_DICTAMEN

    # 7. En comisión.
    if _has_match(tramite, _GIRO_RE):
        return EstadoExpediente.EN_COMISION

    # 8. Ingresado.
    if _has_match(tramite, _INGRESO_RE):
        return EstadoExpediente.INGRESADO

    return EstadoExpediente.DESCONOCIDO


def inferir_caducidad(
    fecha_ingreso: date | None,
    tramite: list[TramiteEvento],
) -> tuple[date | None, date | None, bool]:
    """Devuelve `(fecha_caducidad_original, fecha_caducidad, prorrogado)`.

    Si `fecha_ingreso` es None, los tres valores son None / False.

    Ver spec §"Caducidad" para la regla.
    """
    if fecha_ingreso is None:
        return None, None, False

    prorrogado = False
    for ev in tramite:
        haystack = ev.evento
        if ev.detalle:
            haystack += " " + ev.detalle
        if _PRORROGA_RE.search(haystack):
            prorrogado = True
            break

    fecha_caducidad_original = fecha_ingreso + _DOS_ANIOS
    fecha_caducidad = (
        fecha_caducidad_original + _DOS_ANIOS if prorrogado else fecha_caducidad_original
    )
    return fecha_caducidad_original, fecha_caducidad, prorrogado


def inferir_estado_y_caducidad(
    expediente: Expediente,
    *,
    hoy: date | None = None,
) -> InferenciaResult:
    """Aplica `inferir_caducidad` + `inferir_estado` y devuelve el agregado.

    `hoy` se inyecta para tests; default `date.today()`.
    """
    h = hoy if hoy is not None else date.today()
    cad_original, cad, prorrogado = inferir_caducidad(expediente.fecha_ingreso, expediente.tramite)
    estado = inferir_estado(
        tramite=expediente.tramite,
        fecha_caducidad=cad,
        hoy=h,
    )
    return InferenciaResult(
        estado=estado,
        fecha_caducidad=cad,
        fecha_caducidad_original=cad_original,
        prorrogado=prorrogado,
    )
