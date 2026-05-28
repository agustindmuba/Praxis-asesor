"""Adaptadores de catálogo del padrón legislativo.

Implementaciones del puerto `praxis.application.ports.CatalogoLegisladores`.
"""

from praxis.infrastructure.padron.csv_repository import CsvPadronRepository

__all__ = ["CsvPadronRepository"]
