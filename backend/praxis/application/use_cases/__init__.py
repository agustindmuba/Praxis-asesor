"""Casos de uso de la aplicación.

Cada caso de uso es una unidad de orquestación entre puertos. NO contiene
lógica de negocio (eso es dominio), NI conoce implementaciones concretas
(eso es infrastructure).
"""

from praxis.application.use_cases.buscar_antecedente_parecido import (
    BuscarAntecedenteParecido,
)
from praxis.application.use_cases.buscar_expediente import BuscarExpediente
from praxis.application.use_cases.calcular_inteligencia import (
    CalcularInteligenciaExpediente,
)
from praxis.application.use_cases.clasificar_area_tematica import (
    ClasificarExpedienteTematicamente,
)
from praxis.application.use_cases.detectar_menciones_en_articulo import (
    DetectarMencionesEnArticulo,
    LegisladorAMonitorear,
)
from praxis.application.use_cases.enriquecer_expediente import EnriquecerExpediente
from praxis.application.use_cases.enviar_alerta_mencion import (
    EnviarAlertaMencion,
    IntencionDeAlerta,
)
from praxis.application.use_cases.enviar_briefing_diario import (
    EnviarBriefingDiario,
    ResultadoBriefingDiario,
)
from praxis.application.use_cases.generar_briefing import GenerarBriefing
from praxis.application.use_cases.generar_resumen_ejecutivo import (
    GenerarResumenEjecutivo,
)
from praxis.application.use_cases.procesar_articulos_de_fuente import (
    DespachoSuscrito,
    ProcesarArticulosDeFuente,
    ResultadoProcesamiento,
    calcular_score_relevancia,
)
from praxis.application.use_cases.procesar_webhook_whatsapp import (
    ProcesarWebhookWhatsApp,
    ResultadoWebhook,
)
from praxis.application.use_cases.resolver_contexto import ResolverContextoRequest
from praxis.application.use_cases.sincronizar_usuario_clerk import (
    SincronizarUsuarioDesdeClerk,
)
from praxis.application.use_cases.sugerir_cofirmantes import SugerirCofirmantes

__all__ = [
    "BuscarAntecedenteParecido",
    "BuscarExpediente",
    "CalcularInteligenciaExpediente",
    "ClasificarExpedienteTematicamente",
    "DespachoSuscrito",
    "DetectarMencionesEnArticulo",
    "EnriquecerExpediente",
    "EnviarAlertaMencion",
    "EnviarBriefingDiario",
    "GenerarBriefing",
    "GenerarResumenEjecutivo",
    "IntencionDeAlerta",
    "LegisladorAMonitorear",
    "ProcesarArticulosDeFuente",
    "ProcesarWebhookWhatsApp",
    "ResolverContextoRequest",
    "ResultadoBriefingDiario",
    "ResultadoProcesamiento",
    "ResultadoWebhook",
    "SincronizarUsuarioDesdeClerk",
    "SugerirCofirmantes",
    "calcular_score_relevancia",
]
