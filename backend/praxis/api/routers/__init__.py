"""Routers FastAPI por dominio.

Cada router declara su propio `APIRouter` y se monta en `praxis.api.main`.
"""

from praxis.api.routers import auth, expedientes, seguimientos

__all__ = ["auth", "expedientes", "seguimientos"]
