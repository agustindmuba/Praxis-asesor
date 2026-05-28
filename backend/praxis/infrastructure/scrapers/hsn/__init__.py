"""Adaptador HSN: scraper del portal del Senado de la Nación.

Implementa el puerto `praxis.application.ports.FuenteExpedientes`.
"""

from praxis.infrastructure.scrapers.hsn.scraper import HsnScraper

__all__ = ["HsnScraper"]
