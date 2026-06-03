"""`SitemapAdapter` — parsea `sitemap.xml` para medios sin RSS.

Implementación v1 simple: lee el sitemap, extrae `<url><loc>...` + `<lastmod>`.
Si el sitemap es índice (sitemap de sitemaps), seguimos un nivel.

NO baja cuerpos. Para eso usar `MedioScraper`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from lxml import etree  # type: ignore[import-untyped]

from praxis.application.ports import FuenteNoticias
from praxis.domain import Articulo, FuenteNoDisponible, FuenteNoticia

log = logging.getLogger(__name__)


DEFAULT_UA = (
    "PraxisAsesor/0.1 (+contacto@dominio.com; "
    "monitoreo legislativo Praxis Asesor)"
)

TIMEOUT_SECONDS = 30.0

_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SitemapAdapter(FuenteNoticias):
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": user_agent, "Accept": "application/xml"},
            follow_redirects=True,
        )

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        if not fuente.feed_url:
            log.warning(
                "SitemapAdapter sin feed_url para fuente %s", fuente.nombre,
            )
            return []
        if fuente.id is None:
            raise ValueError(
                "SitemapAdapter exige fuente.id persistido",
            )

        urls = await self._descargar_urls(fuente.feed_url, profundidad=1)
        articulos: list[Articulo] = []
        for url, lastmod in urls:
            if lastmod is not None and lastmod < desde:
                continue
            # Sitemap solo da URL — no tenemos título. Lo dejamos como
            # URL (el caller puede mejorarlo bajando el HTML).
            articulos.append(
                Articulo(
                    id=None,
                    fuente_id=fuente.id,
                    url=url,
                    titulo=_extraer_slug_como_titulo(url),
                    bajada_propia=None,
                    publicado_en=lastmod,
                    capturado_en=datetime.now(UTC),
                )
            )
        return articulos

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        raise NotImplementedError(
            "SitemapAdapter no descarga cuerpos. Usar MedioScraper.",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _descargar_urls(
        self,
        url_sitemap: str,
        *,
        profundidad: int,
    ) -> list[tuple[str, datetime | None]]:
        """Devuelve list[(loc, lastmod)] del sitemap. Si es índice y
        `profundidad > 0`, sigue un nivel."""
        try:
            resp = await self._client.get(url_sitemap)
        except httpx.RequestError as exc:
            raise FuenteNoDisponible(
                f"SitemapAdapter[{url_sitemap}]", str(exc),
            ) from exc

        if resp.status_code != 200 or not resp.content:
            raise FuenteNoDisponible(
                f"SitemapAdapter[{url_sitemap}]",
                f"GET → {resp.status_code}",
            )

        try:
            root = etree.fromstring(resp.content)
        except etree.XMLSyntaxError as exc:
            log.warning("Sitemap %s no parsea: %s", url_sitemap, exc)
            return []

        # Detectar si es un sitemap-índice (contiene <sitemap><loc>).
        sitemaps = root.findall("s:sitemap", _NS)
        if sitemaps:
            if profundidad <= 0:
                return []
            resultado: list[tuple[str, datetime | None]] = []
            for sm in sitemaps:
                loc_el = sm.find("s:loc", _NS)
                if loc_el is None or not loc_el.text:
                    continue
                hijo = await self._descargar_urls(
                    loc_el.text.strip(), profundidad=profundidad - 1,
                )
                resultado.extend(hijo)
            return resultado

        # Sitemap normal: <url><loc>+<lastmod>.
        urls: list[tuple[str, datetime | None]] = []
        for url_el in root.findall("s:url", _NS):
            loc_el = url_el.find("s:loc", _NS)
            if loc_el is None or not loc_el.text:
                continue
            lastmod_el = url_el.find("s:lastmod", _NS)
            lastmod = _parse_lastmod(lastmod_el.text if lastmod_el is not None else None)
            urls.append((loc_el.text.strip(), lastmod))
        return urls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # ISO 8601 con timezone.
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _extraer_slug_como_titulo(url: str) -> str:
    """Fallback: usar el último segmento del path como título.

    El title real lo obtiene el caller bajando el HTML.
    """
    if "://" in url:
        url = url.split("://", 1)[1]
    parts = [p for p in url.split("/") if p]
    if not parts:
        return url
    slug = parts[-1].split(".")[0]
    # Reemplazar guiones por espacios + capitalizar primera letra.
    legible = slug.replace("-", " ").replace("_", " ")
    return legible[:1].upper() + legible[1:] if legible else url


# Suppress unused import warning for UUID (used in type hint of Articulo).
_ = UUID
