"""Scraper de votaciones nominales HCDN.

Submódulo dedicado porque el portal de votaciones
(`votaciones.hcdn.gob.ar`) es independiente del buscador de expedientes
(`www.diputados.gob.ar`). Aunque ambos son HCDN, los formatos y los
caminos de scraping no comparten código.

Ver `docs/spikes/26-votaciones-hcdn.md` para la validación del portal.
"""

from praxis.infrastructure.scrapers.hcdn.votaciones.parser import (
    parse_acta_votacion,
    parse_indice_votaciones,
)

__all__ = ["parse_acta_votacion", "parse_indice_votaciones"]
