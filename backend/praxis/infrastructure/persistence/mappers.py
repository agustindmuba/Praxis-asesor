"""Mappers entre ORM models y entidades de dominio.

Convención:
- `to_<entidad>(orm)` toma un ORM model y devuelve una entidad de dominio.
- `from_<entidad>(domain)` toma una entidad y devuelve un ORM model.

Mantener acá toda la traducción evita que el dominio importe SQLAlchemy.
"""

from __future__ import annotations

from typing import Any

from praxis.domain import (
    AreaTematica,
    Camara,
    EstadoExpediente,
    Expediente,
    ExpedienteAreaTematica,
    Firmante,
    Giro,
    MembresiaDespacho,
    NumeroExpediente,
    OrigenExpediente,
    Prioridad,
    ResumenEjecutivo,
    Rol,
    SeguimientoExpediente,
    TipoExpediente,
    TipoVotacion,
    TramiteEvento,
    Usuario,
    Votacion,
    VotoLegislador,
    VotoTipo,
)
from praxis.domain.despacho import Despacho
from praxis.infrastructure.persistence.models import (
    DespachoOrm,
    ExpedienteAreaTematicaOrm,
    ExpedienteOrm,
    FirmanteOrm,
    GiroOrm,
    MembresiaDespachoOrm,
    ResumenEjecutivoOrm,
    SeguimientoExpedienteOrm,
    TramiteEventoOrm,
    UsuarioOrm,
    VotacionOrm,
    VotoLegisladorOrm,
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
        id=orm.id,
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


# ---------------------------------------------------------------------------
# SeguimientoExpediente
# ---------------------------------------------------------------------------


def to_seguimiento(orm: SeguimientoExpedienteOrm) -> SeguimientoExpediente:
    return SeguimientoExpediente(
        id=orm.id,
        despacho_id=orm.despacho_id,
        expediente_id=orm.expediente_id,
        responsable_id=orm.responsable_id,
        prioridad=Prioridad(orm.prioridad),
        archivado=orm.archivado,
        creado_en=orm.creado_en,
        actualizado_en=orm.actualizado_en,
    )


def from_seguimiento(domain: SeguimientoExpediente) -> SeguimientoExpedienteOrm:
    kwargs: dict[str, Any] = {
        "despacho_id": domain.despacho_id,
        "expediente_id": domain.expediente_id,
        "responsable_id": domain.responsable_id,
        "prioridad": domain.prioridad.value,
        "archivado": domain.archivado,
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return SeguimientoExpedienteOrm(**kwargs)


# ---------------------------------------------------------------------------
# ResumenEjecutivo
# ---------------------------------------------------------------------------


def to_resumen_ejecutivo(orm: ResumenEjecutivoOrm) -> ResumenEjecutivo:
    return ResumenEjecutivo(
        id=orm.id,
        expediente_id=orm.expediente_id,
        contenido_md=orm.contenido_md,
        modelo=orm.modelo,
        prompt_version=orm.prompt_version,
        generado_en=orm.generado_en,
    )


def from_resumen_ejecutivo(domain: ResumenEjecutivo) -> ResumenEjecutivoOrm:
    kwargs: dict[str, Any] = {
        "expediente_id": domain.expediente_id,
        "contenido_md": domain.contenido_md,
        "modelo": domain.modelo,
        "prompt_version": domain.prompt_version,
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return ResumenEjecutivoOrm(**kwargs)


# ---------------------------------------------------------------------------
# Votacion + VotoLegislador
# ---------------------------------------------------------------------------


def to_votacion(orm: VotacionOrm) -> Votacion:
    return Votacion(
        id=orm.id,
        camara=Camara(orm.camara),
        fecha=orm.fecha,
        sesion=orm.sesion,
        asunto=orm.asunto,
        tipo=TipoVotacion(orm.tipo),
        resultado_afirmativos=orm.resultado_afirmativos,
        resultado_negativos=orm.resultado_negativos,
        resultado_abstenciones=orm.resultado_abstenciones,
        resultado_sin_votar=orm.resultado_sin_votar,
        resultado_ausentes=orm.resultado_ausentes,
        aprobada=orm.aprobada,
        presidida_por=orm.presidida_por,
        expediente_id=orm.expediente_id,
        titulo_od=orm.titulo_od,
        acta_id_hcdn=orm.acta_id_hcdn,
        acta_pdf_url=orm.acta_pdf_url,
        fuente_url=orm.fuente_url,
    )


def from_votacion(
    domain: Votacion,
    votos: list[VotoLegislador] | None = None,
) -> VotacionOrm:
    """Crea un ORM nuevo desde el dominio + los votos individuales.

    Los votos se persisten cascade vía la relationship `votos`. No setea
    `id` salvo que el dominio lo traiga explícito (UUID v7 lo genera el
    default_factory de la columna).
    """
    kwargs: dict[str, Any] = {
        "camara": domain.camara.value,
        "fecha": domain.fecha,
        "sesion": domain.sesion,
        "asunto": domain.asunto,
        "tipo": domain.tipo.value,
        "resultado_afirmativos": domain.resultado_afirmativos,
        "resultado_negativos": domain.resultado_negativos,
        "resultado_abstenciones": domain.resultado_abstenciones,
        "resultado_sin_votar": domain.resultado_sin_votar,
        "resultado_ausentes": domain.resultado_ausentes,
        "aprobada": domain.aprobada,
        "presidida_por": domain.presidida_por,
        "expediente_id": domain.expediente_id,
        "titulo_od": domain.titulo_od,
        "acta_id_hcdn": domain.acta_id_hcdn,
        "acta_pdf_url": domain.acta_pdf_url,
        "fuente_url": domain.fuente_url,
        "votos": [_from_voto_legislador(v) for v in (votos or [])],
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return VotacionOrm(**kwargs)


def _to_voto_legislador(orm: VotoLegisladorOrm) -> VotoLegislador:
    return VotoLegislador(
        legislador_nombre=orm.legislador_nombre,
        voto=VotoTipo(orm.voto),
        bloque=orm.bloque,
        distrito=orm.distrito,
        que_dijo=orm.que_dijo,
        legislador_hcdn_id=orm.legislador_hcdn_id,
    )


def _from_voto_legislador(domain: VotoLegislador) -> VotoLegisladorOrm:
    return VotoLegisladorOrm(
        legislador_nombre=domain.legislador_nombre,
        voto=domain.voto.value,
        bloque=domain.bloque,
        distrito=domain.distrito,
        que_dijo=domain.que_dijo,
        legislador_hcdn_id=domain.legislador_hcdn_id,
    )


def to_voto_legislador(orm: VotoLegisladorOrm) -> VotoLegislador:
    """Conveniencia pública del mapper privado."""
    return _to_voto_legislador(orm)


# ---------------------------------------------------------------------------
# ExpedienteAreaTematica
# ---------------------------------------------------------------------------


def to_expediente_area_tematica(
    orm: ExpedienteAreaTematicaOrm,
) -> ExpedienteAreaTematica:
    return ExpedienteAreaTematica(
        id=orm.id,
        expediente_id=orm.expediente_id,
        area=AreaTematica(orm.area),
        modelo=orm.modelo,
        prompt_version=orm.prompt_version,
        generado_en=orm.generado_en,
    )


def from_expediente_area_tematica(
    domain: ExpedienteAreaTematica,
) -> ExpedienteAreaTematicaOrm:
    kwargs: dict[str, Any] = {
        "expediente_id": domain.expediente_id,
        "area": domain.area.value,
        "modelo": domain.modelo,
        "prompt_version": domain.prompt_version,
    }
    if domain.id is not None:
        kwargs["id"] = domain.id
    return ExpedienteAreaTematicaOrm(**kwargs)
