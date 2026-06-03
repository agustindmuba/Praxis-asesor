"""`RssFeedAdapter` — implementa `FuenteNoticias` para feeds RSS/Atom.

Usa `feedparser` (paquete maduro, tolera feeds malformados).

Política:
- Title obligatorio. Sin title → saltamos entry.
- URL obligatoria. Sin link → saltamos.
- `published_parsed` opcional (algunos feeds no lo traen).
- Filtramos por `desde` después del parseo (feedparser no permite filtrar
  pre-parse).

Limitación del RSS: muchos medios truncan el cuerpo o solo dan la
bajada. Para obtener cuerpo completo, hay que bajar la URL canónica
(eso lo hace `MedioScraper.obtener_texto_articulo`).

Para mantener el adapter focused, **RssFeedAdapter NO baja cuerpos**.
Devuelve `Articulo` con `bajada_propia=None` y delega `obtener_texto_articulo`
en otro componente (típicamente `MedioScraper` vía
`FuenteNoticiasMultiAdapter`).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import feedparser  # type: ignore[import-untyped]
import httpx

from praxis.application.ports import FuenteNoticias
from praxis.domain import Articulo, FuenteNoDisponible, FuenteNoticia

log = logging.getLogger(__name__)


DEFAULT_UA = (
    "PraxisAsesor/0.1 (+contacto@dominio.com; "
    "monitoreo legislativo Praxis Asesor)"
)

TIMEOUT_SECONDS = 30.0


class RssFeedAdapter(FuenteNoticias):
    """Adaptador RSS/Atom.

    Stateless: cada llamada abre cliente httpx y lo cierra. Si se quiere
    reutilizar conexiones, pasar un `client` propio (útil cuando el
    caller llama esto en loop).
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
                "Accept": "application/rss+xml, application/atom+xml, "
                "application/xml;q=0.9, text/xml;q=0.8",
            },
            follow_redirects=True,
        )

    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime,
    ) -> list[Articulo]:
        if not fuente.feed_url:
            log.warning(
                "RssFeedAdapter llamado con FuenteNoticia sin feed_url: %s",
                fuente.nombre,
            )
            return []
        if fuente.id is None:
            raise ValueError(
                "RssFeedAdapter exige fuente.id persistido para articulo.fuente_id"
            )

        log.debug("Bajando feed %s", fuente.feed_url)
        try:
            resp = await self._client.get(fuente.feed_url)
        except httpx.RequestError as exc:
            raise FuenteNoDisponible(
                f"RssFeedAdapter[{fuente.nombre}]", str(exc),
            ) from exc

        if resp.status_code != 200 or not resp.content:
            raise FuenteNoDisponible(
                f"RssFeedAdapter[{fuente.nombre}]",
                f"GET {fuente.feed_url} → {resp.status_code}",
            )

        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            log.warning(
                "Feed %s tiene errores y no devolvió entries: %s",
                fuente.feed_url, parsed.bozo_exception,
            )
            return []

        articulos: list[Articulo] = []
        for entry in parsed.entries:
            articulo = _entry_a_articulo(entry, fuente.id)
            if articulo is None:
                continue
            # Filtrar por desde.
            if (
                articulo.publicado_en is not None
                and articulo.publicado_en < desde
            ):
                continue
            articulos.append(articulo)
        return articulos

    async def obtener_texto_articulo(self, articulo: Articulo) -> str:
        """RSS feeds raramente traen cuerpo completo. Delegamos al
        scraper de cuerpo (MedioScraper.obtener_texto_articulo).

        Si querés un adapter dedicado RSS-only que devuelva el summary
        del feed como cuerpo (truncado), se puede agregar un override
        por config; v1 prefiere uniformidad con scraping del HTML
        canónico de la URL.
        """
        raise NotImplementedError(
            "RssFeedAdapter no descarga cuerpos. Usar MedioScraper o "
            "FuenteNoticiasMultiAdapter."
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_a_articulo(entry: Any, fuente_id: UUID) -> Articulo | None:
    titulo = (entry.get("title") or "").strip()
    url = (entry.get("link") or "").strip()
    if not titulo or not url:
        return None

    publicado_en = _parse_published(entry)
    return Articulo(
        id=None,
        fuente_id=fuente_id,
        url=url,
        titulo=titulo,
        bajada_propia=None,
        publicado_en=publicado_en,
        capturado_en=datetime.now(UTC),
    )


def _parse_published(entry: Any) -> datetime | None:
    """feedparser convierte fechas a struct_time en `published_parsed` o
    `updated_parsed`. Las pasamos a datetime UTC.

    Si nada existe, devolvemos None (el filtro `desde` será permisivo).
    """
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st is None:
            continue
        try:
            year, month, day, hour, minute, second = st[:6]
            return datetime(
                year, month, day, hour, minute, second, tzinfo=UTC,
            )
        except (ValueError, TypeError):
            continue
    return None
