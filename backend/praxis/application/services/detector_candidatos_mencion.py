"""Detector de candidatos a mención de un legislador en un texto.

Pase 1 del flujo de detección de menciones (D6 spec 16 + ADR 0009):

- **Regex** sobre el texto del artículo para encontrar candidatos.
- Cada candidato tiene un `snippet_contexto` de ≤200 chars alrededor
  del match.
- El caso de uso (feat-40.3) toma estos candidatos y los pasa al LLM
  para confirmar que es ESE legislador (no homónimo) y clasificar tono.

Estrategia regex:

1. **Nombre completo** (ej. "Pablo Juliano") matcheado como palabra
   completa. Mayor confianza.
2. **Apellido + contexto político** dentro de N caracteres: el
   apellido aparece cerca de palabras como "diputado", "legislador",
   "bloque", "diputada", "@<alias>". Distingue a "Juliano" político
   de personas/marcas con apellido homónimo.

Heurísticas:

- Match case-insensitive con normalización (saca tildes ASCII).
- Sliding window de 200 chars centrada en el match.
- Dedup por posición + alias.

Este módulo NO necesita LLM ni I/O. Es función pura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Palabras que indican "contexto político" alrededor de un apellido.
# Si el apellido aparece cerca de alguna, gana confianza de match.
CONTEXTO_POLITICO = (
    "diputado", "diputada", "diputados",
    "senador", "senadora", "senadores",
    "legislador", "legisladora", "legisladores",
    "bloque", "partido", "interbloque",
    "congreso", "camara", "cámara",
    "asesor", "asesora",
)

# Tamaño del snippet (chars). Se acota a MAX_SNIPPET_CONTEXTO_CHARS del
# dominio (200) al construir Mencion en el caso de uso.
_SNIPPET_HALF_WINDOW = 100

# Ventana en caracteres para "apellido cerca de contexto político".
_PROXIMIDAD_CONTEXTO_CHARS = 80


@dataclass(frozen=True, slots=True)
class CandidatoMencion:
    """Un candidato a mención encontrado por regex.

    `alias_matcheado`: el alias del legislador que el regex matcheó
    (nombre completo o apellido).
    `snippet`: ventana de texto alrededor del match (recortada a ~200
    chars). El caso de uso pasa esto al LLM como contexto para
    confirmar + tono.
    `confianza_regex`: heurística de qué tan confiable es el match
    pre-LLM. 1.0 si fue match nombre completo, 0.7 si fue apellido +
    contexto, 0.4 si fue apellido suelto sin contexto.
    """

    alias_matcheado: str
    snippet: str
    confianza_regex: float
    posicion_inicio: int


def _normalizar(s: str) -> str:
    """Lowercase + saca tildes ASCII para matching tolerante a
    encoding del medio."""
    out = s.lower()
    return out.translate(str.maketrans("áéíóúüñ", "aeiouun"))


def _construir_pattern_alias(alias: str) -> re.Pattern[str]:
    """Pattern case-insensitive con word boundaries para un alias.

    `alias` se pasa tal cual; aceptamos espacios y caracteres
    no-alfanuméricos (ej. "@PJuliano"). Escapamos regex chars.

    `\\b` exige transición word↔non-word. Si el alias empieza/termina
    con un char non-word (ej. "@PJuliano"), `\\b` ahí falla porque el
    char anterior (espacio) también es non-word. Por eso, sólo
    aplicamos `\\b` cuando el extremo es un word char.
    """
    escaped = re.escape(alias)
    prefijo = r"\b" if alias and alias[0].isalnum() else ""
    sufijo = r"\b" if alias and alias[-1].isalnum() else ""
    return re.compile(rf"{prefijo}{escaped}{sufijo}", re.IGNORECASE)


def detectar_candidatos(
    texto: str,
    *,
    nombre_completo: str,
    apellido: str,
    aliases_extra: list[str] | None = None,
) -> list[CandidatoMencion]:
    """Encuentra candidatos a mención del legislador en el texto.

    Args:
        texto: cuerpo del artículo (no se persiste — ADR 0006).
        nombre_completo: ej. "Pablo Juliano".
        apellido: ej. "Juliano".
        aliases_extra: alias adicionales del perfil del despacho
            (ej. "@PJuliano", apodos).

    Returns:
        Lista de candidatos sin duplicar por posición. Ordenada por
        posición creciente. El caso de uso (feat-40.3) los pasa al LLM
        para confirmación + tono.
    """
    if not texto or not nombre_completo or not apellido:
        return []

    texto_norm = _normalizar(texto)
    candidatos: list[CandidatoMencion] = []
    # Rangos (start, end) ya cubiertos. Si un nuevo match cae adentro
    # de un rango, lo deduplicamos (caso típico: el apellido dentro
    # del nombre completo).
    rangos_vistos: list[tuple[int, int]] = []

    def _ya_visto(start: int, end: int) -> bool:
        return any(rs <= start and end <= re_ for rs, re_ in rangos_vistos)

    # 1. Match nombre completo (mayor confianza).
    pat_completo = _construir_pattern_alias(_normalizar(nombre_completo))
    for m in pat_completo.finditer(texto_norm):
        if _ya_visto(m.start(), m.end()):
            continue
        snippet = _extraer_snippet(texto, m.start(), m.end())
        candidatos.append(
            CandidatoMencion(
                alias_matcheado=nombre_completo,
                snippet=snippet,
                confianza_regex=1.0,
                posicion_inicio=m.start(),
            ),
        )
        rangos_vistos.append((m.start(), m.end()))

    # 2. Aliases extra (Twitter handles, apodos). Confianza 0.9.
    for alias in aliases_extra or []:
        if not alias.strip() or alias.lower() == nombre_completo.lower():
            continue
        pat = _construir_pattern_alias(_normalizar(alias))
        for m in pat.finditer(texto_norm):
            if _ya_visto(m.start(), m.end()):
                continue
            snippet = _extraer_snippet(texto, m.start(), m.end())
            candidatos.append(
                CandidatoMencion(
                    alias_matcheado=alias,
                    snippet=snippet,
                    confianza_regex=0.9,
                    posicion_inicio=m.start(),
                ),
            )
            rangos_vistos.append((m.start(), m.end()))

    # 3. Apellido + contexto político cercano.
    pat_apellido = _construir_pattern_alias(_normalizar(apellido))
    for m in pat_apellido.finditer(texto_norm):
        if _ya_visto(m.start(), m.end()):
            continue
        # Apellido suelto sin contexto → 0.4. El LLM lo descarta si es
        # homónimo. Con contexto político cercano → 0.7.
        confianza = (
            0.7
            if _hay_contexto_politico_cerca(texto_norm, m.start(), m.end())
            else 0.4
        )
        snippet = _extraer_snippet(texto, m.start(), m.end())
        candidatos.append(
            CandidatoMencion(
                alias_matcheado=apellido,
                snippet=snippet,
                confianza_regex=confianza,
                posicion_inicio=m.start(),
            ),
        )
        rangos_vistos.append((m.start(), m.end()))

    candidatos.sort(key=lambda c: c.posicion_inicio)
    return candidatos


def _extraer_snippet(texto: str, start: int, end: int) -> str:
    """Snippet de ~200 chars centrado en el match. Lo recortamos en
    word boundaries si caben para no cortar palabras a la mitad.

    El caller (caso de uso) reaplica el cap a MAX_SNIPPET_CONTEXTO_CHARS
    al construir Mencion.
    """
    centro = (start + end) // 2
    desde = max(0, centro - _SNIPPET_HALF_WINDOW)
    hasta = min(len(texto), centro + _SNIPPET_HALF_WINDOW)

    snippet = texto[desde:hasta].strip()
    # Si recortamos a la mitad, agregamos elipsis para señalarlo.
    prefix = "…" if desde > 0 else ""
    suffix = "…" if hasta < len(texto) else ""
    return f"{prefix}{snippet}{suffix}"


def _hay_contexto_politico_cerca(
    texto_norm: str, match_start: int, match_end: int,
) -> bool:
    """True si alguna palabra de CONTEXTO_POLITICO aparece dentro de
    `_PROXIMIDAD_CONTEXTO_CHARS` antes o después del match."""
    desde = max(0, match_start - _PROXIMIDAD_CONTEXTO_CHARS)
    hasta = min(len(texto_norm), match_end + _PROXIMIDAD_CONTEXTO_CHARS)
    ventana = texto_norm[desde:hasta]
    return any(palabra in ventana for palabra in CONTEXTO_POLITICO)
