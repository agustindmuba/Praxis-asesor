"""Servicios puros de la capa application.

A diferencia de los `use_cases`, los servicios no orquestan puertos —
contienen lógica pura (regex, parsing, scoring) que puede vivir solo en
memoria. Esto los hace trivialmente testeables y reusables desde
distintos casos de uso.
"""

from praxis.application.services.detector_candidatos_mencion import (
    CandidatoMencion,
    detectar_candidatos,
)

__all__ = ["CandidatoMencion", "detectar_candidatos"]
