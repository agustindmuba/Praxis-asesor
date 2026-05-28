"""Mappers entre ORM models y entidades de dominio.

Convención:
- `to_<entidad>(orm)` toma un ORM model y devuelve una entidad de dominio.
- `from_<entidad>(domain)` toma una entidad y devuelve un ORM model.

Mantener acá toda la traducción evita que el dominio importe SQLAlchemy.
"""

from __future__ import annotations

from typing import Any

from praxis.domain.despacho import Despacho
from praxis.infrastructure.persistence.models import DespachoOrm


def to_despacho(orm: DespachoOrm) -> Despacho:
    return Despacho(
        id=orm.id,
        nombre=orm.nombre,
        legislador_titular_slug=orm.legislador_titular_slug,
        configuracion=dict(orm.configuracion),  # copia defensiva
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def from_despacho(domain: Despacho) -> DespachoOrm:
    """Construye un ORM nuevo desde una entidad de dominio.

    Si `domain.id` viene seteado, se respeta (caso típico: testing o restauración).
    Si no, el default_factory de la columna lo genera (uuid7).
    """
    kwargs: dict[str, Any] = {
        "nombre": domain.nombre,
        "legislador_titular_slug": domain.legislador_titular_slug,
        "configuracion": dict(domain.configuracion),
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return DespachoOrm(**kwargs)
