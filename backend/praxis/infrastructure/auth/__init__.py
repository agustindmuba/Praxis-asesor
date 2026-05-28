"""Adaptadores de autenticación.

Implementa el puerto `AuthProvider` definido en `praxis.application.ports`.
"""

from praxis.infrastructure.auth.clerk import ClerkAuthProvider

__all__ = ["ClerkAuthProvider"]
