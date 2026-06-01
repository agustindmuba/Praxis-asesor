"""Value objects + helpers puros para los algoritmos del briefing.

Spec 14 §"Algoritmos · Cofirmantes naturales" y §"Antecedente más parecido".

Sin I/O. Las funciones son determinísticas y sirven para los use cases
`SugerirCofirmantes` y `BuscarAntecedenteParecido` que viven en la capa
application.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praxis.domain.value_objects import EstadoExpediente, NumeroExpediente

# ---------------------------------------------------------------------------
# Value objects de salida
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CofirmanteSugerido:
    """Un legislador que podría sumar firma a un proyecto del despacho.

    Frozen. Es el resultado de `SugerirCofirmantes`. Su `razon` es texto
    legible para mostrar en el PDF del briefing.
    """

    nombre: str
    bloque: str | None
    distrito: str | None
    proyectos_similares_firmados: int
    razon: str


@dataclass(frozen=True, slots=True)
class AntecedenteParecido:
    """Un expediente histórico similar al del despacho, con su resultado.

    Es el resultado de `BuscarAntecedenteParecido`. Solo lo devuelve el
    use case si la similitud (Jaccard sobre tokens del título) supera
    `JACCARD_UMBRAL`.
    """

    numero: NumeroExpediente
    titulo: str
    estado_terminal: EstadoExpediente
    similitud: float                # 0..1, Jaccard sobre tokens del título


# ---------------------------------------------------------------------------
# Similaridad pura
# ---------------------------------------------------------------------------


# Umbral mínimo para considerar que un expediente histórico es "antecedente
# parecido". Bajo deliberadamente — preferimos algún antecedente débil a
# devolver `None` sistemáticamente.
JACCARD_UMBRAL = 0.20


# Stopwords muy comunes en títulos parlamentarios. Sacarlas mejora la
# señal de similitud (sino todos los proyectos "matchean" porque comparten
# "MODIFICACION" o "REGIMEN").
_STOPWORDS_TITULO: frozenset[str] = frozenset(
    {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "y",
        "o",
        "a",
        "en",
        "para",
        "por",
        "su",
        "se",
        "que",
        "sobre",
        "con",
        "sin",
        "al",
        "lo",
        "ser",
        "esta",
        "este",
        "estos",
        "estas",
        # frecuentes en títulos del portal
        "ley",
        "leyes",
        "proyecto",
        "modificacion",
        "modificaciones",
        "creacion",
        "establecese",
        "establece",
        "regimen",
        "general",
        "particular",
        "art",
        "articulo",
        "nro",
        "numero",
        "nacional",
        "nacionales",
        "republica",
        "argentina",
        "argentino",
        "argentinos",
    }
)


def tokenizar_titulo(texto: str) -> set[str]:
    """Normaliza + tokeniza un título para comparación.

    Pasos:
    1. lowercase
    2. saca tildes ASCII básicas (mismo mapeo que el clasificador)
    3. saca puntuación
    4. split en palabras
    5. saca stopwords + palabras muy cortas (<4 chars, salvo años)

    Devuelve un set para que la comparación sea Jaccard directo.
    """
    s = texto.lower()
    s = s.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = s.split()
    out: set[str] = set()
    for tok in tokens:
        if tok in _STOPWORDS_TITULO:
            continue
        # Mantenemos años (4 dígitos) aunque sean cortos.
        if len(tok) < 4 and not tok.isdigit():
            continue
        out.add(tok)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    """Similitud de Jaccard entre dos sets de tokens. 0..1."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union
