"""Parser del PDF del Orden del Día / Temario de HCDN (feat-45).

Patrón observado en el corpus de mayo/junio 2026:

Cabecera (página 1):
    144° PERÍODO ORDINARIO
    MIÉRCOLES 20 DE MAYO 11 HS         ← fecha + hora
    4° REUNIÓN – 4° SESIÓN ESPECIAL    ← tipo de sesión
    TEMARIO AMPLIADO                   ← título del documento

Items (cada uno típicamente abarca 3-6 líneas):
    NNNN-D-AAAA DE LEY. <sumario en mayúsculas>.
    NNNN-D-AAAA DE RESOLUCIÓN. <sumario>.
    NNNN-D-AAAA DE DECLARACIÓN. <sumario>.
    NNNN-D-AAAA DE COMUNICACIÓN. <sumario>.
    COMISION1 / COMISION2 / COMISION3   ← giros

El parser es tolerante: si una línea no matchea, sigue. Si el PDF cambia
de formato, los tests fixtures avisan.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import pdfplumber

log = logging.getLogger(__name__)


# Patrón canónico del N° de expediente HCDN: NNNN-X-AAAA o NNNN-X-AA.
# X es una letra única (D, S, PE, JGM, CD, CS, P, OV, OTRO — feat-1).
_NUM_EXP_RE = re.compile(
    r"(?P<num>\d{4})-(?P<origen>[A-Z]{1,4})-(?P<anio>\d{2,4})"
)

# Tipo del proyecto: viene después del N° con "DE LEY." / "DE RESOLUCIÓN." etc.
_TIPO_RE = re.compile(
    r"\bDE\s+(LEY|RESOLUCI[OÓ]N|DECLARACI[OÓ]N|COMUNICACI[OÓ]N)\b",
    re.IGNORECASE,
)

# Cabecera: fecha. Formato del PDF: "MIÉRCOLES 20 DE MAYO 11 HS".
# Capturamos día numérico + mes en español.
_FECHA_RE = re.compile(
    r"(?:LUNES|MARTES|MI[EÉ]RCOLES|JUEVES|VIERNES|S[ÁA]BADO|DOMINGO)\s+"
    r"(?P<dia>\d{1,2})\s+DE\s+(?P<mes>[A-ZÁÉÍÓÚ]+)(?:\s+DE\s+(?P<anio>\d{4}))?",
    re.IGNORECASE,
)

# Tipo de sesión: "4° SESIÓN ESPECIAL", "1° SESIÓN ORDINARIA", "EXTRAORDINARIA"
_TIPO_SESION_RE = re.compile(
    r"\d+\s*°\s+(?:REUNI[OÓ]N\s*[–-]\s*)?\d+\s*°\s+SESI[OÓ]N\s+"
    r"(ORDINARIA|ESPECIAL|EXTRAORDINARIA|INFORMATIVA)",
    re.IGNORECASE,
)

_MESES_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


@dataclass(frozen=True, slots=True)
class ItemOrdenDelDia:
    """Un item del temario: un expediente que se va a tratar."""

    numero_expediente: str       # "0419-D-2026"
    tipo: str                    # "ley" | "resolucion" | "declaracion" | "comunicacion"
    sumario: str                 # texto del proyecto (sentence-case original del PDF)
    comisiones: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OrdenDelDiaParseado:
    """Snapshot de un temario completo."""

    fecha_sesion: date | None
    tipo_sesion: str | None      # "ordinaria" | "especial" | "extraordinaria" | "informativa"
    items: list[ItemOrdenDelDia] = field(default_factory=list)


def extraer_pdf_base64(html: str) -> bytes:
    """Extrae el PDF del wrapper HTML que devuelve `procesar.html`.

    El portal embebe el PDF en una llamada `abrirPDF("base64...")`. El
    base64 puede contener `\\/` (escape JS) que tenemos que normalizar.
    """
    m = re.search(r'abrirPDF\("([A-Za-z0-9+/=\\]+)"\)', html)
    if not m:
        raise ValueError("No se encontró abrirPDF(...) en el HTML del OD")
    b64 = m.group(1).replace("\\/", "/").replace("\\", "")
    return base64.b64decode(b64)


def parsear_pdf_temario(pdf_bytes: bytes) -> OrdenDelDiaParseado:
    """Parsea el PDF del temario en una entidad estructurada.

    Estrategia: extraer texto de TODAS las páginas, juntarlo y procesar
    línea por línea. Cada item del temario empieza con un N° de
    expediente seguido de `DE <TIPO>.`, y termina cuando aparece otro
    N° o una línea de comisiones (slash-separated).
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto = "\n".join(page.extract_text() or "" for page in pdf.pages)

    fecha = _extraer_fecha(texto)
    tipo_sesion = _extraer_tipo_sesion(texto)
    items = list(_iter_items(texto))
    return OrdenDelDiaParseado(
        fecha_sesion=fecha,
        tipo_sesion=tipo_sesion,
        items=items,
    )


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------


def _extraer_fecha(texto: str) -> date | None:
    m = _FECHA_RE.search(texto)
    if not m:
        return None
    mes_str = m.group("mes").upper().strip()
    mes = _MESES_ES.get(mes_str)
    if mes is None:
        return None
    dia = int(m.group("dia"))
    anio_str = m.group("anio")
    if anio_str:
        anio = int(anio_str)
    else:
        # Si no hay año explícito en la línea, intentar capturar del header
        # "144° PERÍODO ORDINARIO" no trae año. Buscamos cualquier 20XX
        # en los primeros 500 chars (suele aparecer en el aviso "Año de...").
        m_year = re.search(r"\b(20\d{2})\b", texto[:1500])
        anio = int(m_year.group(1)) if m_year else date.today().year
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def _extraer_tipo_sesion(texto: str) -> str | None:
    m = _TIPO_SESION_RE.search(texto)
    if not m:
        return None
    return m.group(1).lower()


def _iter_items(texto: str):
    """Yield ItemOrdenDelDia. Algoritmo:

    Cada item empieza con un N° de expediente al inicio de línea. Tomamos
    todo desde ese N° hasta el próximo N° o EOF, y lo procesamos.
    """
    lineas = texto.splitlines()
    # Localizar índices de línea donde arranca un item (línea que empieza
    # con N° de expediente).
    inicios: list[int] = []
    for i, line in enumerate(lineas):
        stripped = line.lstrip()
        m = _NUM_EXP_RE.match(stripped)
        # Solo es inicio de item si en la MISMA línea aparece "DE <TIPO>".
        if m and _TIPO_RE.search(stripped):
            inicios.append(i)

    for j, start in enumerate(inicios):
        end = inicios[j + 1] if j + 1 < len(inicios) else len(lineas)
        bloque = lineas[start:end]
        item = _parsear_bloque(bloque)
        if item is not None:
            yield item


def _parsear_bloque(lineas: list[str]) -> ItemOrdenDelDia | None:
    if not lineas:
        return None
    primera = lineas[0].strip()
    m_num = _NUM_EXP_RE.search(primera)
    if not m_num:
        return None
    numero = (
        f"{m_num.group('num')}-{m_num.group('origen')}-{m_num.group('anio')}"
    )

    m_tipo = _TIPO_RE.search(primera)
    if not m_tipo:
        return None
    tipo_raw = m_tipo.group(1).upper()
    tipo = _mapear_tipo(tipo_raw)

    # Sumario: desde después de "DE <TIPO>." hasta la primera línea que
    # parece "lista de comisiones" (mayoría mayúscula + slashes), o
    # hasta el final del bloque.
    idx_post_tipo = primera.find(m_tipo.group(0)) + len(m_tipo.group(0))
    resto_primera = primera[idx_post_tipo:].lstrip(". ").strip()
    sumario_partes: list[str] = []
    if resto_primera:
        sumario_partes.append(resto_primera)

    comisiones: list[str] = []
    for ln in lineas[1:]:
        s = ln.strip()
        if not s:
            continue
        if _parece_comisiones(s):
            comisiones = _parsear_comisiones(s)
            break
        sumario_partes.append(s)

    sumario = " ".join(sumario_partes).strip()
    return ItemOrdenDelDia(
        numero_expediente=numero,
        tipo=tipo,
        sumario=sumario,
        comisiones=comisiones,
    )


def _mapear_tipo(tipo_raw: str) -> str:
    """Normaliza el tipo extraído del PDF al value del enum domain."""
    tipo_raw = tipo_raw.replace("Ó", "O").replace("ó", "o").upper()
    if tipo_raw == "LEY":
        return "ley"
    if tipo_raw == "RESOLUCION":
        return "resolucion"
    if tipo_raw == "DECLARACION":
        return "declaracion"
    if tipo_raw == "COMUNICACION":
        return "comunicacion"
    return "ley"


def _parece_comisiones(linea: str) -> bool:
    """Heurística: línea casi toda en mayúsculas, contiene `/` o `,` y NO
    contiene N° de expediente."""
    if _NUM_EXP_RE.search(linea):
        return False
    if "/" not in linea and "," not in linea:
        return False
    # Mínimo 60% caracteres alfabéticos en mayúsculas.
    alpha = [c for c in linea if c.isalpha()]
    if not alpha:
        return False
    upper = sum(1 for c in alpha if c.isupper())
    return (upper / len(alpha)) > 0.6


def _parsear_comisiones(linea: str) -> list[str]:
    raw = re.split(r"[/,]", linea)
    out: list[str] = []
    for c in raw:
        c2 = c.strip().rstrip(".")
        if c2 and len(c2) > 2:
            out.append(c2)
    return out
