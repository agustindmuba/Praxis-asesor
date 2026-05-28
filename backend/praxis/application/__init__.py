"""Capa Application — casos de uso y puertos.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.
"""

from praxis.application.ports import CatalogoComisiones, FuenteExpedientes
from praxis.application.use_cases import BuscarExpediente

__all__ = ["BuscarExpediente", "CatalogoComisiones", "FuenteExpedientes"]
