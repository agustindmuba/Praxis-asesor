"""Entidades de dominio para el Boletín Oficial.

Tres unidades de información:

- `NormaBO`: snapshot de una norma publicada en el BO (metadata). Es
  hecho objetivo y compartido entre despachos.
- `NormaBOTexto`: el cuerpo completo del texto. Vive en relación 1:1
  con `NormaBO` pero en tabla aparte (ADR 0006 §D2). Sólo se usa
  internamente — nunca se expone en UI.
- `ClasificacionNormaBO`: clasificación general (área temática,
  organismo, palabras clave). Producida por LLM, cacheable por hash
  del sumario.
- `NormaBOAccionable`: vista de la norma desde el ángulo de un
  despacho específico. Score + razón + expedientes tocados. Se
  RECALCULA si cambia el perfil del despacho.

Convenciones (alineadas con ADR 0002, 0006, 0007):

- Entidades inmutables (`frozen=True`) cuando son snapshots.
- Strings se preservan tal cual del BO; normalización liviana (strip,
  collapse whitespace) sí se aplica.
- Fechas siempre `date`, no string.
- `hash_sumario` es `sha256(sumario)` en lowercase hex; permite dedup
  + cache de clasificación cuando el contenido no cambió.

Ver `docs/specs/15-resumen-bo-accionable.md` y
`docs/adr/0006-modelo-bo-noticias-menciones-whatsapp.md`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from praxis.domain.area_tematica import AreaTematica


class SeccionBO(StrEnum):
    """Secciones lógicas del BO que el modelo conoce.

    **Importante:** estos valores NO se corresponden 1:1 con las
    secciones formales del BO (Primera, Segunda, Tercera, Cuarta). Tras
    feat-39.3 descubrimos que las **designaciones se publican como
    Decretos dentro de la Primera Sección** (no en una sección aparte).
    La "Cuarta Sección" del BO es "Registro de Dominios de Internet",
    irrelevante v1.

    En v1 procesamos sólo la **Primera Sección** (PDF `primera.pdf`) y
    distinguimos legislación de designaciones por el contenido/tipo de
    la norma. Para no romper el modelo de datos, mantenemos los 3
    valores enum como categorías lógicas:

    - `LEGISLACION`: el catch-all de la Primera Sección (decretos,
      resoluciones, leyes, etc. — incluye designaciones implícitamente).
    - `DESIGNACIONES`: reservado para v2, cuando el LLM podrá
      clasificar específicamente designaciones y mostrar la sección
      filtrada en la UI.
    - `AVISOS_OFICIALES`: reservado para v2 vía SAIJ.
    """

    LEGISLACION = "legislacion"
    DESIGNACIONES = "designaciones"
    AVISOS_OFICIALES = "avisos_oficiales"


# Secciones efectivamente procesadas en runtime v1.
#
# Solo LEGISLACION en v1: bajamos el PDF de la Primera Sección y de ahí
# salen todas las normas (incluso designaciones, que están como Decretos).
# Ver `docs/spikes/39-boletin-oficial.md` §"Conclusiones tras feat-39.3".
SECCIONES_ACTIVAS_V1: frozenset[SeccionBO] = frozenset(
    {SeccionBO.LEGISLACION}
)


class PrioridadAccionabilidad(StrEnum):
    """Prioridad derivada del score 0-100 del scoring por despacho.

    Mapping (spec 15 §"Accionabilidad por despacho"):
      score >= 60 → ALTA
      score >= 30 → MEDIA
      score >= 15 → BAJA
      score <  15 → no aparece como accionable
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


# Versión del prompt/heurística de clasificación de BO.
# Bump cuando cambie materialmente el comportamiento del clasificador;
# los caches viejos siguen siendo válidos hasta que se invaliden
# manualmente o se reclasifique con la nueva version.
BO_PROMPT_VERSION = "v1"

# Umbral mínimo de score para considerar una norma accionable para un
# despacho. Debajo de esto se descarta y no se persiste como
# accionable.
SCORE_MINIMO_ACCIONABLE = 15

# Para mostrarse al usuario, la razón es máximo 1 frase corta.
MAX_RAZON_ACCIONABILIDAD_CHARS = 140


# Para colapsar whitespace y \n duplicados en sumarios del BO sin
# perder estructura. El BO suele venir con tabulaciones y saltos
# de línea raros del PDF.
_WHITESPACE_RE = re.compile(r"\s+")


def _normalizar_sumario(texto: str) -> str:
    """Strip + collapse runs de whitespace a 1 espacio.

    Preserva el contenido pero hace los sumarios comparables (mismo
    contenido → mismo hash).
    """
    return _WHITESPACE_RE.sub(" ", texto).strip()


def hash_sumario(sumario: str) -> str:
    """Devuelve sha256 hex del sumario normalizado.

    Usado para:
    1. Dedup: si dos publicaciones del mismo número de norma tienen el
       mismo hash, son la misma norma (no se duplica).
    2. Cache de clasificación: la `ClasificacionNormaBO` se cachea por
       `hash_sumario` + `BO_PROMPT_VERSION`. Si el contenido y el
       prompt no cambiaron, no se vuelve a llamar al LLM.
    """
    normalizado = _normalizar_sumario(sumario)
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NormaBO:
    """Una norma publicada en el Boletín Oficial.

    Identidad lógica: `(fecha_publicacion, seccion, tipo_norma,
    numero_norma)`. Si el mismo número de norma aparece dos veces el
    mismo día (escenario muy raro), `hash_sumario` discrimina.

    Inmutable: una norma publicada no cambia. Si el BO publica una
    rectificación, eso es una NormaBO nueva (otro número).
    """

    id: UUID | None
    fecha_publicacion: date
    seccion: SeccionBO
    tipo_norma: str             # "decreto", "ley", "resolucion", ...
    numero_norma: str           # "412/2026", "27.812", "88/2026"
    organismo_emisor: str
    sumario: str                # tal cual del BO, normalizado
    url_oficial: str            # link al PDF/HTML en boletinoficial.gob.ar
    hash_sumario: str           # sha256 hex de sumario normalizado
    capturado_en: datetime

    def __post_init__(self) -> None:
        if not self.tipo_norma.strip():
            raise ValueError("NormaBO.tipo_norma no puede ser vacío")
        if not self.numero_norma.strip():
            raise ValueError("NormaBO.numero_norma no puede ser vacío")
        if not self.organismo_emisor.strip():
            raise ValueError("NormaBO.organismo_emisor no puede ser vacío")
        if not self.sumario.strip():
            raise ValueError("NormaBO.sumario no puede ser vacío")
        if not self.url_oficial.strip():
            raise ValueError("NormaBO.url_oficial no puede ser vacío")
        if len(self.hash_sumario) != 64:
            raise ValueError(
                "NormaBO.hash_sumario debe ser sha256 hex (64 chars), "
                f"recibido len={len(self.hash_sumario)}"
            )


@dataclass(frozen=True, slots=True)
class NormaBOTexto:
    """Cuerpo completo del texto de una norma BO.

    En tabla aparte (`norma_bo_texto`, ADR 0006 §D2). Nunca se expone
    en endpoints o UI: el usuario va al BO oficial. Lo usamos para
    reclasificación si cambia el prompt, detección de referencias
    legales y futura búsqueda full-text.

    Identidad: `norma_id` (1:1 con `NormaBO.id`).
    """

    norma_id: UUID
    texto: str
    capturado_en: datetime

    def __post_init__(self) -> None:
        if not self.texto.strip():
            raise ValueError("NormaBOTexto.texto no puede ser vacío")


@dataclass(frozen=True, slots=True)
class ClasificacionNormaBO:
    """Clasificación general de una norma (no depende del despacho).

    Cacheable por `(norma_id, modelo, prompt_version)`. Si cambia el
    prompt o el modelo, se reclasifica.
    """

    id: UUID | None
    norma_id: UUID
    area_tematica: AreaTematica
    palabras_clave: list[str]
    afecta_expedientes_hcdn: bool
    referencias_legales: list[str]   # ["Ley 24.660", "Decreto 1.422/2020"]
    modelo: str                       # "fake-keywords" | "claude-sonnet-4-5-..."
    prompt_version: str
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.modelo.strip():
            raise ValueError("ClasificacionNormaBO.modelo no puede estar vacío")
        if not self.prompt_version.strip():
            raise ValueError(
                "ClasificacionNormaBO.prompt_version no puede estar vacío"
            )
        # palabras_clave y referencias_legales pueden ser listas vacías
        # (norma sin keywords claras o sin referencias a otras normas),
        # pero NO None.


@dataclass(frozen=True, slots=True)
class NormaBOAccionable:
    """Una norma vista desde el ángulo de un despacho concreto.

    Se RECALCULA cuando cambia el perfil del despacho — no es un hecho,
    es una vista derivada. UPSERT por `(norma_id, despacho_id)`.

    Si el score cae bajo `SCORE_MINIMO_ACCIONABLE`, la fila se elimina
    (no aparece como accionable).
    """

    norma_id: UUID
    despacho_id: UUID
    score: int                     # 0-100
    prioridad: PrioridadAccionabilidad
    razon: str                     # 1 frase ≤ 140 chars
    expedientes_tocados: list[UUID]
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(
                f"NormaBOAccionable.score debe estar en [0, 100], "
                f"recibido {self.score}"
            )
        if self.score < SCORE_MINIMO_ACCIONABLE:
            raise ValueError(
                f"NormaBOAccionable.score ({self.score}) está bajo el "
                f"umbral mínimo {SCORE_MINIMO_ACCIONABLE}. Si no es "
                f"accionable, no se debe construir la entidad."
            )
        # Validar coherencia score ↔ prioridad.
        prioridad_esperada = _prioridad_para_score(self.score)
        if self.prioridad != prioridad_esperada:
            raise ValueError(
                f"NormaBOAccionable.prioridad ({self.prioridad}) no es "
                f"coherente con score {self.score} (esperaba "
                f"{prioridad_esperada})"
            )
        # Razón debe estar acotada para entrar en UI / WhatsApp.
        razon_strip = self.razon.strip()
        if not razon_strip:
            raise ValueError("NormaBOAccionable.razon no puede ser vacío")
        if len(razon_strip) > MAX_RAZON_ACCIONABILIDAD_CHARS:
            raise ValueError(
                f"NormaBOAccionable.razon excede {MAX_RAZON_ACCIONABILIDAD_CHARS} "
                f"chars (recibido {len(razon_strip)})"
            )


def _prioridad_para_score(score: int) -> PrioridadAccionabilidad:
    """Mapea score 0-100 a prioridad según los umbrales spec 15."""
    if score >= 60:
        return PrioridadAccionabilidad.ALTA
    if score >= 30:
        return PrioridadAccionabilidad.MEDIA
    return PrioridadAccionabilidad.BAJA


def prioridad_para_score(score: int) -> PrioridadAccionabilidad:
    """API pública para que el caller derive prioridad antes de
    construir la entidad."""
    if not 0 <= score <= 100:
        raise ValueError(f"score debe estar en [0, 100], recibido {score}")
    if score < SCORE_MINIMO_ACCIONABLE:
        raise ValueError(
            f"score {score} bajo umbral mínimo {SCORE_MINIMO_ACCIONABLE}; "
            "no se debe construir NormaBOAccionable"
        )
    return _prioridad_para_score(score)


# ---------------------------------------------------------------------------
# Resultado del clasificador LLM
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClasificacionNormaBOResult:
    """Resultado puro del `LlmProvider.clasificar_norma_bo()`.

    Es lo que el provider devuelve; el caller (use case) hidrata a
    `ClasificacionNormaBO` agregando `norma_id`, `modelo`, `prompt_version`
    y `generado_en` antes de persistir.

    Sigue el mismo patrón que `clasificar_area_tematica → AreaTematica`:
    el provider sólo conoce el resultado conceptual, no la entidad de
    persistencia.
    """

    area_tematica: AreaTematica
    palabras_clave: list[str]
    afecta_expedientes_hcdn: bool
    referencias_legales: list[str]
