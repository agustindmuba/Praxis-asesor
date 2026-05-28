"""Funciones puras sobre histórico de trámite (`list[TramiteEvento]`).

Operaciones cámara-agnósticas usadas por casos de uso y futuros repositorios:
merge sin duplicar, filtros, validaciones de consistencia. Sin I/O. Sin estado.

Ver `docs/specs/04-historico-tramites.md` para contexto y decisiones.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from praxis.domain.expediente import TramiteEvento
from praxis.domain.value_objects import Camara

# La clave de igualdad para deduplicar. NO incluye `fuente` para que un mismo
# evento extraído por dos fuentes diferentes (HCDN nativo + HSN derivado) se
# detecte como el mismo. Sí incluye `detalle` porque dos eventos con mismo
# título pero diferente detalle son eventos distintos (ej. dos giros a
# comisiones diferentes, mismo día).
_EventoKey = tuple[date | None, str, str | None, Camara]


def _key(ev: TramiteEvento) -> _EventoKey:
    return (ev.fecha, ev.evento, ev.detalle, ev.camara)


def _sort_chronological(eventos: Iterable[TramiteEvento]) -> list[TramiteEvento]:
    """Eventos ordenados por fecha ascendente; sin fecha al final
    en orden de inserción (estable)."""
    con_fecha = [e for e in eventos if e.fecha is not None]
    sin_fecha = [e for e in eventos if e.fecha is None]
    con_fecha.sort(key=lambda e: e.fecha or date.max)
    return con_fecha + sin_fecha


def merge_tramite(
    existente: list[TramiteEvento],
    nuevo: list[TramiteEvento],
) -> list[TramiteEvento]:
    """Une dos listas de TramiteEvento sin duplicar.

    Dos eventos son duplicados si tienen la misma `(fecha, evento, detalle, camara)`.
    Si un mismo evento aparece en ambas listas, se preserva la versión de
    `existente` (criterio: la fuente más temprana gana).

    El resultado se devuelve ordenado cronológicamente ascendente; eventos sin
    fecha quedan al final en orden de inserción.

    No muta los inputs.
    """
    vistos: set[_EventoKey] = set()
    out: list[TramiteEvento] = []
    for ev in existente:
        k = _key(ev)
        if k not in vistos:
            vistos.add(k)
            out.append(ev)
    for ev in nuevo:
        k = _key(ev)
        if k not in vistos:
            vistos.add(k)
            out.append(ev)
    return _sort_chronological(out)


def filter_by_camara(
    tramite: list[TramiteEvento],
    camara: Camara,
) -> list[TramiteEvento]:
    """Subset de eventos cuya `camara` matchea. Preserva orden de input."""
    return [e for e in tramite if e.camara == camara]


def filter_by_rango(
    tramite: list[TramiteEvento],
    desde: date | None = None,
    hasta: date | None = None,
) -> list[TramiteEvento]:
    """Subset de eventos en el rango `[desde, hasta]` (inclusive).

    Reglas:
    - `desde=None`: sin límite inferior.
    - `hasta=None`: sin límite superior.
    - Eventos sin fecha se incluyen SOLO si tanto `desde` como `hasta` son None.

    Preserva orden de input.
    """
    sin_filtros = desde is None and hasta is None
    out: list[TramiteEvento] = []
    for ev in tramite:
        if ev.fecha is None:
            if sin_filtros:
                out.append(ev)
            continue
        if desde is not None and ev.fecha < desde:
            continue
        if hasta is not None and ev.fecha > hasta:
            continue
        out.append(ev)
    return out


def eventos_recientes(
    tramite: list[TramiteEvento],
    n: int,
) -> list[TramiteEvento]:
    """Los `n` eventos más recientes, ordenados cronológicamente ascendente.

    Eventos sin fecha quedan excluidos del top-N (no se puede saber qué tan
    recientes son). Si la lista tiene menos de N eventos con fecha, devuelve
    todos los que tenga.

    Si `n <= 0`, devuelve lista vacía.
    """
    if n <= 0:
        return []
    con_fecha = [e for e in tramite if e.fecha is not None]
    con_fecha.sort(key=lambda e: e.fecha or date.max)
    return con_fecha[-n:]


def validar_consistencia(tramite: list[TramiteEvento]) -> list[str]:
    """Detecta problemas estructurales en un histórico de trámite.

    Devuelve lista de mensajes descriptivos. Lista vacía = OK.

    Checks:
    - Duplicados exactos (misma clave `(fecha, evento, detalle, camara)`).
    - Eventos con `fecha` futura (sospechoso, probablemente parsing roto).
    - Eventos con `evento` vacío (en teoría no debería pasar — la dataclass
      ya valida — pero defensivo).
    """
    problemas: list[str] = []

    # Duplicados.
    vistos: dict[_EventoKey, int] = {}
    for ev in tramite:
        k = _key(ev)
        vistos[k] = vistos.get(k, 0) + 1
    for k, count in vistos.items():
        if count > 1:
            problemas.append(f"Duplicado: clave={k} aparece {count} veces")

    # Fechas futuras.
    hoy = date.today()
    for ev in tramite:
        if ev.fecha is not None and ev.fecha > hoy:
            problemas.append(f"Fecha futura: evento '{ev.evento}' con fecha {ev.fecha.isoformat()}")

    # Evento vacío (defensivo: la dataclass lanza, pero por las dudas).
    for ev in tramite:
        if not ev.evento.strip():
            problemas.append("Evento con texto vacío detectado")

    return problemas
