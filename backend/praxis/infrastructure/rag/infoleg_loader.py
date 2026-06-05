"""Loader de normativa argentina desde InfoLEG (feat-42.6).

Baja HTML de http://servicios.infoleg.gob.ar/, parsea, divide por
artículo y devuelve `list[NormaChunk]` listo para embeber e indexar.

El catálogo de normas a cargar vive en `CATALOGO_NORMAS` abajo —
agregar/quitar líneas para extender el corpus.

URLs estables observadas en InfoLEG:
- Constitución Nacional: anexos/0-4999/804/norma.htm
- Leyes:                  anexos/{rango_miles}/{num}/texact.htm
  Donde rango_miles es "{primer}-{primer+4999}" según el número.
  Ej. Ley 25.188 → 25000 // 5000 * 5000 = 25000, rango 25000-29999.

`texact.htm` devuelve el texto consolidado con modificaciones —
preferido sobre `norma.htm` que es el texto original.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

INFOLEG_BASE = "http://servicios.infoleg.gob.ar/infolegInternet/anexos/"


@dataclass(frozen=True, slots=True)
class NormaChunk:
    fuente: str               # identificador legible, ej "ley_25188"
    articulo_label: str        # "Artículo 14", "Capítulo III - Inhabilidades"
    orden: int                  # posición dentro de la norma
    texto: str                  # contenido del chunk


@dataclass(frozen=True, slots=True)
class NormaCatalogada:
    """Una entrada del catálogo de normas a cargar."""

    fuente: str                 # identificador estable
    nombre_legible: str          # "Ley 25.188 — Ética Pública"
    url: str                    # URL completa en InfoLEG


# Catálogo curado de normas estructurales del derecho público argentino
# relevantes para legislación en HCDN. Agregar entradas para extender.
CATALOGO_NORMAS: list[NormaCatalogada] = [
    NormaCatalogada(
        fuente="constitucion_nacional",
        nombre_legible="Constitución de la Nación Argentina",
        url=urljoin(INFOLEG_BASE, "0-4999/804/norma.htm"),
    ),
    NormaCatalogada(
        fuente="ley_19549_procedimiento_administrativo",
        nombre_legible="Ley 19.549 — Procedimiento Administrativo Nacional",
        url=urljoin(INFOLEG_BASE, "20000-24999/22363/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_24156_administracion_financiera",
        nombre_legible="Ley 24.156 — Administración Financiera",
        url=urljoin(INFOLEG_BASE, "0-4999/554/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_25188_etica_publica",
        nombre_legible="Ley 25.188 — Ética en el Ejercicio de la Función Pública",
        url=urljoin(INFOLEG_BASE, "60000-64999/60847/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_25326_proteccion_datos_personales",
        nombre_legible="Ley 25.326 — Protección de Datos Personales",
        url=urljoin(INFOLEG_BASE, "60000-64999/64790/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_26485_proteccion_mujeres",
        nombre_legible="Ley 26.485 — Protección Integral contra la Violencia hacia las Mujeres",
        url=urljoin(INFOLEG_BASE, "150000-154999/152155/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_26061_proteccion_ninez",
        nombre_legible="Ley 26.061 — Protección Integral de los Derechos de Niños, Niñas y Adolescentes",
        url=urljoin(INFOLEG_BASE, "110000-114999/110778/norma.htm"),
    ),
    NormaCatalogada(
        fuente="ley_27275_acceso_informacion_publica",
        nombre_legible="Ley 27.275 — Acceso a la Información Pública",
        url=urljoin(INFOLEG_BASE, "265000-269999/265949/norma.htm"),
    ),
    NormaCatalogada(
        fuente="ley_23551_asociaciones_sindicales",
        nombre_legible="Ley 23.551 — Asociaciones Sindicales",
        url=urljoin(INFOLEG_BASE, "20000-24999/20993/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_24522_concursos_quiebras",
        nombre_legible="Ley 24.522 — Concursos y Quiebras",
        url=urljoin(INFOLEG_BASE, "25000-29999/25379/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_26122_regimen_dnu",
        nombre_legible="Ley 26.122 — Régimen Legal de los DNU",
        url=urljoin(INFOLEG_BASE, "115000-119999/117808/norma.htm"),
    ),
    NormaCatalogada(
        fuente="ley_20744_contrato_trabajo",
        nombre_legible="Ley 20.744 — Contrato de Trabajo",
        url=urljoin(INFOLEG_BASE, "25000-29999/25552/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_26529_derechos_paciente",
        nombre_legible="Ley 26.529 — Derechos del Paciente",
        url=urljoin(INFOLEG_BASE, "160000-164999/160432/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_16463_medicamentos",
        nombre_legible="Ley 16.463 — Medicamentos",
        url=urljoin(INFOLEG_BASE, "15000-19999/16613/texact.htm"),
    ),
    NormaCatalogada(
        fuente="ley_26206_educacion_nacional",
        nombre_legible="Ley 26.206 — Educación Nacional",
        url=urljoin(INFOLEG_BASE, "120000-124999/123542/norma.htm"),
    ),
]


# Regex para detectar inicios de artículo en cualquier formato común
# usado en normativa argentina.
ARTICULO_RE = re.compile(
    r"(?im)^\s*("
    r"art[íi]culo\s+\d+[°º]?\s*(?:bis|ter|quater)?\s*[-—.:]?"
    r"|"
    r"art\.\s+\d+[°º]?\s*[-—.:]?"
    r"|"
    r"cap[íi]tulo\s+[ivxlc]+"
    r"|"
    r"t[íi]tulo\s+[ivxlc]+"
    r")",
)


async def descargar_html(url: str, client: httpx.AsyncClient) -> str:
    """Descarga el HTML de una norma de InfoLEG.

    El servidor de InfoLEG responde a veces con Latin-1 sin declarar
    encoding correctamente. Forzamos UTF-8 con fallback Latin-1.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Praxis-Asesor/0.1; contact: agustindm.uba@gmail.com)"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    resp = await client.get(url, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    # InfoLEG declara mal el encoding — probemos UTF-8 y Latin-1.
    raw = resp.content
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parsear_html_a_chunks(
    html: str, fuente: str,
) -> list[NormaChunk]:
    """Toma el HTML crudo de InfoLEG, extrae el texto y lo segmenta
    por artículo.

    InfoLEG sirve el cuerpo dentro de tablas anidadas; nos quedamos
    con el texto plano y partimos por la regex de inicio de artículo.
    """
    soup = BeautifulSoup(html, "lxml")
    # Quitar scripts/styles para no contaminar.
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    texto_plano = soup.get_text("\n", strip=True)
    # Compactar líneas en blanco múltiples.
    texto_plano = re.sub(r"\n\s*\n+", "\n\n", texto_plano)

    # Partir por inicios de artículo manteniendo el separador.
    indices = [m.start() for m in ARTICULO_RE.finditer(texto_plano)]
    if not indices:
        # Norma sin estructura de artículos detectable: devolvemos
        # el texto completo como un único chunk.
        return [
            NormaChunk(
                fuente=fuente,
                articulo_label="Texto completo",
                orden=1,
                texto=texto_plano[:8000],
            ),
        ]

    chunks: list[NormaChunk] = []
    indices.append(len(texto_plano))
    for orden, (inicio, fin) in enumerate(
        zip(indices[:-1], indices[1:], strict=False), start=1,
    ):
        bloque = texto_plano[inicio:fin].strip()
        if not bloque:
            continue
        # Tomar la primera línea como label.
        primera_linea = bloque.split("\n", 1)[0][:120].strip()
        chunks.append(
            NormaChunk(
                fuente=fuente,
                articulo_label=primera_linea,
                orden=orden,
                # Limitamos cada chunk a 3000 chars para que el embed
                # no se sature; suficiente para el artículo medio.
                texto=bloque[:3000],
            ),
        )
    return chunks


async def cargar_norma_completa(
    catalogada: NormaCatalogada, client: httpx.AsyncClient,
) -> list[NormaChunk]:
    """End-to-end: descarga + parsea una norma del catálogo."""
    log.info("Descargando %s desde %s", catalogada.fuente, catalogada.url)
    html = await descargar_html(catalogada.url, client)
    chunks = parsear_html_a_chunks(html, catalogada.fuente)
    log.info(
        "Norma %s → %d chunks", catalogada.fuente, len(chunks),
    )
    return chunks
