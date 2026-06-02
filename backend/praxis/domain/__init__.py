"""Capa Domain — entidades puras, value objects, reglas de negocio.

Ver `README.md` en esta carpeta para responsabilidades y restricciones.

Re-exporta los símbolos principales para imports cómodos desde casos de uso
e infraestructura. La regla es: si una entidad o value object es parte del
contrato público del dominio, vive en este __init__.
"""

from praxis.domain.area_tematica import (
    AREA_LABELS,
    CLASIFICACION_PROMPT_VERSION,
    AreaTematica,
    ExpedienteAreaTematica,
)
from praxis.domain.auth import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    RequestContext,
)
from praxis.domain.briefing import (
    BRIEFING_PROMPT_VERSION,
    AlertaBriefing,
    Briefing,
    PrioridadAlerta,
    ProyectoEnAreaBriefing,
    RecomendacionVoto,
    RolEnDespacho,
    SeccionAreaBriefing,
    SeccionProyectoBriefing,
)
from praxis.domain.briefing_similitud import (
    JACCARD_UMBRAL,
    AntecedenteParecido,
    CofirmanteSugerido,
    jaccard,
    tokenizar_titulo,
)
from praxis.domain.comision import Comision, TipoComision
from praxis.domain.despacho import Despacho
from praxis.domain.exceptions import (
    DomainError,
    ExpedienteNoEncontrado,
    FuenteNoDisponible,
)
from praxis.domain.expediente import (
    Expediente,
    Firmante,
    Giro,
    TramiteEvento,
)
from praxis.domain.expediente_query import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    ExpedienteQuery,
    ResultadoBusqueda,
)
from praxis.domain.inferencia_estado import (
    InferenciaResult,
    inferir_caducidad,
    inferir_estado,
    inferir_estado_y_caducidad,
)
from praxis.domain.inteligencia import (
    ComparacionPeers,
    EtapaPipeline,
    EtapaProgreso,
    InteligenciaExpediente,
    ProgresoTramite,
)
from praxis.domain.legislador import Bloque, Legislador
from praxis.domain.norma_bo import (
    BO_PROMPT_VERSION,
    MAX_RAZON_ACCIONABILIDAD_CHARS,
    SCORE_MINIMO_ACCIONABLE,
    SECCIONES_ACTIVAS_V1,
    ClasificacionNormaBO,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    PrioridadAccionabilidad,
    SeccionBO,
    hash_sumario,
    prioridad_para_score,
)
from praxis.domain.orden_del_dia import FuenteOd, OrdenDelDia
from praxis.domain.perfil_interes_despacho import PerfilInteresDespacho
from praxis.domain.resumen_ejecutivo import PROMPT_VERSION, ResumenEjecutivo
from praxis.domain.seguimiento import Prioridad, SeguimientoExpediente
from praxis.domain.tramite_historico import (
    eventos_recientes,
    filter_by_camara,
    filter_by_rango,
    merge_tramite,
    validar_consistencia,
)
from praxis.domain.usuario import MembresiaDespacho, Rol, Usuario
from praxis.domain.value_objects import (
    Camara,
    EstadoExpediente,
    NumeroExpediente,
    OrigenExpediente,
    TipoExpediente,
)
from praxis.domain.votacion import (
    TipoVotacion,
    Votacion,
    VotoLegislador,
    VotoTipo,
)

__all__ = [
    "AREA_LABELS",
    "BO_PROMPT_VERSION",
    "BRIEFING_PROMPT_VERSION",
    "CLASIFICACION_PROMPT_VERSION",
    "JACCARD_UMBRAL",
    "LIMIT_DEFAULT",
    "LIMIT_MAX",
    "MAX_RAZON_ACCIONABILIDAD_CHARS",
    "PROMPT_VERSION",
    "SCORE_MINIMO_ACCIONABLE",
    "SECCIONES_ACTIVAS_V1",
    "AlertaBriefing",
    "AntecedenteParecido",
    "AreaTematica",
    "AuthClaims",
    "AuthError",
    "AuthErrorCode",
    "Bloque",
    "Briefing",
    "Camara",
    "ClasificacionNormaBO",
    "CofirmanteSugerido",
    "Comision",
    "ComparacionPeers",
    "Despacho",
    "DomainError",
    "EstadoExpediente",
    "EtapaPipeline",
    "EtapaProgreso",
    "Expediente",
    "ExpedienteAreaTematica",
    "ExpedienteNoEncontrado",
    "ExpedienteQuery",
    "Firmante",
    "FuenteNoDisponible",
    "FuenteOd",
    "Giro",
    "InferenciaResult",
    "InteligenciaExpediente",
    "Legislador",
    "MembresiaDespacho",
    "NormaBO",
    "NormaBOAccionable",
    "NormaBOTexto",
    "NumeroExpediente",
    "OrdenDelDia",
    "OrigenExpediente",
    "PerfilInteresDespacho",
    "Prioridad",
    "PrioridadAccionabilidad",
    "PrioridadAlerta",
    "ProgresoTramite",
    "ProyectoEnAreaBriefing",
    "RecomendacionVoto",
    "RequestContext",
    "ResultadoBusqueda",
    "ResumenEjecutivo",
    "Rol",
    "RolEnDespacho",
    "SeccionAreaBriefing",
    "SeccionBO",
    "SeccionProyectoBriefing",
    "SeguimientoExpediente",
    "TipoComision",
    "TipoExpediente",
    "TipoVotacion",
    "TramiteEvento",
    "Usuario",
    "Votacion",
    "VotoLegislador",
    "VotoTipo",
    "eventos_recientes",
    "filter_by_camara",
    "filter_by_rango",
    "hash_sumario",
    "inferir_caducidad",
    "inferir_estado",
    "inferir_estado_y_caducidad",
    "jaccard",
    "merge_tramite",
    "prioridad_para_score",
    "tokenizar_titulo",
    "validar_consistencia",
]
