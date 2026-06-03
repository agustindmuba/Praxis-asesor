"""`MedioScraper` — adaptador genérico para medios sin RSS/sitemap, y
para obtener el cuerpo del artículo (`obtener_texto_articulo`) que los
demás adapters delegan.

`listar_articulos_nuevos` con scraping de la home está pensado como
último recurso (ADR 0007 §"Prioridad RSS"). En v1 lo dejamos esqueleto
porque cada medio sin feed tiene su propia estructura HTML — agregamos
selector específico cuando aparezca un caso real.

`obtener_texto_articulo` extrae el cuerpo del HTML del artículo con
BeautifulSoup. Heurística genérica:
1. Buscar `<article>` (estándar HTML5 para contenido principal).
2. Si no hay, buscar el `<main>`.
3. Si no, todo el `<body>` filtrando scripts/estilos.

Tras extraer el texto **el caller lo descarta** (regla legal ADR 0006).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from praxis.application.ports import FuenteNoticias
from praxis.domain import Articulo, FuenteNoDisponible, FuenteNoticia

log = logging.getLogger(__name__)


DEFAULT_UA = (
    "PraxisAsesor/0.1 (+contacto@dominio.com; "
    "monitoreo legislativo Praxis Asesor)"
)
TIMEOUT_SECONDS = 30.0


class MedioScraper(FuenteNoticias):
    """Scraper HTML genérico.

    Para `listar_articulos_nuevos`, devuelve `[]` por default — cada
    medio sin RSS tiene su propia estructura. Cuando aparezca un medio
    a configurar manualmente, se subclasea y se overridea
    `_extraer_links_de_home`.

    Para `obtener_texto_articulo`, usa heurística genérica de
    `<article>` → `<main>` → `<body>`.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-AR,es;q=0.9",
            },
            follow_redirects=True,
        )

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        log.info(
            "MedioScraper.listar_articulos_nuevos sin implementación "
            "genérica para %s; devolviendo vacío. Override la subclase.",
            fuente.nombre,
        )
        return []

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        try:
            resp = await self._client.get(articulo.url)
        except httpx.RequestError as exc:
            raise FuenteNoDisponible(
                f"MedioScraper.get[{articulo.url}]", str(exc),
            ) from exc

        if resp.status_code != 200 or not resp.content:
            raise FuenteNoDisponible(
                f"MedioScraper.get[{articulo.url}]",
                f"GET → {resp.status_code}",
            )

        return _extraer_texto(resp.text)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Whitespace para colapsar runs.
_WS_RE = re.compile(r"\s+")


def _extraer_texto(html: str) -> str:
    """Devuelve el cuerpo del artículo como texto plano.

    Heurística:
    1. <article>.
    2. <main>.
    3. Todo <body> sin <script>, <style>, <nav>, <footer>, <header>, <aside>.
    """
    soup = BeautifulSoup(html, "lxml")

    # Eliminar elementos típicamente irrelevantes.
    for sel in ("script", "style", "nav", "footer", "header", "aside",
                "form", "iframe", "noscript"):
        for el in soup.find_all(sel):
            el.decompose()

    contenedor = soup.find("article") or soup.find("main") or soup.body
    if contenedor is None:
        return _normalizar_ws(soup.get_text(" "))
    return _normalizar_ws(contenedor.get_text(" "))


def _normalizar_ws(texto: str) -> str:
    return _WS_RE.sub(" ", texto).strip()
