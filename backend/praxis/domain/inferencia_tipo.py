"""Inferencia de `TipoExpediente` desde el título/sumario (feat-43.1.3).

El parser de feat-1 solo detectaba "declaraci/resoluci/comunicaci" en los
primeros 80 chars del texto. Pero los expedientes reales del portal HCDN
suelen empezar con verbos imperativos ("EXPRESAR", "DECLARAR DE INTERÉS",
"PEDIDO DE INFORMES", etc.) que NO matchean esa heurística, y todo cae a
PROYECTO_LEY por default.

Resultado en la DB: 435/443 expedientes como `proyecto_ley` aunque la
mayoría sean declaraciones o resoluciones. Este módulo aplica una
heurística más rica basada en los verbos típicos.

Pruebas con el corpus actual (Diputados 2026): los 8 títulos del primer
screenshot de Agustín se reclasifican correctamente.
"""

from __future__ import annotations

import re

from praxis.domain.value_objects import Camara, OrigenExpediente, TipoExpediente


# Patrones por tipo. Orden importante: el primer match gana.
# Compilados al import para velocidad.
_PATRONES: list[tuple[re.Pattern[str], TipoExpediente]] = [
    # --- DECLARACIONES (la cámara expresa voluntad/posición) ---
    # "EXPRESAR BENEPLÁCITO", "EXPRESAR REPUDIO", "EXPRESAR PREOCUPACIÓN"
    (re.compile(r"\bexpresar\b.*?(beneplacito|repudio|preocupacion|adhesion|pesar|reconocimiento|homenaje|solidaridad)"), TipoExpediente.PROYECTO_DECLARACION),
    # "DECLARAR DE INTERÉS de la H. Cámara"
    (re.compile(r"\bdeclarar\b.*?(de interes|personalidad destacada|huesped|visitante ilustre)"), TipoExpediente.PROYECTO_DECLARACION),
    # "REPUDIAR" / "MANIFESTAR PREOCUPACIÓN" / "MANIFESTAR ADHESIÓN"
    (re.compile(r"\b(repudiar|conmemorar|rendir homenaje|manifestar (preocupacion|adhesion|solidaridad|repudio))\b"), TipoExpediente.PROYECTO_DECLARACION),
    # "DECLARACIÓN" como palabra explícita al inicio
    (re.compile(r"\bproyecto de declaracion\b"), TipoExpediente.PROYECTO_DECLARACION),

    # --- COMUNICACIONES (pedido formal al PEN) ---
    # "PEDIDO DE INFORMES AL PODER EJECUTIVO" — en HCDN es Resolución,
    # en HSN se llama Comunicación. Acá optamos por COMUNICACION por
    # default; el caller (`inferir_tipo_desde_titulo`) puede ajustar
    # según cámara.
    (re.compile(r"\bpedido de informes?\b"), TipoExpediente.PROYECTO_COMUNICACION),
    (re.compile(r"\b(solicitar|requerir|pedir).*?(al poder ejecutivo|al pen|al ministerio|al jefe de gabinete)\b.*?(informe|inform[ea])"), TipoExpediente.PROYECTO_COMUNICACION),
    (re.compile(r"\bproyecto de comunicacion\b"), TipoExpediente.PROYECTO_COMUNICACION),

    # --- RESOLUCIONES (decisión interna de la cámara) ---
    # "CITAR" / "INTERPELAR" un ministro o jefe de gabinete → Resolución
    (re.compile(r"\b(citar|interpelar|convocar).*?(ministr|secretari|funcionari|jefe de gabinete)"), TipoExpediente.PROYECTO_RESOLUCION),
    # "INTERPELAR" suelto (sin objeto) también es resolución
    (re.compile(r"\binterpelar\b"), TipoExpediente.PROYECTO_RESOLUCION),
    # "CREAR UNA COMISIÓN ESPECIAL" / "DESIGNAR" en función interna
    (re.compile(r"\b(crear|constituir).*?(comision especial|comision investigadora|comision bicameral)"), TipoExpediente.PROYECTO_RESOLUCION),
    (re.compile(r"\bproyecto de resolucion\b"), TipoExpediente.PROYECTO_RESOLUCION),

    # --- LEYES (regulación general) ---
    # "PROYECTO DE LEY", "MODIFICASE LA LEY...", "CREASE EL...", "ESTABLECESE..."
    (re.compile(r"\bproyecto de ley\b"), TipoExpediente.PROYECTO_LEY),
    (re.compile(r"\b(creas?e|establec[ea]s?e|modificas?e|sustituyese|derogase|incorporase).*?(ley\s*(n|nro|n°|numero|nº)?|articulo|codigo)"), TipoExpediente.PROYECTO_LEY),

    # --- MENSAJE PE ---
    (re.compile(r"\bmensaje\b.*?(del poder ejecutivo|n[°º]?\s*\d)"), TipoExpediente.MENSAJE_PE),

    # --- DECRETOS ---
    (re.compile(r"\bdecreto\b\s*(de necesidad|n[°º]?\s*\d)"), TipoExpediente.DECRETO),
]


def inferir_tipo_desde_titulo(
    titulo: str,
    *,
    sumario: str = "",
    origen: OrigenExpediente | None = None,
    camara: Camara | None = None,
) -> TipoExpediente:
    """Infiere el tipo a partir del título (+ sumario opcional).

    Prioridad: regex específicos > heurística por origen > fallback LEY.

    Ajustes por cámara:
    - "PEDIDO DE INFORMES" matchea como COMUNICACION por default. En HCDN
      el reglamento define "Pedido de Informes" como Resolución; en HSN
      como Comunicación. Si la cámara es HCDN, lo movemos a RESOLUCION.
    """
    texto = _normalizar(f"{titulo} {sumario}")

    # Pase 1: regex específicos.
    for patron, tipo in _PATRONES:
        if patron.search(texto):
            # Override: pedido de informes en HCDN es Resolución.
            if (
                tipo == TipoExpediente.PROYECTO_COMUNICACION
                and "pedido de informes" in texto
                and camara == Camara.HCDN
            ):
                return TipoExpediente.PROYECTO_RESOLUCION
            return tipo

    # Pase 2: heurística por origen (caso PE/JGM ambiguo).
    if origen in (OrigenExpediente.EJECUTIVO, OrigenExpediente.JEFATURA_GABINETE):
        if "mensaje" in texto:
            return TipoExpediente.MENSAJE_PE
        if "proyecto de ley" in texto or "proyecto de" in texto:
            return TipoExpediente.PROYECTO_LEY
        return TipoExpediente.MENSAJE_PE  # default conservador

    # Pase 3: fallback LEY (cubre la mayoría de iniciativas de diputados).
    return TipoExpediente.PROYECTO_LEY


def _normalizar(s: str) -> str:
    """Lowercase + saca tildes ASCII básicas para matching más laxo."""
    out = s.lower()
    table = str.maketrans("áéíóúüñ", "aeiouun")
    return out.translate(table)
