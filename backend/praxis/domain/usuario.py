"""Entidades de dominio: Usuario, Rol, MembresiaDespacho.

Modela los actores humanos del sistema y su pertenencia a despachos.
Sin acoplamiento a auth todavía: `auth_provider_id` es opcional hasta
que la feature de auth (Clerk u otro) esté cableada.

Ver `docs/adr/0002-modelo-expediente.md` §"Multi-tenancy" y `0003-persistencia.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Rol(StrEnum):
    """Roles del usuario dentro de un despacho.

    Por ADR 0002 §"Roles del MVP":
    - JEFE_ASESORES: todo dentro del despacho.
    - ASESOR: lee todo del despacho; escribe en sus seguimientos/notas propios.
    - LECTOR: solo lectura del despacho.
    """

    JEFE_ASESORES = "jefe_asesores"
    ASESOR = "asesor"
    LECTOR = "lector"


@dataclass(slots=True)
class Usuario:
    """Usuario humano del sistema.

    `auth_provider_id` queda None hasta que el adapter de auth lo asocie
    con la identidad externa (Clerk, etc.). Permite invitar usuarios
    "pre-auth" o crear cuentas seed para testing.
    """

    id: UUID
    email: str
    nombre: str
    auth_provider_id: str | None = None
    activo: bool = True
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.email.strip():
            raise ValueError("Usuario.email no puede ser vacío")
        if not self.nombre.strip():
            raise ValueError("Usuario.nombre no puede ser vacío")
        if "@" not in self.email:
            raise ValueError(f"Usuario.email parece inválido: {self.email!r}")


@dataclass(slots=True)
class MembresiaDespacho:
    """Pertenencia de un Usuario a un Despacho, con su rol.

    PK lógica: (usuario_id, despacho_id). Un usuario puede pertenecer a
    múltiples despachos (caso típico: asesor que trabaja en dos bloques),
    cada uno con su rol propio.
    """

    usuario_id: UUID
    despacho_id: UUID
    rol: Rol
    activo: bool = True
    creado_en: datetime | None = None
