"""Adaptadores de `FuenteNoticias` (feat-40.2, spec 16).

Tres implementaciones según el `modo_acceso` de cada `FuenteNoticia`:

- `RssFeedAdapter`: consume RSS/Atom con `feedparser`. Preferido cuando
  el medio expone feed estándar.
- `SitemapAdapter`: parsea `sitemap.xml` con `lxml`. Para medios con
  sitemap pero sin RSS.
- `MedioScraper`: scraping HTML genérico con `httpx + BeautifulSoup`.
  Último recurso (ADR 0007 §"Prioridad RSS").

Despachador `FuenteNoticiasMultiAdapter` que elige el adapter por
`fuente.modo_acceso`. Es lo que el caller (use case de polling) usa.

Política de scraping (ADR 0007 aplicada):
- UA `PraxisAsesor/0.1 (+contacto@dominio.com)`.
- Rate limit 1 req/seg por dominio (responsabilidad del caller; el
  adapter es stateless).
- Timeout 30s.
- BackoffExponencial para 429/503 (caller).

Restricción legal materializada:
- `Articulo.bajada_propia` se genera en feat-40.4 (LLM), NO acá. El
  adapter solo provee título + url + fecha + cuerpo (cuerpo NO se
  persiste; el caller lo descarta tras procesar).
"""

from praxis.infrastructure.noticias.multi_adapter import (
    FuenteNoticiasMultiAdapter,
)
from praxis.infrastructure.noticias.rss_feed_adapter import RssFeedAdapter
from praxis.infrastructure.noticias.scraper import MedioScraper
from praxis.infrastructure.noticias.sitemap_adapter import SitemapAdapter

__all__ = [
    "FuenteNoticiasMultiAdapter",
    "MedioScraper",
    "RssFeedAdapter",
    "SitemapAdapter",
]
