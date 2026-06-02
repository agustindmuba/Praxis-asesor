"""Parser del PDF del Boletín Oficial — Primera y Cuarta sección.

El PDF tiene un **SUMARIO** en las primeras páginas que lista todas las
normas con esta estructura:

    SUMARIO
    Avisos Nuevos
    Decretos
    MINISTERIO X. Decreto 412/2026. DECTO-2026-412-APN-PTE - Sumario. ......... 4
    PROCEDIMIENTOS ADMINISTRATIVOS. Decreto 417/2026. DECTO-2026-417-... ...... 4
    Resoluciones
    MINISTERIO X. Resolución 19/2026. RESFC-2026-19-E-... .................... 15
    ...

Parseamos el sumario para obtener metadata de cada norma + la página
donde empieza. Para el texto completo, extraemos las páginas en el rango
`[inicio, inicio_siguiente_norma - 1]`.

Patrones de cada línea del sumario:

    <ORGANISMO>. <Tipo> <Numero>. <ID-INTERNO> - <SumarioCorto>. <dots> <pagina>
    <ORGANISMO>. <Tipo> <Numero>. <ID-INTERNO>. <dots> <pagina>          (sin sumario corto)

`<Tipo>` ∈ {Decreto, Resolución, Decisión Administrativa, Ley,
Disposición, ...}. `<Numero>` típicamente `NNNN/AAAA`.

El parser es **defensivo**: si una línea no matchea, la salta y loguea
warning. Acumula todo lo que matche.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from pdfplumber.pdf import PDF

from praxis.domain import NormaBO, NormaBOTexto, SeccionBO, hash_sumario

log = logging.getLogger(__name__)


# Tipos de norma esperados, en orden de probabilidad. El regex usa esta
# lista como alternancia.
TIPOS_NORMA = (
    "Decreto",
    "Resolución",
    "Resoluci",                # acentos rotos por extract_text
    "Decisión Administrativa",
    "Decisi",
    "Ley",
    "Disposición",
    "Disposici",
    "Comunicación",
    "Acordada",
    "Acuerdo",
    "Aviso",
)


# Regex de una línea del sumario.
#
# Estructura:
#   <ORGANISMO>. <Tipo> <Numero>. <ID-INTERNO>[ - <Sumario>]. <dots> <pagina>
#
# Notas:
# - ORGANISMO es UPPERCASE, puede contener punto interno (ej. "MINISTERIO
#   DE ECONOMÍA. SECRETARÍA DE INDUSTRIA"), así que aceptamos el último
#   "." antes del tipo como el separador real. Implementamos como greedy
#   match seguido del marcador `\. (TIPO) NUMERO\.`.
# - Numero formato `NNNN/AAAA`. Aceptamos también `NNN.NNN` para casos
#   tipo "Ley 27.812" donde el número usa punto.
# - Sumario opcional, separado por `" - "` después del ID-INTERNO.
# - Cierra con secuencia de puntos (".......") + página.
_TIPOS_RE = "|".join(re.escape(t) for t in TIPOS_NORMA)
_LINEA_SUMARIO_RE = re.compile(
    rf"""
    ^(?P<organismo>.+?)\.                       # organismo (greedy)
    \s+(?P<tipo>{_TIPOS_RE})                    # tipo de norma
    \s+(?P<numero>[\d.]+/\d{{4}}|\d+\.\d+)      # NNNN/AAAA o NN.NNN
    \.\s+
    (?P<resto>.+?)                              # ID interno + sumario opt
    \s*\.+\s*
    (?P<pagina>\d+)\s*$                         # página al final
    """,
    re.VERBOSE,
)

# Header de sección dentro del sumario.
_HEADERS_SECCION = {
    "Decretos",
    "Resoluciones",
    "Decisiones Administrativas",
    "Leyes",
    "Disposiciones",
    "Comunicaciones",
    "Acordadas",
    "Acuerdos",
    "Avisos",
}


@dataclass(frozen=True, slots=True)
class SumarioEntry:
    """Una entrada del SUMARIO del BO, extraída del índice."""

    organismo: str
    tipo: str
    numero: str
    sumario_corto: str            # puede ser "" si la norma no lo tiene
    id_interno: str               # ej. "DECTO-2026-412-APN-PTE"
    pagina_inicio: int


def parsear_sumario(pdf: PDF, max_paginas_indice: int = 8) -> list[SumarioEntry]:
    """Parsea el SUMARIO del BO y devuelve entradas con metadata.

    El SUMARIO empieza en la página 2 típicamente. Leemos las primeras
    `max_paginas_indice` páginas buscando líneas que matcheen
    `_LINEA_SUMARIO_RE`.

    No asumimos dónde termina el sumario — paramos de matchear al
    encontrar líneas que no son del índice (el cuerpo del BO empieza
    después con otro formato).
    """
    entradas: list[SumarioEntry] = []
    paginas_a_leer = min(max_paginas_indice, len(pdf.pages))

    for nro_pagina in range(paginas_a_leer):
        texto = pdf.pages[nro_pagina].extract_text() or ""
        # Las líneas largas del sumario pueden romperse en varias líneas
        # de texto. Detectamos eso uniendo líneas que no terminan con
        # un número de página + secuencia de puntos.
        lineas = _unir_lineas_partidas(texto.splitlines())

        for linea in lineas:
            entry = _parsear_linea(linea)
            if entry is not None:
                entradas.append(entry)

    return entradas


def _unir_lineas_partidas(lineas: list[str]) -> list[str]:
    """Una línea del sumario que se rompe en 2 visualmente en el PDF
    queda como 2 líneas separadas en extract_text(). Las reunimos.

    Una entrada típica del SUMARIO termina con "...... <NNN>". Si una
    línea no termina así, la siguiente es continuación SIEMPRE Y CUANDO
    no sea un header de sección (Decretos, Resoluciones, etc.) ni
    empiece con boilerplate del BO.
    """
    resultado: list[str] = []
    buffer = ""
    for raw in lineas:
        linea = raw.strip()
        if not linea:
            # Línea vacía: cierra el buffer pendiente.
            if buffer:
                resultado.append(buffer)
                buffer = ""
            continue

        # Header de sección: cierra el buffer pendiente y agrega el
        # header solo. NUNCA se une con la siguiente línea (importante
        # para que el organismo de la primera entrada de la sección
        # quede limpio).
        if linea in _HEADERS_SECCION:
            if buffer:
                resultado.append(buffer)
                buffer = ""
            resultado.append(linea)
            continue

        # Boilerplate del BO: descartar.
        if linea.startswith(("BOLETÍN OFICIAL", "BOLET", "SUMARIO",
                             "Avisos Nuevos", "Avisos Anteriores")):
            if buffer:
                resultado.append(buffer)
                buffer = ""
            continue

        buffer = buffer + " " + linea if buffer else linea

        # Si buffer termina con "..... NNN", está completo.
        if re.search(r"\.+\s*\d+\s*$", buffer):
            resultado.append(buffer)
            buffer = ""

    if buffer:
        resultado.append(buffer)
    return resultado


def _parsear_linea(linea: str) -> SumarioEntry | None:
    """Parsea una línea del sumario. Devuelve None si no matchea."""
    # Saltar headers de sección y líneas de boilerplate.
    if linea.strip() in _HEADERS_SECCION:
        return None
    if linea.startswith(("BOLETÍN OFICIAL", "BOLET")):
        return None

    m = _LINEA_SUMARIO_RE.match(linea)
    if m is None:
        return None

    organismo = m.group("organismo").strip()
    tipo_raw = m.group("tipo")
    numero = m.group("numero").strip()
    resto = m.group("resto").strip().rstrip(".")
    pagina = int(m.group("pagina"))

    # Normalizar tipo (los acentos rotos de extract_text los compensamos).
    tipo = _normalizar_tipo(tipo_raw)

    # `resto` viene como "ID-INTERNO - Sumario" o solo "ID-INTERNO".
    id_interno, sumario_corto = _split_id_y_sumario(resto)

    return SumarioEntry(
        organismo=organismo,
        tipo=tipo,
        numero=numero,
        sumario_corto=sumario_corto,
        id_interno=id_interno,
        pagina_inicio=pagina,
    )


def _normalizar_tipo(tipo: str) -> str:
    """`Resoluci` (con acento perdido) → `Resolución`. Similar para otros."""
    return {
        "Resoluci": "Resolución",
        "Decisi": "Decisión Administrativa",
        "Disposici": "Disposición",
    }.get(tipo, tipo)


def _split_id_y_sumario(resto: str) -> tuple[str, str]:
    """Split por ` - ` (con espacios) — convención del BO para separar
    el ID interno del sumario corto.

    Si no hay separador, todo es `id_interno` y `sumario_corto = ""`.
    """
    if " - " in resto:
        id_interno, _, sumario = resto.partition(" - ")
        return id_interno.strip(), sumario.strip()
    return resto.strip(), ""


# ---------------------------------------------------------------------------
# Conversión a dominio
# ---------------------------------------------------------------------------


def extraer_normas_bo(
    pdf: PDF,
    *,
    fecha_publicacion: date,
    seccion: SeccionBO,
    base_url_oficial: str = "https://www.boletinoficial.gob.ar",
    capturado_en: datetime | None = None,
) -> tuple[list[NormaBO], list[NormaBOTexto]]:
    """Extrae normas + textos del PDF. Devuelve ambas listas alineadas
    por orden (cada `NormaBO[i]` corresponde al `NormaBOTexto[i]`).

    Para el texto: concatenamos las páginas desde la página de inicio de
    la norma hasta una página antes de la siguiente entrada. Para la
    última, hasta el final del PDF.

    El `id` de `NormaBO` queda en None — lo asigna el repo al persistir.
    El `norma_id` de `NormaBOTexto` queda como `UUID(0...0)` placeholder
    porque el caller lo rellena después con el id devuelto por el repo
    de NormaBO. (Patrón usado en otros repos del proyecto.)
    """
    from uuid import UUID

    capturado = capturado_en or datetime.now(UTC)
    entradas = parsear_sumario(pdf)

    normas: list[NormaBO] = []
    textos: list[NormaBOTexto] = []
    placeholder_uuid = UUID(int=0)

    for i, entry in enumerate(entradas):
        # Determinar el rango de páginas del cuerpo: [inicio, next_inicio).
        page_idx_inicio = entry.pagina_inicio - 1   # PDF 0-indexed
        if i + 1 < len(entradas):
            page_idx_fin = entradas[i + 1].pagina_inicio - 1
        else:
            page_idx_fin = len(pdf.pages)
        # Clamp por seguridad.
        page_idx_inicio = max(0, min(page_idx_inicio, len(pdf.pages) - 1))
        page_idx_fin = max(page_idx_inicio + 1, min(page_idx_fin, len(pdf.pages)))

        texto_cuerpo_partes = []
        for idx in range(page_idx_inicio, page_idx_fin):
            t = pdf.pages[idx].extract_text() or ""
            if t.strip():
                texto_cuerpo_partes.append(t)
        texto_cuerpo = "\n".join(texto_cuerpo_partes).strip()
        if not texto_cuerpo:
            # Si no hubo texto extraíble, usamos el sumario corto como
            # placeholder para no violar invariante de NormaBOTexto.
            texto_cuerpo = entry.sumario_corto or entry.id_interno or "(sin texto)"

        # Sumario del NormaBO: usamos el sumario corto si lo hay; si no,
        # el organismo + id_interno como fallback.
        sumario = entry.sumario_corto or (
            f"{entry.organismo} — {entry.id_interno}"
        )

        normas.append(
            NormaBO(
                id=None,
                fecha_publicacion=fecha_publicacion,
                seccion=seccion,
                tipo_norma=entry.tipo,
                numero_norma=entry.numero,
                organismo_emisor=entry.organismo,
                sumario=sumario,
                url_oficial=base_url_oficial,
                hash_sumario=hash_sumario(sumario),
                capturado_en=capturado,
            )
        )
        textos.append(
            NormaBOTexto(
                norma_id=placeholder_uuid,
                texto=texto_cuerpo,
                capturado_en=capturado,
            )
        )

    return normas, textos
