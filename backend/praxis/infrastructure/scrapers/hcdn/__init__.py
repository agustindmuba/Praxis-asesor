"""Adaptador HCDN: scraper del portal de la Cámara de Diputados.

Implementa el puerto `praxis.application.ports.FuenteExpedientes`.
"""

from praxis.infrastructure.scrapers.hcdn.scraper import HcdnScraper

__all__ = ["HcdnScraper"]
