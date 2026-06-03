"""`FuenteNoticiasMultiAdapter` — despacha por `fuente.modo_acceso`.

Es lo que el caller (use case de polling, feat-40.5) usa. Internamente:
- RSS / sitemap: usa `RssFeedAdapter` o `SitemapAdapter` para listar
  artículos nuevos.
- Scraping: usa `MedioScraper`.
- `obtener_texto_articulo`: SIEMPRE usa `MedioScraper` (los feeds raras
  veces traen cuerpo completo, ADR 0007 §"RSS truncado").

Reutiliza un único `httpx.AsyncClient` interno entre los 3 adapters
para amortizar conexiones cuando se polla en loop.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from praxis.application.ports import FuenteNoticias
from praxis.domain import Articulo, FuenteNoticia, ModoAccesoFuente
from praxis.infrastructure.noticias.rss_feed_adapter import (
    DEFAULT_UA,
    TIMEOUT_SECONDS,
    RssFeedAdapter,
)
from praxis.infrastructure.noticias.scraper import MedioScraper
from praxis.infrastructure.noticias.sitemap_adapter import SitemapAdapter


class FuenteNoticiasMultiAdapter(FuenteNoticias):
    """Despachador. Stateless por afuera; mantiene un client httpx
    compartido entre sus adapters internos."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self._owns_client = client is None
        # Cliente compartido. Cada adapter usa headers default de su
        # propio Accept, pero como pasamos el client al constructor, el
        # client no aplica los headers por adapter (httpx no permite
        # mergear). Si se necesitan Accepts distintos por adapter, hay
        # que pasar `headers=` por request — para v1 los tres aceptan
        # `*/*` implícito y funciona.
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={
                "User-Agent": user_agent,
                "Accept": "*/*",
            },
            follow_redirects=True,
        )
        self._rss = RssFeedAdapter(client=self._client)
        self._sitemap = SitemapAdapter(client=self._client)
        self._scraper = MedioScraper(client=self._client)

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        if fuente.modo_acceso == ModoAccesoFuente.RSS:
            return await self._rss.listar_articulos_nuevos(
                fuente, desde=desde,
            )
        if fuente.modo_acceso == ModoAccesoFuente.SITEMAP:
            return await self._sitemap.listar_articulos_nuevos(
                fuente, desde=desde,
            )
        return await self._scraper.listar_articulos_nuevos(
            fuente, desde=desde,
        )

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        # Siempre vía scraper del HTML canónico.
        return await self._scraper.obtener_texto_articulo(articulo)

    async def aclose(self) -> None:
        # Cerrar el client una sola vez (los adapters internos no son
        # owners — todos comparten el client).
        if self._owns_client:
            await self._client.aclose()
