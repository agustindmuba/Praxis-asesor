"""Repositorios SQLAlchemy async.

Cada repo implementa un puerto definido en `praxis.application.ports`.
Convención: una clase por agregado raíz.
"""

from praxis.infrastructure.persistence.repositories.briefing import (
    SqlAlchemyBriefingRepository,
)
from praxis.infrastructure.persistence.repositories.despacho import (
    SqlAlchemyDespachoRepository,
)
from praxis.infrastructure.persistence.repositories.efemeride import (
    SqlAlchemyEfemerideRepository,
)
from praxis.infrastructure.persistence.repositories.expediente import (
    SqlAlchemyExpedienteRepository,
)
from praxis.infrastructure.persistence.repositories.expediente_area_tematica import (
    SqlAlchemyExpedienteAreaTematicaRepository,
)
from praxis.infrastructure.persistence.repositories.membresia_despacho import (
    SqlAlchemyMembresiaDespachoRepository,
)
from praxis.infrastructure.persistence.repositories.norma_bo import (
    SqlAlchemyClasificacionNormaBORepository,
    SqlAlchemyNormaBOAccionableRepository,
    SqlAlchemyNormaBORepository,
    SqlAlchemyNormaBOTextoRepository,
)
from praxis.infrastructure.persistence.repositories.noticia import (
    SqlAlchemyArticuloHashRepository,
    SqlAlchemyArticuloRelevanteRepository,
    SqlAlchemyArticuloRepository,
    SqlAlchemyClasificacionArticuloRepository,
    SqlAlchemyFuenteNoticiaRepository,
    SqlAlchemyMencionRepository,
)
from praxis.infrastructure.persistence.repositories.orden_del_dia import (
    SqlAlchemyOrdenDelDiaRepository,
)
from praxis.infrastructure.persistence.repositories.accionable import (
    SqlAlchemyAccionableEventoRepository,
)
from praxis.infrastructure.persistence.repositories.perfil_interes_despacho import (
    SqlAlchemyPerfilInteresDespachoRepository,
)
from praxis.infrastructure.persistence.repositories.perfil_opositor import (
    SqlAlchemyPerfilOpositorRepository,
)
from praxis.infrastructure.persistence.repositories.proyecto_redaccion import (
    SqlAlchemyProyectoRedaccionRepository,
)
from praxis.infrastructure.persistence.repositories.resumen_ejecutivo import (
    SqlAlchemyResumenEjecutivoRepository,
)
from praxis.infrastructure.persistence.repositories.seguimiento import (
    SqlAlchemySeguimientoExpedienteRepository,
)
from praxis.infrastructure.persistence.repositories.usuario import (
    SqlAlchemyUsuarioRepository,
)
from praxis.infrastructure.persistence.repositories.votacion import (
    SqlAlchemyVotacionRepository,
)
from praxis.infrastructure.persistence.repositories.whatsapp import (
    SqlAlchemyDestinatarioRepository,
    SqlAlchemyEnvioWhatsAppRepository,
    SqlAlchemyPlantillaWhatsAppRepository,
)

__all__ = [
    "SqlAlchemyArticuloHashRepository",
    "SqlAlchemyArticuloRelevanteRepository",
    "SqlAlchemyArticuloRepository",
    "SqlAlchemyBriefingRepository",
    "SqlAlchemyClasificacionArticuloRepository",
    "SqlAlchemyClasificacionNormaBORepository",
    "SqlAlchemyDespachoRepository",
    "SqlAlchemyDestinatarioRepository",
    "SqlAlchemyEfemerideRepository",
    "SqlAlchemyEnvioWhatsAppRepository",
    "SqlAlchemyExpedienteAreaTematicaRepository",
    "SqlAlchemyExpedienteRepository",
    "SqlAlchemyFuenteNoticiaRepository",
    "SqlAlchemyMembresiaDespachoRepository",
    "SqlAlchemyMencionRepository",
    "SqlAlchemyNormaBOAccionableRepository",
    "SqlAlchemyNormaBORepository",
    "SqlAlchemyNormaBOTextoRepository",
    "SqlAlchemyOrdenDelDiaRepository",
    "SqlAlchemyAccionableEventoRepository",
    "SqlAlchemyPerfilInteresDespachoRepository",
    "SqlAlchemyPerfilOpositorRepository",
    "SqlAlchemyProyectoRedaccionRepository",
    "SqlAlchemyPlantillaWhatsAppRepository",
    "SqlAlchemyResumenEjecutivoRepository",
    "SqlAlchemySeguimientoExpedienteRepository",
    "SqlAlchemyUsuarioRepository",
    "SqlAlchemyVotacionRepository",
]
