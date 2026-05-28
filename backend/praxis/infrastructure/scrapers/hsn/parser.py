"""Parser puro de HTML del portal HSN → entidades de dominio.

Sin I/O. Recibe HTML como string y devuelve un `Expediente`. Anclado a
selectores semánticos (atributo `summary=` de las 5 tablas), no a XPath
posicional — ver `docs/data-sources.md` §HSN y `docs/specs/02-ingesta-hsn.md`.

Punto de entrada: `parse_expediente_hsn(html, numero, tipo)`.

Helper expuesto para tests directos: `derive_tramite_from_stages(...)`,
que convierte los timestamps de etapas en una lista de `TramiteEvento`
con `fuente="derived:hsn-stages"`.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    Firmante,
    Giro,
    NumeroExpediente,
    TipoExpediente,
    TramiteEvento,
)

# Fuente registrada en cada TramiteEvento que generamos: el campo permite
# distinguir eventos derivados de los nativos (HCDN). Ver ADR 0002 §"TramiteEvento".
FUENTE_DERIVADO = "derived:hsn-stages"

# Formato de fechas en HSN: "DD-MM-YYYY". También aparece "SIN FECHA".
_DATE_FORMATS_HSN = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


# ---------------------------------------------------------------------------
# Helpers de texto / fecha
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Colapsa whitespace; HSN tiene muchos `\\n\\t` en las celdas."""
    return " ".join(text.split()).strip()


def _parse_date_hsn(raw: str) -> date | None:
    """Devuelve date o None. None para 'SIN FECHA', '', o formato inesperado."""
    s = _clean(raw)
    if not s or s.upper() in {"SIN FECHA", "-", "—", "N/A"}:
        return None
    for fmt in _DATE_FORMATS_HSN:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _table_data_rows(table: Tag) -> list[list[str]]:
    """Devuelve filas con celdas limpias (omite filas header-only)."""
    out: list[list[str]] = []
    for tr in table.find_all("tr"):
        if tr.find("th") and not tr.find("td"):
            continue
        cells = [_clean(td.get_text(" ")) for td in tr.find_all("td")]
        if any(cells):
            out.append(cells)
    return out


def _find_table(soup: BeautifulSoup, summary_pattern: str) -> Tag | None:
    """Busca la primera tabla cuyo `summary=` matche el patrón regex (case-insensitive)."""
    regex = re.compile(summary_pattern, re.IGNORECASE)
    tag = soup.find("table", summary=regex)
    return tag if isinstance(tag, Tag) else None


# ---------------------------------------------------------------------------
# Derivador de trámite
# ---------------------------------------------------------------------------


def derive_tramite_from_stages(
    *,
    fecha_mesa_entradas: date | None,
    fecha_dado_cuenta: date | None,
    fecha_dir_comisiones: date | None,
    fecha_dictamen_mesa: date | None,
    giros: list[Giro],
    numero_dae: str | None = None,
) -> list[TramiteEvento]:
    """Construye un event-log a partir de los timestamps de etapas de HSN.

    Reglas (ver `docs/specs/02-ingesta-hsn.md` §"Derivación"):
    - Cada fecha presente genera un `TramiteEvento` con texto descriptivo.
    - `numero_dae`, si está, se incluye como detalle del evento "Dado Cuenta".
    - Cada giro genera 1 o 2 eventos: ingreso (siempre) y egreso (si tiene fecha).
    - Los eventos se devuelven ordenados cronológicamente ascendente. Empates
      por fecha respetan el orden semántico (Mesa antes que Comisiones, etc.).
    - Todos con `fuente="derived:hsn-stages"` y `camara=HSN`.
    """
    eventos: list[TramiteEvento] = []

    # Eventos con orden semántico estable: damos un sort-key secundario.
    # Esto sostiene el orden razonable cuando dos eventos comparten fecha.
    raw: list[tuple[date | None, int, TramiteEvento]] = []

    if fecha_mesa_entradas:
        raw.append(
            (
                fecha_mesa_entradas,
                10,
                TramiteEvento(
                    fecha=fecha_mesa_entradas,
                    camara=Camara.HSN,
                    evento="INGRESO A MESA DE ENTRADAS",
                    detalle=None,
                    fuente=FUENTE_DERIVADO,
                ),
            )
        )

    if fecha_dado_cuenta:
        raw.append(
            (
                fecha_dado_cuenta,
                20,
                TramiteEvento(
                    fecha=fecha_dado_cuenta,
                    camara=Camara.HSN,
                    evento="DADO CUENTA EN SESION",
                    detalle=f"D.A.E. {numero_dae}" if numero_dae else None,
                    fuente=FUENTE_DERIVADO,
                ),
            )
        )

    if fecha_dir_comisiones:
        raw.append(
            (
                fecha_dir_comisiones,
                30,
                TramiteEvento(
                    fecha=fecha_dir_comisiones,
                    camara=Camara.HSN,
                    evento="INGRESO A DIRECCION GENERAL DE COMISIONES",
                    detalle=None,
                    fuente=FUENTE_DERIVADO,
                ),
            )
        )

    for giro in giros:
        if giro.fecha_ingreso:
            raw.append(
                (
                    giro.fecha_ingreso,
                    40,
                    TramiteEvento(
                        fecha=giro.fecha_ingreso,
                        camara=Camara.HSN,
                        evento="GIRO A COMISION",
                        detalle=giro.comision,
                        fuente=FUENTE_DERIVADO,
                    ),
                )
            )
        if giro.fecha_egreso:
            raw.append(
                (
                    giro.fecha_egreso,
                    50,
                    TramiteEvento(
                        fecha=giro.fecha_egreso,
                        camara=Camara.HSN,
                        evento="EGRESO DE COMISION",
                        detalle=giro.comision,
                        fuente=FUENTE_DERIVADO,
                    ),
                )
            )

    if fecha_dictamen_mesa:
        raw.append(
            (
                fecha_dictamen_mesa,
                60,
                TramiteEvento(
                    fecha=fecha_dictamen_mesa,
                    camara=Camara.HSN,
                    evento="INGRESO DEL DICTAMEN A LA MESA",
                    detalle=None,
                    fuente=FUENTE_DERIVADO,
                ),
            )
        )

    # Sort: primero por fecha (ascendente), luego por orden semántico.
    raw.sort(key=lambda triple: (triple[0] or date.max, triple[1]))
    eventos = [t[2] for t in raw]
    return eventos


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------


def parse_expediente_hsn(
    html: str,
    numero: NumeroExpediente,
    tipo: TipoExpediente,
) -> Expediente:
    """Parsea el HTML de `/parlamentario/comisiones/verExp/...` y construye Expediente.

    Args:
        html: HTML completo de la página.
        numero: Identificador del expediente (la cámara debe ser HSN).
        tipo: Tipo del expediente (HSN lo expone vía URL, no en el HTML).

    Returns:
        Expediente con todos los campos extraíbles, incluyendo trámite derivado.

    Raises:
        ValueError: si el HTML no parece una ficha válida de HSN.
    """
    soup = BeautifulSoup(html, "lxml")

    # Sanity: el HTML debe tener al menos la tabla cabecera.
    cabecera = _find_table(soup, r"N.mero de Expediente")
    if cabecera is None:
        raise ValueError("El HTML no parece una ficha de expediente HSN válida")

    # 1. Cabecera: Nº / Origen / Tipo / Extracto.
    extracto: str | None = None
    rows = _table_data_rows(cabecera)
    if rows:
        first = rows[0]
        if len(first) >= 4:
            extracto = first[3] or None

    titulo = extracto or f"Expediente {numero}"

    # 2. Autores: tabla con summary "Listado de Autores".
    firmantes = _extract_firmantes(soup)

    # 3. Mesa de Entradas: fechas + DAE.
    mesa_entradas, dado_cuenta, numero_dae = _extract_mesa(soup)

    # 4. Dir. Comisiones: fechas.
    fecha_dir_comisiones, fecha_dictamen_mesa = _extract_dir_comisiones(soup)

    # 5. Giros.
    giros = _extract_giros(soup)

    # 6. PDF.
    texto_url = _extract_pdf_url(soup)

    # 7. Trámite derivado.
    tramite = derive_tramite_from_stages(
        fecha_mesa_entradas=mesa_entradas,
        fecha_dado_cuenta=dado_cuenta,
        fecha_dir_comisiones=fecha_dir_comisiones,
        fecha_dictamen_mesa=fecha_dictamen_mesa,
        giros=giros,
        numero_dae=numero_dae,
    )

    return Expediente(
        numero=numero,
        tipo=tipo,
        titulo=titulo,
        sumario=None,  # HSN no expone un "sumario largo" separado del extracto.
        fecha_ingreso=mesa_entradas,
        estado=EstadoExpediente.DESCONOCIDO,
        firmantes=firmantes,
        giros=giros,
        tramite=tramite,
        texto_url=texto_url,
    )


# ---------------------------------------------------------------------------
# Extractores por sección
# ---------------------------------------------------------------------------


def _extract_firmantes(soup: BeautifulSoup) -> list[Firmante]:
    """Autores: tabla `summary="Listado de Autores"`.

    En expedientes CD-origen (revisión desde Diputados) puede estar vacía
    porque los autores viven en HCDN — comportamiento documentado en
    `docs/data-sources.md` §HSN.
    """
    table = _find_table(soup, r"Autores")
    if table is None:
        return []
    firmantes: list[Firmante] = []
    orden = 0
    for row in _table_data_rows(table):
        for cell in row:
            if not cell:
                continue
            orden += 1
            firmantes.append(Firmante(nombre=cell, distrito=None, bloque=None, orden=orden))
    return firmantes


def _extract_mesa(soup: BeautifulSoup) -> tuple[date | None, date | None, str | None]:
    """Devuelve (fecha_mesa, fecha_dado_cuenta, numero_dae)."""
    table = _find_table(soup, r"Mesa de Entradas")
    if table is None:
        return None, None, None
    rows = _table_data_rows(table)
    if not rows:
        return None, None, None
    row = rows[0]
    fecha_mesa = _parse_date_hsn(row[0]) if len(row) >= 1 else None
    fecha_dado_cuenta = _parse_date_hsn(row[1]) if len(row) >= 2 else None
    # La celda DAE viene mezclada con "Tipo: NORMAL" — tomamos el primer token.
    numero_dae: str | None = None
    if len(row) >= 3 and row[2]:
        numero_dae = row[2].split()[0]
    return fecha_mesa, fecha_dado_cuenta, numero_dae


def _extract_dir_comisiones(soup: BeautifulSoup) -> tuple[date | None, date | None]:
    """Devuelve (fecha_dir_comisiones, fecha_dictamen_mesa)."""
    table = _find_table(soup, r"Direcci.n Comisiones")
    if table is None:
        return None, None
    rows = _table_data_rows(table)
    if not rows:
        return None, None
    row = rows[0]
    fecha_dir = _parse_date_hsn(row[0]) if len(row) >= 1 else None
    fecha_dict = _parse_date_hsn(row[1]) if len(row) >= 2 else None
    return fecha_dir, fecha_dict


def _extract_giros(soup: BeautifulSoup) -> list[Giro]:
    """Giros: tabla con `summary="Giros del Expediente a Comisiones"`.

    Cada celda comisión viene como "DE SALUD ORDEN DE GIRO: 1" — separamos
    el nombre del orden con regex.
    """
    table = _find_table(soup, r"Giros del Expediente")
    if table is None:
        return []
    giros: list[Giro] = []
    for row in _table_data_rows(table):
        if not row or not row[0]:
            continue
        comision_raw = row[0]
        m = re.match(r"^(.+?)\s+ORDEN DE GIRO:\s*(\d+)\s*$", comision_raw, re.IGNORECASE)
        if m:
            comision = _clean(m.group(1))
            orden: int | None = int(m.group(2))
        else:
            comision = comision_raw
            orden = None
        fecha_ingreso = _parse_date_hsn(row[1]) if len(row) >= 2 else None
        fecha_egreso = _parse_date_hsn(row[2]) if len(row) >= 3 else None
        giros.append(
            Giro(
                comision=comision,
                fecha_ingreso=fecha_ingreso,
                fecha_egreso=fecha_egreso,
                orden=orden,
            )
        )
    return giros


def _extract_pdf_url(soup: BeautifulSoup) -> str | None:
    """Link al PDF dentro de `<div id="textoOriginal">`.

    Patrón conocido: `/parlamentario/parlamentaria/<docId>/downloadPdf`.
    """
    div = soup.find("div", id="textoOriginal")
    if not isinstance(div, Tag):
        return None
    a = div.find("a", href=True)
    if not isinstance(a, Tag):
        return None
    href_raw = a["href"]
    href = href_raw if isinstance(href_raw, str) else " ".join(href_raw)
    if "downloadpdf" not in href.lower():
        return None
    return href if href.startswith("http") else f"https://www.senado.gob.ar{href}"
