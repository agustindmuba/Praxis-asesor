"""Mappers entre ORM models y entidades de dominio.

Convención:
- `to_<entidad>(orm)` toma un ORM model y devuelve una entidad de dominio.
- `from_<entidad>(domain)` toma una entidad y devuelve un ORM model.

Mantener acá toda la traducción evita que el dominio importe SQLAlchemy.
"""

from __future__ import annotations

from typing import Any

from praxis.domain import (
    Camara,
    EstadoExpediente,
    Expediente,
    Firmante,
    Giro,
    MembresiaDespacho,
    NumeroExpediente,
    OrigenExpediente,
    Rol,
    TipoExpediente,
    TramiteEvento,
    Usuario,
)
from praxis.domain.despacho import Despacho
from praxis.infrastructure.persistence.models import (
    DespachoOrm,
    ExpedienteOrm,
    FirmanteOrm,
    GiroOrm,
    MembresiaDespachoOrm,
    TramiteEventoOrm,
    UsuarioOrm,
)

# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------


def to_despacho(orm: DespachoOrm) -> Despacho:
    return Despacho(
        id=orm.id,
        nombre=orm.nombre,
        legislador_titular_slug=orm.legislador_titular_slug,
        configuracion=dict(orm.configuracion),
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def from_despacho(domain: Despacho) -> DespachoOrm:
    kwargs: dict[str, Any] = {
        "nombre": domain.nombre,
        "legislador_titular_slug": domain.legislador_titular_slug,
        "configuracion": dict(domain.configuracion),
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return DespachoOrm(**kwargs)


# ---------------------------------------------------------------------------
# Expediente y relaciones
# ---------------------------------------------------------------------------


def to_expediente(orm: ExpedienteOrm) -> Expediente:
    """Hidrata un Expediente del dominio desde su ORM + relaciones cargadas.

    Nota: `expediente_relacionado` queda como None hasta que tengamos cross-ref
    resuelto en otra feature (ver ADR 0003 §"Tablas a crear").
    """
    numero = NumeroExpediente(
        numero=orm.numero,
        origen=OrigenExpediente(orm.origen),
        anio=orm.anio,
        camara=Camara(orm.camara),
    )
    firmantes = [_to_firmante(f) for f in sorted(orm.firmantes, key=lambda x: x.orden)]
    giros = [_to_giro(g) for g in orm.giros]
    tramite = [_to_tramite_evento(t) for t in orm.tramite]
    return Expediente(
        numero=numero,
        tipo=TipoExpediente(orm.tipo),
        titulo=orm.titulo,
        sumario=orm.sumario,
        fecha_ingreso=orm.fecha_ingreso,
        estado=EstadoExpediente(orm.estado),
        firmantes=firmantes,
        giros=giros,
        tramite=tramite,
        texto_url=orm.texto_url,
        fuente_url=orm.fuente_url,
        expediente_relacionado=None,
        fecha_caducidad=orm.fecha_caducidad,
        fecha_caducidad_original=orm.fecha_caducidad_original,
        prorrogado=orm.prorrogado,
    )


def from_expediente(domain: Expediente) -> ExpedienteOrm:
    """Crea un ORM nuevo desde el dominio. Hijos cascade vía relationship.

    No setea `id` salvo que sea explícito en el dominio (que actualmente no
    tiene campo id — es decisión hexagonal). El default_factory de la columna
    genera UUID v7.

    `expediente_relacionado` del dominio se ignora por ahora (la persistencia
    como FK self-ref llegará con una feature de cross-referencing).
    """
    orm = ExpedienteOrm(
        numero=domain.numero.numero,
        origen=domain.numero.origen.value,
        anio=domain.numero.anio,
        camara=domain.numero.camara.value,
        tipo=domain.tipo.value,
        titulo=domain.titulo,
        sumario=domain.sumario,
        fecha_ingreso=domain.fecha_ingreso,
        estado=domain.estado.value,
        texto_url=domain.texto_url,
        fuente_url=domain.fuente_url,
        fecha_caducidad=domain.fecha_caducidad,
        fecha_caducidad_original=domain.fecha_caducidad_original,
        prorrogado=domain.prorrogado,
        firmantes=[_from_firmante(f) for f in domain.firmantes],
        giros=[_from_giro(g) for g in domain.giros],
        tramite=[_from_tramite_evento(t) for t in domain.tramite],
    )
    return orm


def _to_firmante(orm: FirmanteOrm) -> Firmante:
    return Firmante(
        nombre=orm.nombre,
        distrito=orm.distrito,
        bloque=orm.bloque,
        orden=orm.orden,
    )


def _from_firmante(domain: Firmante) -> FirmanteOrm:
    return FirmanteOrm(
        nombre=domain.nombre,
        distrito=domain.distrito,
        bloque=domain.bloque,
        orden=domain.orden,
    )


def _to_giro(orm: GiroOrm) -> Giro:
    return Giro(
        comision=orm.comision,
        fecha_ingreso=orm.fecha_ingreso,
        fecha_egreso=orm.fecha_egreso,
        orden=orm.orden,
    )


def _from_giro(domain: Giro) -> GiroOrm:
    return GiroOrm(
        comision=domain.comision,
        fecha_ingreso=domain.fecha_ingreso,
        fecha_egreso=domain.fecha_egreso,
        orden=domain.orden,
    )


def _to_tramite_evento(orm: TramiteEventoOrm) -> TramiteEvento:
    return TramiteEvento(
        fecha=orm.fecha,
        camara=Camara(orm.camara),
        evento=orm.evento,
        detalle=orm.detalle,
        fuente=orm.fuente,
    )


def _from_tramite_evento(domain: TramiteEvento) -> TramiteEventoOrm:
    return TramiteEventoOrm(
        fecha=domain.fecha,
        camara=domain.camara.value,
        evento=domain.evento,
        detalle=domain.detalle,
        fuente=domain.fuente,
    )


# ---------------------------------------------------------------------------
# Usuario y MembresiaDespacho
# ---------------------------------------------------------------------------


def to_usuario(orm: UsuarioOrm) -> Usuario:
    return Usuario(
        id=orm.id,
        email=orm.email,
        nombre=orm.nombre,
        auth_provider_id=orm.auth_provider_id,
        activo=orm.activo,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def from_usuario(domain: Usuario) -> UsuarioOrm:
    kwargs: dict[str, Any] = {
        "email": domain.email.strip().lower(),
        "nombre": domain.nombre,
        "auth_provider_id": domain.auth_provider_id,
        "activo": domain.activo,
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return UsuarioOrm(**kwargs)


def to_membresia_despacho(orm: MembresiaDespachoOrm) -> MembresiaDespacho:
    return MembresiaDespacho(
        usuario_id=orm.usuario_id,
        despacho_id=orm.despacho_id,
        rol=Rol(orm.rol),
        activo=orm.activo,
        creado_en=orm.creado_en,
    )


def from_membresia_despacho(domain: MembresiaDespacho) -> MembresiaDespachoOrm:
    return MembresiaDespachoOrm(
        usuario_id=domain.usuario_id,
        despacho_id=domain.despacho_id,
        rol=domain.rol.value,
        activo=domain.activo,
    )
