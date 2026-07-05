"""Scraper de comisiones HCDN (feat-61.4).

3 endpoints:
- `listar_permanentes()` → 46 comisiones desde el índice oficial.
- `listar_integrantes(slug)` → tabla `tablaIntegrantes` por comisión.
- `listar_reuniones(slug)` → citaciones por fecha + PDF.

Sin retries elaborados (el portal HCDN responde bien). User-Agent
identificado, rate limit suave entre llamadas.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, time
from urllib.parse import urljoin

import httpx
import structlog
from lxml import html

from praxis.domain import (
    Camara,
    ComisionHcdn,
    IntegranteComision,
    ReunionComision,
    TipoComision,
)

log = structlog.get_logger(__name__)

HCDN_BASE = "https://www.hcdn.gob.ar"
URL_INDICE_PERMANENTES = f"{HCDN_BASE}/comisiones/permanentes/"
URL_INTEGRANTES_TPL = (
    f"{HCDN_BASE}/comisiones/permanentes/{{slug}}/integrantes.html"
)
URL_REUNIONES_TPL = (
    f"{HCDN_BASE}/comisiones/permanentes/{{slug}}/reuniones/index.html"
)
DEFAULT_USER_AGENT = "PraxisAsesor/0.1 (+contacto@dominio.com)"

# Pausa entre requests para ser amable con el portal. ~46 comisiones x 2
# llamadas = ~92 requests por corrida; con 250ms = ~25s total.
DEFAULT_DELAY_S = 0.25

_FECHA_RE = re.compile(r"REUNIONES DEL DIA (\d{2})/(\d{2})/(\d{4})")
# Captura "15:00" o "15:00hs" al inicio del título.
_HORA_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*h?s?\.?")
# Captura comisiones en MAYÚSCULAS tras el separador "·".
# Ej: "REUNIÓN CONJUNTA · ASUNTOS CONSTITUCIONALES LEGISLACION GENERAL ..."
_COMISIONES_INVITADAS_RE = re.compile(
    r"·\s*([A-ZÁÉÍÓÚÑ ,;\-]+?)(?=\s+[A-Z][a-z]|\s+COMISIONES?:|\s+INVITAD|\s+TEMAS|\s+MENSAJE|\s*$)"
)


class ComisionesHcdnScraper:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        delay_s: float = DEFAULT_DELAY_S,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._delay_s = delay_s

    async def __aenter__(self) -> ComisionesHcdnScraper:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=30.0,
            )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def listar_permanentes(self) -> list[ComisionHcdn]:
        """Lee el índice y devuelve las 46 comisiones permanentes
        (sin integrantes ni reuniones)."""
        assert self._client is not None
        log.info("scrape.comisiones.indice", url=URL_INDICE_PERMANENTES)
        resp = await self._client.get(URL_INDICE_PERMANENTES)
        resp.raise_for_status()
        return _parse_indice(_decode(resp))

    async def listar_integrantes(self, slug: str) -> list[IntegranteComision]:
        """Trae la tabla `tablaIntegrantes` de la comisión."""
        assert self._client is not None
        url = URL_INTEGRANTES_TPL.format(slug=slug)
        log.info("scrape.comisiones.integrantes", slug=slug, url=url)
        resp = await self._client.get(url)
        await asyncio.sleep(self._delay_s)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return _parse_integrantes(_decode(resp))

    async def listar_reuniones(
        self,
        slug: str,
        *,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[ReunionComision]:
        """Trae las reuniones citadas. Por default solo las futuras
        (`desde=hoy`) — el portal trae histórico de años y no nos sirve
        para la agenda. Pasar `desde`/`hasta` explícitos para más rango.
        """
        assert self._client is not None
        url = URL_REUNIONES_TPL.format(slug=slug)
        log.info("scrape.comisiones.reuniones", slug=slug, url=url)
        resp = await self._client.get(url)
        await asyncio.sleep(self._delay_s)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        todas = _parse_reuniones(_decode(resp))
        if desde is None and hasta is None:
            # Default agresivo: solo futuras. Para histórico, pasarlo
            # explícito en el caller.
            from datetime import date as _date
            desde = _date.today()
        if desde is not None:
            todas = [r for r in todas if r.fecha >= desde]
        if hasta is not None:
            todas = [r for r in todas if r.fecha <= hasta]
        return todas


# ---------------------------------------------------------------------------
# Parsers puros (testeables sin red)
# ---------------------------------------------------------------------------


def _parse_indice(html_text: str) -> list[ComisionHcdn]:
    """Extrae todas las `<a href='/comisiones/permanentes/{slug}'>NOMBRE</a>`
    del índice. Las 46 permanentes están en una tabla simple."""
    root = html.fromstring(html_text)
    enlaces = root.xpath(
        "//a[contains(@href, '/comisiones/permanentes/') "
        "and not(contains(@href, '/integrantes')) "
        "and not(contains(@href, '/reuniones'))]"
    )
    out: list[ComisionHcdn] = []
    vistos: set[str] = set()
    for a in enlaces:
        href = (a.get("href") or "").strip().rstrip("/")
        nombre = (a.text_content() or "").strip()
        if not href or not nombre:
            continue
        # /comisiones/permanentes/caconstitucionales → slug = caconstitucionales
        slug = href.rsplit("/", 1)[-1]
        if not slug or slug in vistos:
            continue
        if slug in {"permanentes", "comisiones"}:
            continue
        vistos.add(slug)
        out.append(
            ComisionHcdn(
                id=None,
                camara=Camara.HCDN,
                slug=slug,
                nombre=_normalizar_nombre(nombre),
                tipo=TipoComision.PERMANENTE,
                url_oficial=urljoin(HCDN_BASE, href + "/"),
            ),
        )
    return out


def _parse_integrantes(html_text: str) -> list[IntegranteComision]:
    """Parsea la tabla `tablaIntegrantes`.

    Columnas habituales: distrito | cargo | diputado | partido.
    El orden cambia entre comisiones, así que parseo por encabezado.
    """
    root = html.fromstring(html_text)
    tablas = root.xpath("//table[contains(@class, 'tablaIntegrantes')]")
    if not tablas:
        return []
    tabla = tablas[0]
    headers = [
        (th.text_content() or "").strip().lower()
        for th in tabla.xpath(".//th")
    ]
    idx_cargo = _idx_col(headers, ["cargo"])
    idx_diputado = _idx_col(headers, ["diputado", "nombre"])
    idx_partido = _idx_col(headers, ["bloque", "partido"])
    idx_distrito = _idx_col(headers, ["distrito"])

    out: list[IntegranteComision] = []
    for tr in tabla.xpath(".//tr"):
        celdas = [
            (td.text_content() or "").strip()
            for td in tr.xpath(".//td")
        ]
        if not celdas:
            continue
        if idx_cargo is None or idx_cargo >= len(celdas):
            continue
        cargo = celdas[idx_cargo].strip()
        nombre = celdas[idx_diputado].strip() if (
            idx_diputado is not None and idx_diputado < len(celdas)
        ) else ""
        if not cargo and not nombre:
            continue
        # Tabla "puenteada": cuando una fila tiene solo el cargo y la
        # siguiente trae el nombre. Para MVP: salteamos filas que no
        # tienen nombre (la imagen y los espacios del portal generan
        # ruido). El operador puede limpiar después.
        if not nombre:
            continue
        partido = celdas[idx_partido].strip() if (
            idx_partido is not None and idx_partido < len(celdas)
        ) else None
        distrito = celdas[idx_distrito].strip() if (
            idx_distrito is not None and idx_distrito < len(celdas)
        ) else None
        out.append(
            IntegranteComision(
                id=None,
                comision_id=_PLACEHOLDER_UUID,  # se setea al persistir
                nombre_diputado=nombre[:200],
                cargo=cargo[:40] or "VOCAL",
                partido=partido[:200] if partido else None,
                distrito=distrito[:80] if distrito else None,
            ),
        )
    return out


def _parse_reuniones(html_text: str) -> list[ReunionComision]:
    """Parsea las citaciones por fecha.

    El portal HCDN usa UNA sola `<table>` con múltiples `<thead>` adentro
    (uno por fecha). Las filas que vienen DESPUÉS de un `<thead>` pero
    ANTES del próximo pertenecen a esa fecha. Iteramos en orden de
    aparición y asignamos al último encabezado visto.
    """
    root = html.fromstring(html_text)
    out: list[ReunionComision] = []
    fecha_actual: date | None = None
    # XPath que une <thead> y <tr> en orden de aparición.
    for nodo in root.xpath("//thead | //tr"):
        if nodo.tag == "thead":
            txt = nodo.text_content() or ""
            match = _FECHA_RE.search(txt)
            if match:
                dd, mm, yyyy = match.groups()
                try:
                    fecha_actual = date(int(yyyy), int(mm), int(dd))
                except ValueError:
                    fecha_actual = None
            continue
        # Es un <tr>. Salteamos los que están dentro de un <thead>.
        if nodo.xpath("./ancestor::thead"):
            continue
        if fecha_actual is None:
            continue
        celdas = nodo.xpath(".//td")
        if not celdas:
            continue
        texto = " · ".join(
            _limpiar(c.text_content()) for c in celdas
        ).strip(" ·")
        if not texto:
            continue
        pdf = None
        links = nodo.xpath(".//a[contains(@href, 'archivo')]/@href")
        if links:
            pdf = str(links[0])

        hora, sala, descripcion, comisiones_inv, restante = _split_titulo(
            texto,
        )
        out.append(
            ReunionComision(
                id=None,
                comision_id=_PLACEHOLDER_UUID,
                fecha=fecha_actual,
                titulo=restante[:500],
                hora=hora,
                sala=sala,
                descripcion=descripcion,
                comisiones_invitadas=comisiones_inv,
                citacion_pdf_url=pdf,
            ),
        )
    return out


def _split_titulo(
    texto: str,
) -> tuple[time | None, str | None, str | None, list[str], str]:
    """Separa el texto crudo en (hora, sala, descripcion, comisiones, raw).

    El formato típico del portal HCDN:
        "15:00 Anexo \"C\" - 2° piso · ASUNTOS CONSTITUCIONALES Proyectos..."

    Estrategia:
    1. Extraer hora del inicio.
    2. Después de hora, hasta el separador "·": eso es la sala/ubicación.
    3. Después de "·": comisiones (MAYÚSCULAS) y luego descripción.
    """
    restante = texto.strip()
    hora: time | None = None
    sala: str | None = None
    descripcion: str | None = None
    comisiones_inv: list[str] = []

    # 1. Hora
    m = _HORA_RE.match(restante)
    if m:
        try:
            hora = time(int(m.group(1)), int(m.group(2)))
        except ValueError:
            hora = None
        restante = restante[m.end():].strip()

    # 2. Partir por el primer "·".
    partes = restante.split("·", 1)
    if len(partes) == 2:
        sala_raw = partes[0].strip(" -")
        if sala_raw:
            sala = sala_raw[:120]
        descripcion_raw = partes[1].strip()
    else:
        descripcion_raw = restante

    # 3. Extraer comisiones invitadas y dejar el resto como descripción.
    desc_limpia, comisiones_inv = _extraer_comisiones(descripcion_raw)
    if desc_limpia:
        descripcion = desc_limpia[:2000]

    return hora, sala, descripcion, comisiones_inv, restante


def _extraer_comisiones(texto: str) -> tuple[str, list[str]]:
    """Detecta el bloque MAYÚSCULAS al inicio del texto como comisiones
    invitadas, retorna la descripción "limpia" y la lista de comisiones.
    """
    palabras = texto.split()
    if not palabras:
        return texto, []

    # Tomamos palabras en MAYÚSCULAS al inicio (con tolerancia para
    # conectores como "Y", "DE", etc. también en mayúsculas).
    i = 0
    bloque: list[str] = []
    while i < len(palabras):
        w = palabras[i].strip(".,;:")
        # Caracteres especiales que aceptamos dentro del bloque MAYÚSCULAS
        sin_simbolos = w.replace("Ñ", "N").replace("Á", "A").replace(
            "É", "E",
        ).replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
        if (
            sin_simbolos.isupper()
            and len(sin_simbolos) > 1
            and sin_simbolos.isalpha()
        ):
            bloque.append(w)
            i += 1
        else:
            break

    if not bloque:
        return texto, []

    # Heurística: el bloque puede contener MÚLTIPLES comisiones separadas
    # por nada (ej "ASUNTOS CONSTITUCIONALES LEGISLACION GENERAL PRESUPUESTO
    # Y HACIENDA"). Por ahora persistimos el bloque completo como un único
    # string. Splitting fino queda para una versión LLM-asistida.
    nombre_bloque = " ".join(bloque)
    descripcion = " ".join(palabras[i:]).strip()
    return descripcion, [nombre_bloque]


def _limpiar(s: str | None) -> str:
    """Colapsa whitespace y quita espacios al borde."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _decode(resp: httpx.Response) -> str:
    """El portal HCDN sirve UTF-8 pero a veces declara latin-1 en el
    header. Forzamos UTF-8 para evitar los caracteres rotos (Nicol�s)."""
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return resp.text


def _idx_col(headers: list[str], opciones: list[str]) -> int | None:
    for i, h in enumerate(headers):
        for op in opciones:
            if op in h:
                return i
    return None


def _normalizar_nombre(s: str) -> str:
    # El portal viene en CAPS; pasar a Title Case manteniendo siglas
    # cortas en mayúscula sería ideal, pero para no romper la identidad
    # natural lo guardamos tal cual.
    return s.strip()[:300]


# Sentinel para diferenciar parsers puros (no conocen el UUID) del repo.
from uuid import UUID
_PLACEHOLDER_UUID = UUID("00000000-0000-0000-0000-000000000000")
