"""Parser puro de HTML del portal de votaciones HCDN.

Sin I/O. Recibe HTML como string, devuelve entidades de dominio.

Dos parsers:

- `parse_indice_votaciones`: la tabla del listado (home o /votaciones/search).
  Devuelve metadata mínima por acta (id, fecha, título, resultado).
  Se usa en el scraper para iterar.

- `parse_acta_votacion`: detalle completo de una votación
  (encabezado + tabla de votos individuales por legislador).

Estructura DOM validada con fixtures en `backend/spikes/votaciones/`
y documentada en `docs/spikes/26-votaciones-hcdn.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

from praxis.domain import (
    Camara,
    TipoVotacion,
    Votacion,
    VotoLegislador,
    VotoTipo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_HORA_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-?\s*(\d{2}:\d{2})\s*$")
_OD_RE = re.compile(r"O\.D\.\s*(\d+)", re.IGNORECASE)
_SESION_RE = re.compile(
    r"Per[ií]odo\s+\d+\s*-\s*Reuni[oó]n\s+\d+\s*-\s*Acta\s+\d+",
    re.IGNORECASE,
)
_ACTA_ID_URL_RE = re.compile(r"/(?:pdf/acta|votacion)/(\d+)", re.IGNORECASE)
_LEGISLADOR_ID_URL_RE = re.compile(r"/assets/diputados/(\w+)", re.IGNORECASE)

# Mapeo de strings del portal a VotoTipo. El portal usa MAYÚSCULAS sin tildes
# en abstención.
_VOTO_MAP: dict[str, VotoTipo] = {
    "AFIRMATIVO": VotoTipo.AFIRMATIVO,
    "NEGATIVO": VotoTipo.NEGATIVO,
    "ABSTENCION": VotoTipo.ABSTENCION,
    "ABSTENCIÓN": VotoTipo.ABSTENCION,
    "SIN VOTAR": VotoTipo.SIN_VOTAR,
    "AUSENTE": VotoTipo.AUSENTE,
    # El presidente de la sesión no vota — el portal lo marca como
    # PRESIDENTE en la columna de voto. Conceptualmente equivale a
    # 'sin votar' (figura en el padrón pero su voto no se contabiliza).
    # El conteo agregado del encabezado lo suma a "SIN VOTAR".
    "PRESIDENTE": VotoTipo.SIN_VOTAR,
}


def _clean(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split()).strip()


def _parse_fecha(s: str) -> date | None:
    """Acepta dd/mm/yyyy."""
    s = _clean(s)
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def _inferir_tipo(asunto: str) -> TipoVotacion:
    """Heurística: clasifica el asunto en uno de los buckets de TipoVotacion.

    El portal solo dice "Votación Nominal" como categoría macro. El bucket
    útil para análisis se infiere del texto del asunto.
    """
    a = asunto.upper()
    if "MOCION" in a or "MOCIÓN" in a or "APARTAMIENTO" in a:
        return TipoVotacion.MOCION
    if "CAPÍTULO" in a or "CAPITULO" in a or "VOT. EN PART" in a or "EN PARTICULAR" in a:
        return TipoVotacion.PARTICULAR
    if "VOT. EN GRAL" in a or "EN GENERAL" in a:
        return TipoVotacion.GENERAL
    return TipoVotacion.OTRO


# ---------------------------------------------------------------------------
# Índice (listado de votaciones)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndiceItem:
    """Metadata mínima de una votación, extraída del listado."""

    acta_id: int
    fecha: date | None
    hora: str | None
    titulo: str
    tipo_portal: str          # 'Votación Nominal' etc — texto crudo del portal
    resultado_agregado: str   # 'AFIRMATIVO' / 'NEGATIVO' / 'EMPATE' etc — texto crudo
    pdf_url: str | None
    votacion_url: str | None


def parse_indice_votaciones(html: str) -> list[IndiceItem]:
    """Parsea el listado de votaciones (home o /votaciones/search).

    Devuelve los items en el orden que vinieron (más reciente primero).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None or not isinstance(table, Tag):
        return []

    items: list[IndiceItem] = []
    rows = table.find_all("tr")
    if not rows:
        return items
    # Primera fila es header (FECHA, TÍTULO, TIPO, RESULTADO, '').
    for tr in rows[1:]:
        if not isinstance(tr, Tag):
            continue
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        fecha_raw = _clean(cells[0].get_text(" "))
        # Fecha viene como dd/mm/yyyy + hora pegada, ej "20/05/202622:07"
        fecha_str = fecha_raw[:10] if len(fecha_raw) >= 10 else fecha_raw
        hora_raw = fecha_raw[10:].strip() if len(fecha_raw) > 10 else ""
        # El listado concatena fecha+hora sin separador: "20/05/202622:07".
        # Si la "hora" no tiene ":" la insertamos.
        if hora_raw and ":" not in hora_raw and len(hora_raw) >= 4:
            hora_str: str | None = f"{hora_raw[:2]}:{hora_raw[2:4]}"
        elif hora_raw:
            hora_str = hora_raw
        else:
            hora_str = None

        titulo = _clean(cells[1].get_text(" "))
        tipo_portal = _clean(cells[2].get_text(" "))
        resultado = _clean(cells[3].get_text(" "))

        pdf_url: str | None = None
        votacion_url: str | None = None
        acta_id: int | None = None
        for a in tr.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a.get("href", "")
            if isinstance(href, list):
                href = href[0] if href else ""
            if not isinstance(href, str):
                continue
            if "/pdf/acta/" in href:
                pdf_url = href
                m = _ACTA_ID_URL_RE.search(href)
                if m:
                    acta_id = int(m.group(1))
            elif "/votacion/" in href:
                votacion_url = href
                if acta_id is None:
                    m = _ACTA_ID_URL_RE.search(href)
                    if m:
                        acta_id = int(m.group(1))

        if acta_id is None:
            # Sin id no podemos referenciar la votación. Saltamos.
            continue

        items.append(
            IndiceItem(
                acta_id=acta_id,
                fecha=_parse_fecha(fecha_str),
                hora=hora_str,
                titulo=titulo,
                tipo_portal=tipo_portal,
                resultado_agregado=resultado,
                pdf_url=pdf_url,
                votacion_url=votacion_url,
            )
        )

    return items


# ---------------------------------------------------------------------------
# Detalle de una votación
# ---------------------------------------------------------------------------


def parse_acta_votacion(
    html: str,
    *,
    acta_id: int | None = None,
    fuente_url: str | None = None,
) -> tuple[Votacion, list[VotoLegislador]]:
    """Parsea el HTML de detalle de una votación.

    Devuelve `(Votacion, list[VotoLegislador])`. Si `acta_id` se pasa
    explícito, sobreescribe el que se haya podido detectar del HTML.

    Levanta `ValueError` si el HTML no contiene los campos críticos
    (título, fecha, totales).
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Encabezado --------------------------------------------------------

    # El primer <h4> tiene "TÍTULO  dd/mm/yyyy - HH:MM"
    h4s = [_clean(h.get_text(" ")) for h in soup.find_all("h4")]
    if not h4s:
        raise ValueError("HTML sin <h4>; no es una página de votación válida")

    titulo_raw = h4s[0]
    m = _DATE_HORA_RE.search(titulo_raw)
    if not m:
        raise ValueError(f"No pude extraer fecha del título: {titulo_raw!r}")
    fecha_str = m.group(1)
    # m.group(2) tiene la hora; no la persistimos en Votacion (la fecha alcanza
    # para todos los joineos. Si en el futuro se necesita, agregar campo `hora`).
    fecha = _parse_fecha(fecha_str)
    if fecha is None:
        raise ValueError(f"Fecha inválida en título: {fecha_str!r}")
    asunto = titulo_raw[: m.start()].strip()
    asunto = re.sub(r"\s+", " ", asunto).strip()

    # OD
    titulo_od_m = _OD_RE.search(asunto)
    titulo_od = f"O.D. {titulo_od_m.group(1)}" if titulo_od_m else None

    # Presidida por: segundo h4 usualmente
    presidida_por: str | None = None
    for txt in h4s[:5]:
        if txt.lower().startswith("presidida por"):
            presidida_por = txt[len("Presidida por"):].strip(" :,")
            break

    # Sesión: buscar texto "Período N - Reunión N - Acta N" en todo el body
    body_text = soup.get_text(" ", strip=True)
    sesion_m = _SESION_RE.search(body_text)
    if sesion_m:
        sesion = sesion_m.group(0)
    elif acta_id is not None:
        sesion = f"Acta {acta_id}"
    else:
        sesion = "Sesión sin identificar"

    # Resultado agregado y conteos -----------------------------------------
    h3s = [_clean(h.get_text(" ")) for h in soup.find_all("h3") if _clean(h.get_text(" "))]
    resultado_agregado = h3s[0] if h3s else ""
    aprobada = resultado_agregado.upper().strip() == "AFIRMATIVO"

    # Buscar pares (número h3, label h4) recorriendo el DOM en orden.
    conteos = _extraer_conteos(soup)

    # Tipo de votación inferido del asunto
    tipo = _inferir_tipo(asunto)

    votacion = Votacion(
        id=None,
        camara=Camara.HCDN,
        fecha=fecha,
        sesion=sesion,
        asunto=asunto or "(sin asunto)",
        tipo=tipo,
        resultado_afirmativos=conteos.get("AFIRMATIVOS", 0),
        resultado_negativos=conteos.get("NEGATIVOS", 0),
        resultado_abstenciones=conteos.get("ABSTENCIONES", 0),
        resultado_sin_votar=conteos.get("SIN VOTAR", 0),
        resultado_ausentes=conteos.get("AUSENTES", 0),
        aprobada=aprobada,
        presidida_por=presidida_por,
        titulo_od=titulo_od,
        acta_id_hcdn=acta_id,
        acta_pdf_url=f"/pdf/acta/{acta_id}" if acta_id else None,
        fuente_url=fuente_url,
    )

    # --- Votos individuales ------------------------------------------------

    votos: list[VotoLegislador] = []
    for tr in soup.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        # Filtrar header
        if any(c.find("th") for c in cells):
            continue
        nombre = _clean(cells[1].get_text(" "))
        bloque = _clean(cells[2].get_text(" ")) or None
        provincia = _clean(cells[3].get_text(" ")) or None
        voto_raw = _clean(cells[4].get_text(" ")).upper()
        que_dijo = _clean(cells[5].get_text(" ")) if len(cells) > 5 else ""
        if not nombre:
            continue
        voto = _VOTO_MAP.get(voto_raw)
        if voto is None:
            # Tolerancia: si el portal cambia un label, no fallamos toda
            # la votación — saltamos al legislador.
            continue
        # Sacar legislador_hcdn_id del asset link en la fila
        legislador_hcdn_id: str | None = None
        for a in tr.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href_attr = a.get("href", "")
            if isinstance(href_attr, list):
                href_attr = href_attr[0] if href_attr else ""
            if not isinstance(href_attr, str):
                continue
            m = _LEGISLADOR_ID_URL_RE.search(href_attr)
            if m:
                legislador_hcdn_id = m.group(1)
                break

        votos.append(
            VotoLegislador(
                legislador_nombre=nombre,
                voto=voto,
                bloque=bloque,
                distrito=provincia,
                que_dijo=que_dijo or None,
                legislador_hcdn_id=legislador_hcdn_id,
            )
        )

    return votacion, votos


def _extraer_conteos(soup: BeautifulSoup) -> dict[str, int]:
    """Encuentra los pares (número, label) en el panel de totales.

    El portal estructura los conteos como `<h3>137</h3><h4>AFIRMATIVOS</h4>`
    repetidos para cada categoría. Recorremos h3+h4 en orden de aparición
    en el documento y emparejamos.
    """
    conteos: dict[str, int] = {}
    candidatos: list[Tag] = [
        el
        for el in soup.find_all(["h3", "h4"])
        if isinstance(el, Tag)
    ]

    labels_validos = {"AFIRMATIVOS", "NEGATIVOS", "ABSTENCIONES", "SIN VOTAR", "AUSENTES"}

    # Recorrer en orden buscando: h3 (número), h4 (label en labels_validos)
    i = 0
    while i < len(candidatos) - 1:
        a = candidatos[i]
        b = candidatos[i + 1]
        if a.name == "h3" and b.name == "h4":
            txt_num = _clean(a.get_text(" "))
            txt_label = _clean(b.get_text(" ")).upper()
            if txt_label in labels_validos and txt_num.isdigit():
                conteos[txt_label] = int(txt_num)
        i += 1

    return conteos


# ---------------------------------------------------------------------------
# Utilidades públicas (re-export)
# ---------------------------------------------------------------------------


def parse_indice_y_meta(html: str) -> dict[str, Any]:
    """Convenience: devuelve dict con conteo + items para logging."""
    items = parse_indice_votaciones(html)
    return {"total": len(items), "items": items}
