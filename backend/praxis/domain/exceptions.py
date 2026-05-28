"""Excepciones del dominio.

Estas viven en `domain/` porque son parte del contrato del modelo, no de
la infraestructura. Los adaptadores las lanzan, los casos de uso las
atrapan o las propagan.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todas las excepciones de dominio."""


class ExpedienteNoEncontrado(DomainError):
    """La fuente no encontró el expediente solicitado."""

    def __init__(self, numero: str, fuente: str | None = None) -> None:
        msg = f"Expediente '{numero}' no encontrado"
        if fuente:
            msg += f" en {fuente}"
        super().__init__(msg)
        self.numero = numero
        self.fuente = fuente


class FuenteNoDisponible(DomainError):
    """La fuente externa está caída, devuelve errores, o no responde."""

    def __init__(self, fuente: str, detalle: str | None = None) -> None:
        msg = f"Fuente '{fuente}' no disponible"
        if detalle:
            msg += f": {detalle}"
        super().__init__(msg)
        self.fuente = fuente
        self.detalle = detalle
