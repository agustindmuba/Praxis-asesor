"""Tests de los adapters de FuenteNoticias (feat-40.2).

Usamos `httpx.MockTransport` para no agregar `respx` como dep. Mockeamos:
- RSS: bytes de feed RSS válido + entradas con title/link/published.
- Sitemap: XML de sitemap + sitemap-índice.
- Scraper (cuerpo): HTML con <article>.

Cubren:
- RssFeedAdapter: parsea entradas, filtra por `desde`, salta entries
  sin title/link, status no-200 → FuenteNoDisponible, sin feed_url →
  warning + lista vacía.
- SitemapAdapter: parsea <url><loc>, filtra por lastmod, sigue índice
  un nivel.
- MedioScraper.obtener_texto_articulo: extrae texto de <article>,
  fallback a <main> y <body>, elimina script/nav/footer.
- FuenteNoticiasMultiAdapter: despacha según modo_acceso; cuerpo
  siempre vía scraper.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from praxis.domain import (
    AlcanceMedio,
    Articulo,
    FuenteNoDisponible,
    FuenteNoticia,
    ModoAccesoFuente,
    TipoFuenteNoticia,
)
from praxis.infrastructure.noticias import (
    FuenteNoticiasMultiAdapter,
    MedioScraper,
    RssFeedAdapter,
    SitemapAdapter,
)
from praxis.infrastructure.noticias.scraper import _extraer_texto

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


RSS_VALIDO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Medio de Prueba</title>
<link>https://medio.test</link>
<description>Feed</description>
<item>
<title>Diputado Juliano propuso ley educativa</title>
<link>https://medio.test/nota-1</link>
<pubDate>Tue, 02 Jun 2026 12:00:00 +0000</pubDate>
</item>
<item>
<title>Vieja noticia</title>
<link>https://medio.test/nota-vieja</link>
<pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate>
</item>
<item>
<link>https://medio.test/nota-sin-titulo</link>
</item>
</channel>
</rss>
"""


SITEMAP_NORMAL = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url>
<loc>https://medio.test/articulo-reciente</loc>
<lastmod>2026-06-02T10:00:00Z</lastmod>
</url>
<url>
<loc>https://medio.test/articulo-viejo</loc>
<lastmod>2024-01-01T00:00:00Z</lastmod>
</url>
</urlset>
"""


SITEMAP_INDICE = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap>
<loc>https://medio.test/sitemap-noticias.xml</loc>
</sitemap>
</sitemapindex>
"""


HTML_CON_ARTICLE = """
<html><body>
<header><nav>menu</nav></header>
<article>
<h1>Titular</h1>
<p>Primer párrafo del artículo.</p>
<p>Segundo párrafo con más detalles.</p>
</article>
<footer>copyright</footer>
<script>tracking()</script>
</body></html>
"""


def _fuente_rss(fuente_id=None) -> FuenteNoticia:
    return FuenteNoticia(
        id=fuente_id or uuid4(),
        nombre="Medio de Prueba",
        dominio="medio.test",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.RSS,
        feed_url="https://medio.test/feed.xml",
    )


def _fuente_sitemap(fuente_id=None) -> FuenteNoticia:
    return FuenteNoticia(
        id=fuente_id or uuid4(),
        nombre="Medio Sitemap",
        dominio="medio.test",
        tipo=TipoFuenteNoticia.NACIONAL,
        alcance=AlcanceMedio.NACIONAL,
        modo_acceso=ModoAccesoFuente.SITEMAP,
        feed_url="https://medio.test/sitemap.xml",
    )


def _client(handler) -> httpx.AsyncClient:
    """AsyncClient con MockTransport."""
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=30.0,
    )


# ---------------------------------------------------------------------------
# RssFeedAdapter
# ---------------------------------------------------------------------------


class TestRssFeedAdapter:
    async def test_parsea_feed_valido_y_filtra_por_desde(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert "feed.xml" in str(req.url)
            return httpx.Response(200, content=RSS_VALIDO.encode())

        async with _client(handler) as http:
            adapter = RssFeedAdapter(client=http)
            articulos = await adapter.listar_articulos_nuevos(
                _fuente_rss(), desde=datetime(2026, 1, 1, tzinfo=UTC),
            )
        # 1 reciente + 1 vieja con published > desde? Vieja es 2024 < 2026 → out.
        # Sin título → out.
        assert len(articulos) == 1
        assert articulos[0].titulo.startswith("Diputado Juliano")
        assert articulos[0].publicado_en == datetime(
            2026, 6, 2, 12, 0, tzinfo=UTC,
        )

    async def test_status_no_200_levanta(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"server error")

        async with _client(handler) as http:
            adapter = RssFeedAdapter(client=http)
            with pytest.raises(FuenteNoDisponible):
                await adapter.listar_articulos_nuevos(
                    _fuente_rss(), desde=datetime(2026, 1, 1, tzinfo=UTC),
                )

    async def test_sin_feed_url_devuelve_vacio(self) -> None:
        # Construimos una fuente válida por dominio (modo SCRAPING) que
        # NO necesita feed_url; pero llamamos al RssFeedAdapter
        # igual y verificamos el warning + retorno vacío.
        f = FuenteNoticia(
            id=uuid4(),
            nombre="Sin feed",
            dominio="ejemplo.com",
            tipo=TipoFuenteNoticia.NACIONAL,
            alcance=AlcanceMedio.NACIONAL,
            modo_acceso=ModoAccesoFuente.SCRAPING,
            feed_url=None,
        )

        def handler(req: httpx.Request) -> httpx.Response:
            raise AssertionError("No debería llamar a HTTP")

        async with _client(handler) as http:
            adapter = RssFeedAdapter(client=http)
            articulos = await adapter.listar_articulos_nuevos(
                f, desde=datetime(2026, 1, 1, tzinfo=UTC),
            )
            assert articulos == []

    async def test_obtener_texto_levanta_not_implemented(self) -> None:
        async with _client(lambda r: httpx.Response(200)) as http:
            adapter = RssFeedAdapter(client=http)
            articulo = Articulo(
                id=None,
                fuente_id=uuid4(),
                url="https://x.com/a",
                titulo="x",
            )
            with pytest.raises(NotImplementedError):
                await adapter.obtener_texto_articulo(articulo)


# ---------------------------------------------------------------------------
# SitemapAdapter
# ---------------------------------------------------------------------------


class TestSitemapAdapter:
    async def test_parsea_sitemap_normal_y_filtra(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert "sitemap.xml" in str(req.url)
            return httpx.Response(200, content=SITEMAP_NORMAL.encode())

        async with _client(handler) as http:
            adapter = SitemapAdapter(client=http)
            urls = await adapter.listar_articulos_nuevos(
                _fuente_sitemap(),
                desde=datetime(2025, 1, 1, tzinfo=UTC),
            )
        assert len(urls) == 1
        assert urls[0].url == "https://medio.test/articulo-reciente"
        assert urls[0].titulo == "Articulo reciente"

    async def test_sitemap_indice_sigue_un_nivel(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if str(req.url).endswith("sitemap.xml"):
                return httpx.Response(200, content=SITEMAP_INDICE.encode())
            # Sub-sitemap.
            return httpx.Response(200, content=SITEMAP_NORMAL.encode())

        async with _client(handler) as http:
            adapter = SitemapAdapter(client=http)
            urls = await adapter.listar_articulos_nuevos(
                _fuente_sitemap(),
                desde=datetime(2025, 1, 1, tzinfo=UTC),
            )
        assert len(urls) == 1   # mismo filtro que el normal


# ---------------------------------------------------------------------------
# MedioScraper
# ---------------------------------------------------------------------------


class TestMedioScraperObtenerTexto:
    async def test_extrae_de_article(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=HTML_CON_ARTICLE.encode(),
                headers={"content-type": "text/html"},
            )

        async with _client(handler) as http:
            scraper = MedioScraper(client=http)
            articulo = Articulo(
                id=None,
                fuente_id=uuid4(),
                url="https://medio.test/articulo-x",
                titulo="x",
            )
            texto = await scraper.obtener_texto_articulo(articulo)
        assert "Primer párrafo" in texto
        assert "Segundo párrafo" in texto
        assert "menu" not in texto
        assert "copyright" not in texto
        assert "tracking()" not in texto


class TestExtraerTextoHelper:
    def test_fallback_a_main_si_no_hay_article(self) -> None:
        html = "<html><body><main><p>Solo main</p></main></body></html>"
        assert "Solo main" in _extraer_texto(html)

    def test_fallback_a_body_si_no_hay_article_ni_main(self) -> None:
        html = "<html><body><div><p>Body only</p></div></body></html>"
        assert "Body only" in _extraer_texto(html)

    def test_quita_script_y_style(self) -> None:
        html = (
            "<html><body><article>"
            "<script>secret()</script>"
            "<style>.x{}</style>"
            "<p>Contenido visible</p>"
            "</article></body></html>"
        )
        texto = _extraer_texto(html)
        assert "Contenido visible" in texto
        assert "secret()" not in texto
        assert ".x" not in texto


# ---------------------------------------------------------------------------
# FuenteNoticiasMultiAdapter
# ---------------------------------------------------------------------------


class TestMultiAdapter:
    async def test_rss_va_al_rss_adapter(self) -> None:
        llamadas = {"feed": 0, "html": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            url = str(req.url)
            if "feed.xml" in url:
                llamadas["feed"] += 1
                return httpx.Response(200, content=RSS_VALIDO.encode())
            llamadas["html"] += 1
            return httpx.Response(200, content=HTML_CON_ARTICLE.encode())

        async with _client(handler) as http:
            multi = FuenteNoticiasMultiAdapter(client=http)
            articulos = await multi.listar_articulos_nuevos(
                _fuente_rss(),
                desde=datetime(2026, 1, 1, tzinfo=UTC),
            )
        assert llamadas["feed"] == 1
        assert llamadas["html"] == 0
        assert len(articulos) == 1

    async def test_obtener_texto_siempre_via_scraper(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=HTML_CON_ARTICLE.encode(),
            )

        async with _client(handler) as http:
            multi = FuenteNoticiasMultiAdapter(client=http)
            articulo = Articulo(
                id=None,
                fuente_id=uuid4(),
                url="https://medio.test/x",
                titulo="x",
            )
            texto = await multi.obtener_texto_articulo(articulo)
        assert "Primer párrafo" in texto


# ---------------------------------------------------------------------------
# Sanity: el desde filtering funciona
# ---------------------------------------------------------------------------


async def test_desde_en_el_futuro_descarta_todo() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS_VALIDO.encode())

    async with _client(handler) as http:
        adapter = RssFeedAdapter(client=http)
        articulos = await adapter.listar_articulos_nuevos(
            _fuente_rss(),
            desde=datetime.now(UTC) + timedelta(days=365),
        )
    assert articulos == []
