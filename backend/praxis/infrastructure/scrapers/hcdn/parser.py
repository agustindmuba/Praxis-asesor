"""Parser puro de HTML del portal HCDN → entidades de dominio.

Sin I/O. Recibe HTML como string y devuelve un `Expediente`. Esto permite
testearlo con HTML fixturizado (rápido, sin red).

Documentación de los selectores y gotchas: `docs/data-sources.md` §HCDN.
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup, Tag

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    Firmante,
    Giro,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
    TramiteEvento,
)

# Formatos de fecha que aparecen en HCDN. Probamos en orden.
_DATE_FORMATS_HCDN = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d")


def _clean(text: str | None) -> str:
    """Colapsa whitespace; devuelve '' para None."""
    if text is None:
        return ""
    return " ".join(text.split()).strip()


def _parse_date_hcdn(raw: str) -> date | None:
    """Intenta parsear una fecha en formatos típicos de HCDN. None si no puede."""
    s = _clean(raw)
    if not s or s.upper() in {"SIN FECHA", "-", "—", "N/A"}:
        return None
    from datetime import datetime

    for fmt in _DATE_FORMATS_HCDN:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _camara_from_cell(text: str) -> Camara:
    """Traduce 'Diputados' / 'Senado' a Camara enum."""
    t = text.lower()
    if "senado" in t or "hsn" in t:
        return Camara.HSN
    return Camara.HCDN


def _find_table_with_headers(soup: BeautifulSoup, required: list[str]) -> Tag | None:
    """Devuelve la primera tabla cuyos `<th>` contengan todos los substrings
    de `required` (case-insensitive), o None."""
    required_lower = [r.lower() for r in required]
    for table in soup.find_all("table"):
        headers = [_clean(th.get_text()).lower() for th in table.find_all("th")]
        if not headers:
            continue
        if all(any(req in h for h in headers) for req in required_lower):
            assert isinstance(table, Tag)
            return table
    return None


def _table_data_rows(table: Tag) -> list[list[str]]:
    """Filas de datos (no headers) ya limpias."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        # Skip rows that are header-only.
        if tr.find("th") and not tr.find("td"):
            continue
        cells = [_clean(td.get_text(" ")) for td in tr.find_all("td")]
        if any(cells):
            rows.append(cells)
    return rows


def parse_resultado_hcdn(html: str, numero: NumeroExpediente) -> Expediente:
    """Parsea la HTML de `/proyectos/resultado.html` y construye un Expediente.

    Args:
        html: HTML completo devuelto por la búsqueda.
        numero: El número de expediente que se buscó (lo usamos como key,
            ya que el HTML no siempre lo expone en un campo idéntico).

    Returns:
        Expediente con todos los campos que se hayan podido extraer.

    Raises:
        ValueError: si el HTML claramente no es una ficha válida.
    """
    soup = BeautifulSoup(html, "lxml")

    # Sanity: el HTML debe tener al menos la tabla de firmantes o un dp-texto.
    has_dp = soup.find("div", class_="dp-texto") is not None
    has_firmante_table = (
        _find_table_with_headers(soup, ["firmante", "distrito", "bloque"]) is not None
    )
    if not (has_dp or has_firmante_table):
        raise ValueError("El HTML no parece una ficha de expediente HCDN válida")

    # 1. Extracto (sumario corto) y sumario (largo, en div oculto del modal).
    extracto = None
    dp = soup.find("div", class_="dp-texto")
    if isinstance(dp, Tag):
        extracto = _clean(dp.get_text(" "))

    sumario = None
    sumario_div = soup.find("div", id=re.compile(r"^sumario\d+"))
    if isinstance(sumario_div, Tag):
        sumario = _clean(sumario_div.get_text(" "))

    titulo = extracto or sumario or f"Expediente {numero}"

    # 2. Tipo: heurística que combina origen + texto del sumario.
    #    Ver Amendment 1 del ADR 0002 §6 para la regla completa.
    tipo = _inferir_tipo(extracto or "", sumario or "", numero.origen)

    # 3. Firmantes.
    firmantes = _extract_firmantes(soup)

    # 4. Giros.
    giros = _extract_giros(soup)

    # 5. Trámite.
    tramite = _extract_tramite(soup)

    # 6. PDF (link a www4.hcdn.gob.ar/.../<exp>.pdf).
    texto_url = _extract_pdf_url(soup, numero)

    return Expediente(
        numero=numero,
        tipo=tipo,
        titulo=titulo,
        sumario=sumario,
        firmantes=firmantes,
        giros=giros,
        tramite=tramite,
        texto_url=texto_url,
        estado=EstadoExpediente.DESCONOCIDO,
    )


# Regex para detectar la palabra "mensaje" como palabra completa.
# Matchea "mensaje", "Mensaje", "MENSAJE", "mensaje n°", "mensaje nº", etc.
_MENSAJE_PE_RE = re.compile(r"\bmensaje\b", re.IGNORECASE)


def _inferir_tipo(extracto: str, sumario: str, origen: OrigenExpediente) -> TipoExpediente:
    """Inferencia de TipoExpediente desde el texto del expediente.

    Heurística definida en Amendment 1 del ADR 0002 §6:

    Si origen ∈ {EJECUTIVO, JEFATURA_GABINETE}:
      1. Si el texto contiene la palabra completa "mensaje" → MENSAJE_PE.
      2. Si contiene "proyecto de ley" o "proyecto de" → PROYECTO_LEY.
      3. Else (ambiguo) → MENSAJE_PE (default conservador, porque los
         mensajes son la mayoría en este origen).

    Resto de orígenes: marcadores explícitos en los primeros 80 caracteres
    (declaraci → DECLARACION, resoluci → RESOLUCION, comunicaci → COMUNICACION),
    default PROYECTO_LEY (cubre el caso más frecuente).
    """
    texto = (extracto + " " + sumario).lower()

    if origen in (OrigenExpediente.EJECUTIVO, OrigenExpediente.JEFATURA_GABINETE):
        if _MENSAJE_PE_RE.search(texto):
            return TipoExpediente.MENSAJE_PE
        if "proyecto de ley" in texto or "proyecto de" in texto:
            return TipoExpediente.PROYECTO_LEY
        return TipoExpediente.MENSAJE_PE  # default conservador para PE/JGM

    # Resto de orígenes: marcadores al inicio del sumario.
    if "declaraci" in texto[:80]:
        return TipoExpediente.PROYECTO_DECLARACION
    if "resoluci" in texto[:80]:
        return TipoExpediente.PROYECTO_RESOLUCION
    if "comunicaci" in texto[:80]:
        return TipoExpediente.PROYECTO_COMUNICACION
    return TipoExpediente.PROYECTO_LEY


def _extract_firmantes(soup: BeautifulSoup) -> list[Firmante]:
    table = _find_table_with_headers(soup, ["firmante", "distrito", "bloque"])
    if table is None:
        return []
    firmantes: list[Firmante] = []
    for orden, cells in enumerate(_table_data_rows(table), start=1):
        if len(cells) < 1 or not cells[0]:
            continue
        nombre = cells[0]
        distrito = cells[1] if len(cells) > 1 and cells[1] else None
        bloque = cells[2] if len(cells) > 2 and cells[2] else None
        firmantes.append(Firmante(nombre=nombre, distrito=distrito, bloque=bloque, orden=orden))
    return firmantes


def _extract_giros(soup: BeautifulSoup) -> list[Giro]:
    """Giros HCDN: tabla con header COMISIÓN. Puede traer una sola columna o más."""
    # Buscamos una tabla cuya cabecera incluya COMISIÓN pero NO los headers de trámite
    # (cámara/movimiento/resultado).
    for table in soup.find_all("table"):
        headers = [_clean(th.get_text()).lower() for th in table.find_all("th")]
        if not headers:
            continue
        if any("comisi" in h for h in headers) and not any(
            "movimi" in h or "resultado" in h for h in headers
        ):
            giros: list[Giro] = []
            for cells in _table_data_rows(table):
                if cells and cells[0]:
                    giros.append(Giro(comision=cells[0]))
            return giros
    return []


def _extract_tramite(soup: BeautifulSoup) -> list[TramiteEvento]:
    """Trámite HCDN: tabla con CÁMARA / MOVIMIENTO / FECHA / RESULTADO."""
    table = _find_table_with_headers(soup, ["mara", "movimi", "fecha", "resultado"])
    if table is None:
        return []
    eventos: list[TramiteEvento] = []
    for cells in _table_data_rows(table):
        if len(cells) < 4:
            continue
        camara_text, movimiento, fecha_text, resultado = cells[0], cells[1], cells[2], cells[3]
        if not movimiento:
            continue
        eventos.append(
            TramiteEvento(
                fecha=_parse_date_hcdn(fecha_text),
                camara=_camara_from_cell(camara_text),
                evento=movimiento,
                detalle=resultado or None,
                fuente="scraper:hcdn",
            )
        )
    return eventos


def _extract_pdf_url(soup: BeautifulSoup, numero: NumeroExpediente) -> str | None:
    """Busca el link al PDF del expediente original.

    Patrón conocido (validado en spike):
        https://www4.hcdn.gob.ar/.../TP<YYYY>/<NNNN-X-YYYY>.pdf
    """
    numero_str = numero.format_hcdn().lower()
    for a in soup.find_all("a", href=True):
        # bs4 4.14+ tipa attrs como `str | AttributeValueList`; href siempre es str.
        href_raw = a["href"]
        href = href_raw if isinstance(href_raw, str) else " ".join(href_raw)
        if href.lower().endswith(".pdf") and numero_str in href.lower():
            return href if href.startswith("http") else f"https://www.diputados.gob.ar{href}"
    return None
