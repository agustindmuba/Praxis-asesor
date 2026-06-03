"""Entidades de dominio para Noticias + Menciones (spec 16, feat-40).

Cuatro unidades de información:

- `FuenteNoticia`: un medio monitoreado (La Nación, Clarín, etc.).
  Catálogo global de fuentes nacionales y políticas, extensible con
  fuentes distritales por despacho (relación puente).
- `Articulo`: snapshot mínimo de un artículo. **NUNCA persiste el cuerpo
  del texto** (restricción legal — ADR 0006 §"Reglas de diseño 1"). Lo
  que vive en DB es metadata + bajada propia generada por Praxis.
- `ClasificacionArticulo`: clasificación general (área temática +
  palabras clave). Cacheada por artículo.
- `ArticuloRelevante`: vista por despacho del scoring de relevancia.
- `Mencion`: detección de una mención de un legislador en un artículo.
  Incluye snippet ≤200 chars (decisión D5: se persiste).
- `AlertaMencionEnviada`: auditoría de alertas WhatsApp efectivamente
  enviadas; se popula al lado consumidor en spec 17.

Convenciones (alineadas con ADR 0006):

- `frozen=True, slots=True` para entidades inmutables (snapshots).
- Restricción legal materializada: `Articulo` **no tiene campo `texto`**.
  El cuerpo se baja a memoria del worker para detección/clasificación
  y se descarta tras procesar (`FuenteNoticias.obtener_texto_articulo`).
- `hash_dedup` = sha256 de URL canonicalizada para idempotencia de
  ingesta cross-corrida.
- Tono y alcance del medio como literals (D7: alcance es catálogo
  fijo por fuente; D9: tono de bajada propia neutro).

Ver `docs/specs/16-briefing-noticias-y-menciones.md` y
`docs/adr/0006-modelo-bo-noticias-menciones-whatsapp.md`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from praxis.domain.area_tematica import AreaTematica


class TipoFuenteNoticia(StrEnum):
    """Categoría del medio monitoreado.

    `NACIONAL`: La Nación, Clarín, Infobae, Página/12, Perfil, Ámbito.
    `POLITICO`: Parlamentario, La Política Online, Letra P.
    `DISTRITAL`: agregados por un despacho específico (2-3 por despacho
    según spec 16).
    """

    NACIONAL = "nacional"
    POLITICO = "politico"
    DISTRITAL = "distrital"


class AlcanceMedio(StrEnum):
    """Alcance del medio. D7: catálogo fijo por fuente, no decide LLM.

    - `NACIONAL`: medios masivos con cobertura nacional.
    - `PROVINCIAL`: medios distritales o provinciales.
    - `NICHO`: medios especializados (políticos, sectoriales).
    """

    NACIONAL = "nacional"
    PROVINCIAL = "provincial"
    NICHO = "nicho"


class ModoAccesoFuente(StrEnum):
    """Cómo accedemos al contenido del medio.

    Preferencia: RSS > sitemap > scraping (ADR 0007 §"Prioridad RSS").
    """

    RSS = "rss"
    SITEMAP = "sitemap"
    SCRAPING = "scraping"


class TonoMencion(StrEnum):
    """Tono de una mención detectada por el clasificador.

    Los valores son los que la spec 16 define como salida del LLM
    disambiguator. `confianza_tono` (0-1) acompaña al valor.
    """

    POSITIVO = "positivo"
    NEUTRO = "neutro"
    NEGATIVO = "negativo"


# Tipos para tono (alias de Literal por convención del proyecto).
TonoLiteral = Literal["positivo", "neutro", "negativo"]


# Versión del prompt LLM para clasificación + bajada + tono.
# Bump si el prompt cambia materialmente.
NOTICIA_PROMPT_VERSION = "v1"

# Límites operativos.
MAX_BAJADA_PROPIA_CHARS = 240
MAX_SNIPPET_CONTEXTO_CHARS = 200


# Para normalizar URLs antes de hashear.
_URL_QUERY_NORMALIZE_RE = re.compile(r"[?#].*$")


def canonicalizar_url(url: str) -> str:
    """Normaliza una URL para dedup:

    - Lowercase del scheme + host.
    - Strip trailing slash.
    - Saca query string y fragment (típicos UTM/analytics).

    Mantenemos el path tal cual (case-sensitive) porque algunos medios
    usan slugs case-sensitive.
    """
    cleaned = _URL_QUERY_NORMALIZE_RE.sub("", url.strip())
    if "://" in cleaned:
        scheme, rest = cleaned.split("://", 1)
        host_path = rest.split("/", 1)
        host = host_path[0].lower()
        path = host_path[1] if len(host_path) > 1 else ""
        cleaned = f"{scheme.lower()}://{host}/{path}"
    cleaned = cleaned.rstrip("/")
    return cleaned


def hash_url(url: str) -> str:
    """sha256 hex de URL canonicalizada. Usado como `hash_dedup`."""
    return hashlib.sha256(canonicalizar_url(url).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FuenteNoticia:
    """Un medio monitoreado. Catálogo global + extensión por despacho."""

    id: UUID | None
    nombre: str                                # "La Nación"
    dominio: str                               # "lanacion.com.ar"
    tipo: TipoFuenteNoticia
    alcance: AlcanceMedio
    modo_acceso: ModoAccesoFuente
    feed_url: str | None = None
    distrito: str | None = None                # sólo si tipo=DISTRITAL
    robots_ok: bool = True
    ultima_revision: datetime | None = None
    activa: bool = True

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("FuenteNoticia.nombre no puede ser vacío")
        if not self.dominio.strip():
            raise ValueError("FuenteNoticia.dominio no puede ser vacío")
        if (
            self.modo_acceso in (ModoAccesoFuente.RSS, ModoAccesoFuente.SITEMAP)
            and not self.feed_url
        ):
            raise ValueError(
                f"FuenteNoticia.feed_url es requerido para modo_acceso="
                f"{self.modo_acceso.value}"
            )
        if self.tipo == TipoFuenteNoticia.DISTRITAL and not self.distrito:
            raise ValueError(
                "FuenteNoticia.distrito es requerido para tipo=distrital"
            )


@dataclass(frozen=True, slots=True)
class Articulo:
    """Snapshot mínimo de un artículo de un medio.

    **NUNCA tiene campo `texto_completo`** (regla legal materializada
    en el esquema, ADR 0006). El cuerpo se baja en memoria del worker
    para detección/clasificación y se descarta.

    `bajada_propia` es generada por LLM con tono neutro estilo Reuters
    (D9). 1 frase ≤240 chars. None hasta que se genere.
    """

    id: UUID | None
    fuente_id: UUID
    url: str
    titulo: str
    bajada_propia: str | None = None
    publicado_en: datetime | None = None
    capturado_en: datetime | None = None
    hash_dedup: str = ""                       # autocalculado en __post_init__

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("Articulo.url no puede ser vacía")
        if not self.titulo.strip():
            raise ValueError("Articulo.titulo no puede ser vacío")
        if self.bajada_propia is not None and len(
            self.bajada_propia
        ) > MAX_BAJADA_PROPIA_CHARS:
            raise ValueError(
                f"Articulo.bajada_propia excede {MAX_BAJADA_PROPIA_CHARS} "
                f"chars (recibido {len(self.bajada_propia)})"
            )
        # Si no se pasó hash_dedup, calcularlo. Por ser frozen, usamos
        # object.__setattr__.
        if not self.hash_dedup:
            object.__setattr__(self, "hash_dedup", hash_url(self.url))
        elif len(self.hash_dedup) != 64:
            raise ValueError(
                "Articulo.hash_dedup debe ser sha256 hex (64 chars), "
                f"recibido len={len(self.hash_dedup)}"
            )


@dataclass(frozen=True, slots=True)
class ClasificacionArticulo:
    """Clasificación general de un artículo (no depende del despacho).

    Cacheable por `(articulo_id, modelo, prompt_version)`. Si cambia el
    prompt o el modelo, se reclasifica.
    """

    id: UUID | None
    articulo_id: UUID
    area_tematica: AreaTematica
    palabras_clave: list[str] = field(default_factory=list)
    modelo: str = ""
    prompt_version: str = NOTICIA_PROMPT_VERSION
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.modelo.strip():
            raise ValueError("ClasificacionArticulo.modelo no puede estar vacío")
        if not self.prompt_version.strip():
            raise ValueError(
                "ClasificacionArticulo.prompt_version no puede estar vacío"
            )


@dataclass(frozen=True, slots=True)
class ArticuloRelevante:
    """Vista por despacho del scoring de relevancia.

    Análoga a `NormaBOAccionable`: se recalcula cuando cambia el
    perfil de interés del despacho. UPSERT por `(articulo_id,
    despacho_id)`.
    """

    articulo_id: UUID
    despacho_id: UUID
    score: int                                 # 0-100
    razon: str
    expedientes_tocados: list[UUID] = field(default_factory=list)
    generado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(
                f"ArticuloRelevante.score debe estar en [0, 100], "
                f"recibido {self.score}"
            )
        if not self.razon.strip():
            raise ValueError("ArticuloRelevante.razon no puede ser vacío")


@dataclass(frozen=True, slots=True)
class Mencion:
    """Mención de un legislador en un artículo (spec 16 D6).

    `snippet_contexto` ≤200 chars (D5: se persiste para histórico).
    `confianza_tono` viene del LLM disambiguator (D6).
    """

    id: UUID | None
    articulo_id: UUID
    legislador_id: UUID
    despacho_id: UUID
    snippet_contexto: str
    tono: TonoMencion
    confianza_tono: float
    alcance_medio: AlcanceMedio
    detectado_en: datetime | None = None
    notificada: bool = False

    def __post_init__(self) -> None:
        snippet_strip = self.snippet_contexto.strip()
        if not snippet_strip:
            raise ValueError("Mencion.snippet_contexto no puede ser vacío")
        if len(snippet_strip) > MAX_SNIPPET_CONTEXTO_CHARS:
            raise ValueError(
                f"Mencion.snippet_contexto excede "
                f"{MAX_SNIPPET_CONTEXTO_CHARS} chars (recibido "
                f"{len(snippet_strip)})"
            )
        if not 0.0 <= self.confianza_tono <= 1.0:
            raise ValueError(
                f"Mencion.confianza_tono debe estar en [0.0, 1.0], "
                f"recibido {self.confianza_tono}"
            )


@dataclass(frozen=True, slots=True)
class AlertaMencionEnviada:
    """Auditoría de alertas WhatsApp efectivamente enviadas (spec 17 +
    ADR 0009 anti-flood)."""

    id: UUID | None
    destinatario_id: UUID
    tipo: Literal["individual", "agrupada"]
    menciones_ids: list[UUID]
    plantilla_meta: str
    enviado_en: datetime
    estado: Literal["enviado", "fallo", "rechazado"]
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.menciones_ids:
            raise ValueError(
                "AlertaMencionEnviada.menciones_ids no puede ser vacía"
            )
        if self.tipo == "individual" and len(self.menciones_ids) != 1:
            raise ValueError(
                "AlertaMencionEnviada de tipo individual debe tener "
                "exactamente 1 mención"
            )
        if self.tipo == "agrupada" and len(self.menciones_ids) < 2:
            raise ValueError(
                "AlertaMencionEnviada de tipo agrupada debe tener "
                "≥ 2 menciones"
            )
