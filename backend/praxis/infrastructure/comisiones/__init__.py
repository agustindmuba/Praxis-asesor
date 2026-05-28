"""Adaptadores de catálogo de comisiones.

Implementa `praxis.application.ports.CatalogoComisiones`.
"""

from praxis.infrastructure.comisiones.local_repository import LocalCatalogoComisiones

__all__ = ["LocalCatalogoComisiones"]
