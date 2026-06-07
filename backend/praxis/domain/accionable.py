"""Entidad de dominio para Accionables enriquecidos con perfil opositor
(feat-42.2 — sprint A+B+F).

Un `AccionableEvento` es la respuesta del LLM (informado por el
perfil opositor del despacho) a la pregunta: "Apareció este evento
[norma BO | artículo de noticia], qué tiene que hacer Juliano con
esto?"

El LLM devuelve:
- razon_para_despacho: por qué importa para ESTE despacho (no genérico).
- accion_sugerida: enum con la acción concreta recomendada.
- explicacion_accion: 1-2 oraciones que dan contexto a la acción.
- tweets_sugeridos: 2-3 alternativas con distintos tonos.
- confianza: alta / media / baja.

Polimorfismo: 1 tabla `accionable_evento` con `(tipo_evento, evento_id)`
apuntando a `norma_bo.id` o `articulo.id`. UNIQUE en
(despacho_id, tipo_evento, evento_id) → 1 accionable por evento por
despacho. Si el asesor lo regenera, hacemos upsert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


ACCIONABLE_PROMPT_VERSION = "v1"


class TipoEvento(StrEnum):
    """Origen del evento sobre el que se generó el accionable."""

    NORMA_BO = "norma_bo"
    ARTICULO = "articulo"


class AccionSugerida(StrEnum):
    """Catálogo cerrado de acciones que el LLM puede sugerir.

    Cada una mapea a una pieza concreta de la rutina del despacho
    parlamentario. Si el LLM devuelve algo fuera del catálogo,
    cae a OTRO."""

    PEDIDO_INFORMES = "pedido_informes"
    PROYECTO_CONTRAPOSICION = "proyecto_contraposicion"
    DECLARACION_CAMARA = "declaracion_camara"
    SILENCIO_ESTRATEGICO = "silencio_estrategico"
    RETWEET_CRITICO = "retweet_critico"
    RETWEET_APOYO = "retweet_apoyo"
    ARTICULO_OPINION = "articulo_opinion"
    INTERPELACION = "interpelacion"
    OTRO = "otro"


# Etiquetas visibles en UI (ES). El frontend tiene su propia copia,
# esta lista sirve para validación/seed.
ACCION_LABELS: dict[AccionSugerida, str] = {
    AccionSugerida.PEDIDO_INFORMES: "Pedido de informes",
    AccionSugerida.PROYECTO_CONTRAPOSICION: "Proyecto de contraposición",
    AccionSugerida.DECLARACION_CAMARA: "Declaración de la cámara",
    AccionSugerida.SILENCIO_ESTRATEGICO: "Silencio estratégico",
    AccionSugerida.RETWEET_CRITICO: "RT con comentario crítico",
    AccionSugerida.RETWEET_APOYO: "RT con comentario de apoyo",
    AccionSugerida.ARTICULO_OPINION: "Artículo de opinión",
    AccionSugerida.INTERPELACION: "Interpelación / citación",
    AccionSugerida.OTRO: "Otro",
}


class ConfianzaAccionable(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class EstadoAccionable(StrEnum):
    """Estado de seguimiento del accionable por parte del asesor (feat-43.2).

    Alimenta el "feedback loop" que en feat-43.3 ajusta el tono del perfil
    opositor: si el asesor ignora consistentemente cierto tipo de acción,
    el bot lo aprende.
    """

    PENDIENTE = "pendiente"      # Default cuando se genera.
    HECHO = "hecho"              # El asesor ejecutó la acción tal cual.
    IGNORADO = "ignorado"        # El asesor decidió no actuar.
    ADAPTADO = "adaptado"        # El asesor hizo algo distinto (con nota).


@dataclass(frozen=True, slots=True)
class TweetSugerido:
    """Una propuesta de tweet por el LLM con su tono pretendido.

    `caracteres` se calcula en el constructor para que el frontend no
    tenga que recalcular. Límite tweet/X = 280; advertimos si excede.
    """

    tono: str                 # "frontal", "técnico", "irónico", "dialogal", etc.
    texto: str
    caracteres: int = 0

    def __post_init__(self) -> None:
        if not self.texto.strip():
            raise ValueError("TweetSugerido.texto no puede estar vacío")
        # Calculamos len si vino en 0; si vino con valor (deserialización
        # desde DB), respetamos.
        if self.caracteres == 0:
            object.__setattr__(self, "caracteres", len(self.texto))


@dataclass(slots=True)
class AccionableEvento:
    """Accionable generado por LLM informado por el perfil opositor.

    No frozen: el asesor puede editar el texto del tweet / cambiar
    la acción sugerida desde la UI (feat-42.3 futura).
    """

    despacho_id: UUID
    tipo_evento: TipoEvento
    evento_id: UUID                       # FK polimórfico a norma_bo.id o articulo.id

    razon_para_despacho: str
    accion_sugerida: AccionSugerida
    explicacion_accion: str
    tweets_sugeridos: list[TweetSugerido] = field(default_factory=list)
    confianza: ConfianzaAccionable = ConfianzaAccionable.MEDIA

    id: UUID | None = None
    generado_en: datetime | None = None
    editado_en: datetime | None = None
    modelo: str | None = None
    prompt_version: str = ACCIONABLE_PROMPT_VERSION

    # Feedback del asesor (feat-43.2).
    estado: EstadoAccionable = EstadoAccionable.PENDIENTE
    nota_asesor: str | None = None       # solo aplica si estado=ADAPTADO
    marcado_en: datetime | None = None   # cuándo el asesor lo marcó

    def __post_init__(self) -> None:
        if not self.razon_para_despacho.strip():
            raise ValueError("razon_para_despacho no puede estar vacío")
        if not self.explicacion_accion.strip():
            raise ValueError("explicacion_accion no puede estar vacío")
        if self.estado == EstadoAccionable.ADAPTADO and not (self.nota_asesor or "").strip():
            raise ValueError(
                "AccionableEvento.nota_asesor es obligatoria si estado=ADAPTADO",
            )
