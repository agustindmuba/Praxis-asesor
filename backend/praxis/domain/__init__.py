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
    ClasificacionNormaBOResult,
    NormaBO,
    NormaBOAccionable,
    NormaBOTexto,
    PrioridadAccionabilidad,
    SeccionBO,
    hash_sumario,
    prioridad_para_score,
)
from praxis.domain.noticia import (
    MAX_BAJADA_PROPIA_CHARS,
    MAX_SNIPPET_CONTEXTO_CHARS,
    NOTICIA_PROMPT_VERSION,
    AlcanceMedio,
    AlertaMencionEnviada,
    Articulo,
    ArticuloRelevante,
    ClasificacionArticulo,
    DisambiguacionMencion,
    FuenteNoticia,
    Mencion,
    ModoAccesoFuente,
    TipoFuenteNoticia,
    TonoLiteral,
    TonoMencion,
    canonicalizar_url,
    hash_url,
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
    "MAX_BAJADA_PROPIA_CHARS",
    "MAX_RAZON_ACCIONABILIDAD_CHARS",
    "MAX_SNIPPET_CONTEXTO_CHARS",
    "NOTICIA_PROMPT_VERSION",
    "PROMPT_VERSION",
    "SCORE_MINIMO_ACCIONABLE",
    "SECCIONES_ACTIVAS_V1",
    "AlcanceMedio",
    "AlertaBriefing",
    "AlertaMencionEnviada",
    "AntecedenteParecido",
    "AreaTematica",
    "Articulo",
    "ArticuloRelevante",
    "AuthClaims",
    "AuthError",
    "AuthErrorCode",
    "Bloque",
    "Briefing",
    "Camara",
    "ClasificacionArticulo",
    "ClasificacionNormaBO",
    "ClasificacionNormaBOResult",
    "CofirmanteSugerido",
    "Comision",
    "ComparacionPeers",
    "Despacho",
    "DisambiguacionMencion",
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
    "FuenteNoticia",
    "FuenteOd",
    "Giro",
    "InferenciaResult",
    "InteligenciaExpediente",
    "Legislador",
    "MembresiaDespacho",
    "Mencion",
    "ModoAccesoFuente",
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
    "TipoFuenteNoticia",
    "TipoVotacion",
    "TonoLiteral",
    "TonoMencion",
    "TramiteEvento",
    "Usuario",
    "Votacion",
    "VotoLegislador",
    "VotoTipo",
    "canonicalizar_url",
    "eventos_recientes",
    "filter_by_camara",
    "filter_by_rango",
    "hash_sumario",
    "hash_url",
    "inferir_caducidad",
    "inferir_estado",
    "inferir_estado_y_caducidad",
    "jaccard",
    "merge_tramite",
    "prioridad_para_score",
    "tokenizar_titulo",
    "validar_consistencia",
]
