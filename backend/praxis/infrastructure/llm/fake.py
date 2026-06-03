"""FakeLlmProvider — sin red, sin costo.

Genera un resumen ejecutivo plausible usando solo los datos que ya están
en el `Expediente`. Sirve para que el usuario vea cómo va a quedar la
feature antes de enchufar la API real.

Estrategia:
- "Qué propone" → reformula título + sumario.
- "Quién lo impulsa" → primer firmante + bloque/distrito.
- "Probabilidad de avance" → mapeo del estado actual (+ flag de caducidad
  inminente si vence en < 60 días).
"""

from __future__ import annotations

import re
from datetime import date

from praxis.application.ports import LlmProvider
from praxis.domain import (
    AreaTematica,
    ClasificacionNormaBOResult,
    DisambiguacionMencion,
    EstadoExpediente,
    Expediente,
    Firmante,
    Legislador,
    NormaBO,
    TonoMencion,
)

FAKE_MODEL_NAME = "fake-keywords"


class FakeLlmProvider(LlmProvider):
    """Provider sin red. Devuelve markdown con 3 bullets."""

    @property
    def nombre_modelo(self) -> str:
        return FAKE_MODEL_NAME

    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str:
        que_propone = _qué_propone(expediente)
        quien = _quien_lo_impulsa(expediente)
        avance = _probabilidad_de_avance(expediente)

        return (
            f"**Qué propone:** {que_propone}\n\n"
            f"**Quién lo impulsa:** {quien}\n\n"
            f"**Probabilidad de avance:** {avance}"
        )

    async def clasificar_area_tematica(self, expediente: Expediente) -> AreaTematica:
        """Clasifica con keywords sobre título + sumario.

        Estrategia: recorre los buckets de keywords en orden (educación
        antes que economía, etc.) y devuelve el primer match. Si nada
        matchea → `OTROS`.

        Es intencionalmente conservadora: si dos áreas matchean, gana la
        que aparece primero en `_AREA_KEYWORDS`. Las áreas más específicas
        (salud, educación) se ponen antes que las más amplias (economía).
        """
        haystack = _normalizar(
            f"{expediente.titulo} {expediente.sumario or ''}"
        )
        for area, palabras in _AREA_KEYWORDS:
            for palabra in palabras:
                if palabra in haystack:
                    return area
        return AreaTematica.OTROS

    async def generar_argumentos(
        self,
        expediente: Expediente,
        *,
        contraargumentos: bool = False,
    ) -> list[str]:
        """Genera 3 bullets fake para alimentar el briefing.

        No consulta APIs externas. Compone texto plausible usando título,
        firmantes y estado del expediente. Sirve para que la UI tenga
        contenido vendible mientras esperamos enchufar Sonnet real.
        """
        if contraargumentos:
            return _contraargumentos_fake(expediente)
        return _argumentos_fake(expediente)

    async def clasificar_norma_bo(
        self,
        norma: NormaBO,
        *,
        texto: str | None = None,
    ) -> ClasificacionNormaBOResult:
        """Clasifica una norma BO usando keywords sobre sumario +
        organismo + texto (si está).

        Estrategia:
        - Area temática: reusa el mismo bucket de keywords del clasificador
          de expedientes (`_AREA_KEYWORDS`); el mejor match gana.
        - Palabras clave: las que matchearon en la búsqueda + términos
          característicos del organismo.
        - `afecta_expedientes_hcdn`: heurística — True si el texto
          contiene "Ley NNN" o "Expediente NNN-X-YYYY".
        - Referencias legales: regex de "Ley NNNNN" y "Decreto NNNN/AAAA".
        """
        haystack = _normalizar(
            f"{norma.sumario} {norma.organismo_emisor} {texto or ''}"
        )
        area = AreaTematica.OTROS
        palabras_match: list[str] = []
        for cand_area, palabras in _AREA_KEYWORDS:
            for palabra in palabras:
                if palabra in haystack:
                    if area == AreaTematica.OTROS:
                        # Primer match define el área.
                        area = cand_area
                    if cand_area == area:
                        palabras_match.append(palabra)
        # Dedup conservando orden.
        palabras_clave: list[str] = []
        for p in palabras_match:
            if p not in palabras_clave:
                palabras_clave.append(p)
            if len(palabras_clave) >= 5:
                break

        referencias = _detectar_referencias_legales(
            f"{norma.sumario} {texto or ''}"
        )
        afecta_hcdn = bool(referencias) or "expediente" in haystack

        return ClasificacionNormaBOResult(
            area_tematica=area,
            palabras_clave=palabras_clave,
            afecta_expedientes_hcdn=afecta_hcdn,
            referencias_legales=referencias,
        )

    async def disambiguar_mencion(
        self,
        *,
        legislador: Legislador,
        alias_matcheado: str,
        snippet: str,
        titulo_articulo: str,
    ) -> DisambiguacionMencion:
        """Heurística sin LLM:

        - `es_el_legislador`: True si el snippet/titulo contiene
          señales políticas (bloque del legislador, distrito, palabra
          'diputado'/'senador'), O si el match fue por nombre completo
          (más fuerte que apellido). False si el contexto sugiere otra
          cosa (ej. "S.A.", "empresa", "futbolista").
        - `tono`: keywords positivas vs negativas en el snippet. Sin
          señal → neutro.
        - `confianza_tono`: 0.8 si hay match claro de keywords, 0.5
          si es neutro por falta de señal.
        - `razon`: explicación corta.
        """
        haystack = _normalizar(f"{titulo_articulo} {snippet}")
        alias_norm = _normalizar(alias_matcheado)
        nombre_completo_norm = _normalizar(
            f"{legislador.nombre} {legislador.apellido}"
        )

        # Heurística de identidad.
        coincide_nombre_completo = alias_norm == nombre_completo_norm
        senales_negativas_identidad = (
            " s.a." in haystack
            or " sa " in haystack
            or "empresa" in haystack
            or "futbolista" in haystack
            or "actor" in haystack
            or "cantante" in haystack
        )
        senales_politicas = (
            "diputad" in haystack
            or "senador" in haystack
            or "legislad" in haystack
            or "bloque" in haystack
            or "congreso" in haystack
            or _normalizar(legislador.bloque.nombre) in haystack
            or _normalizar(legislador.distrito) in haystack
        )
        if coincide_nombre_completo and not senales_negativas_identidad:
            es_el = True
            razon_id = "Match por nombre completo."
        elif senales_negativas_identidad and not senales_politicas:
            es_el = False
            razon_id = "Contexto no político (homónimo probable)."
        elif senales_politicas:
            es_el = True
            razon_id = "Contexto político confirma identidad."
        else:
            # Apellido suelto sin señales — el Fake es conservador y lo
            # acepta con baja confianza para que la suite no descarte
            # menciones legítimas en textos cortos.
            es_el = True
            razon_id = "Sin señales contradictorias; acepta con cautela."

        # Heurística de tono.
        positivos = (
            "impulsa", "promueve", "acompaña", "defiende", "destaca",
            "celebra", "lidera", "logra", "presenta",
        )
        negativos = (
            "critica", "rechaza", "cuestiona", "denuncia", "acusa",
            "ataca", "tilda", "fustiga", "renuncia", "polemiza",
            "denunciado", "acusado",
        )
        hay_pos = any(p in haystack for p in positivos)
        hay_neg = any(n in haystack for n in negativos)
        if hay_pos and not hay_neg:
            tono = TonoMencion.POSITIVO
            confianza = 0.8
            razon_tono = "Verbo positivo en el snippet."
        elif hay_neg and not hay_pos:
            tono = TonoMencion.NEGATIVO
            confianza = 0.8
            razon_tono = "Verbo negativo en el snippet."
        else:
            tono = TonoMencion.NEUTRO
            confianza = 0.5
            razon_tono = "Sin señales claras de tono."

        razon = f"{razon_id} {razon_tono}"[:200]
        return DisambiguacionMencion(
            es_el_legislador=es_el,
            tono=tono,
            confianza_tono=confianza,
            razon=razon,
        )


# ---------------------------------------------------------------------------
# Composición de bullets
# ---------------------------------------------------------------------------


def _qué_propone(e: Expediente) -> str:
    titulo = e.titulo.strip().rstrip(".").strip()
    sumario = (e.sumario or "").strip().rstrip(".").strip()

    if not sumario:
        # Sin sumario, reformulamos el título.
        return _hacer_legible(titulo) + "."

    # Si el sumario empieza repitiendo el título, evitamos el duplicado.
    titulo_corto = titulo.split(" - ")[0] if " - " in titulo else titulo
    base = _hacer_legible(titulo_corto)
    return f"{base}. En concreto: {_hacer_legible(sumario)}."


def _quien_lo_impulsa(e: Expediente) -> str:
    if not e.firmantes:
        return "Sin firmantes registrados en el portal."

    autor = _autor_principal(e.firmantes)
    nombre = autor.nombre.strip()
    partes_extra: list[str] = []
    if autor.bloque:
        partes_extra.append(f"bloque {autor.bloque.strip().title()}")
    if autor.distrito:
        partes_extra.append(f"distrito {autor.distrito.strip().title()}")

    coautores = len(e.firmantes) - 1
    sufijo_co = ""
    if coautores == 1:
        sufijo_co = " Acompaña 1 cofirmante."
    elif coautores > 1:
        sufijo_co = f" Acompañan {coautores} cofirmantes."

    contexto = f" ({'; '.join(partes_extra)})" if partes_extra else ""
    return f"{nombre}{contexto}.{sufijo_co}"


def _probabilidad_de_avance(e: Expediente) -> str:
    base = _avance_segun_estado(e.estado)

    # Si vence por caducidad en < 60 días, sumamos alerta.
    aviso_caducidad = ""
    if e.fecha_caducidad is not None:
        dias = (e.fecha_caducidad - date.today()).days
        if 0 <= dias <= 60:
            aviso_caducidad = (
                f" ⚠ Atención: caduca en {dias} día{'s' if dias != 1 else ''} "
                "por Ley 13.640 si no avanza."
            )

    eventos = len(e.tramite)
    if eventos == 0:
        base += " Sin eventos de trámite registrados todavía."
    elif eventos > 5:
        base += f" Trámite activo: {eventos} eventos registrados."

    return base + aviso_caducidad


# ---------------------------------------------------------------------------
# Argumentos / contraargumentos del briefing
# ---------------------------------------------------------------------------


def _argumentos_fake(e: Expediente) -> list[str]:
    """3 bullets a favor del proyecto, plausibles pero genéricos."""
    autor = _autor_principal(e.firmantes) if e.firmantes else None
    nombre_autor = autor.nombre.strip() if autor else "el autor"
    bloque = (autor.bloque or "").strip().title() if autor else ""
    tipo_legible = e.tipo.value.replace("_", " ")
    bullets = [
        (
            f"Acompaña la línea de trabajo histórica de {bloque or 'su bloque'} "
            f"en la materia y consolida una posición política consistente "
            f"de {nombre_autor.title()}."
        ),
        (
            f"Es un {tipo_legible} con cofirmantes diversos, lo que aumenta "
            f"la probabilidad de obtener dictamen favorable en comisión."
        ),
        (
            "Atiende un reclamo concreto del electorado del despacho — el "
            "tratamiento favorable suma capital político en distritos clave."
        ),
    ]
    return bullets


def _contraargumentos_fake(e: Expediente) -> list[str]:
    """2 bullets de objeciones esperables del bloque rival."""
    return [
        (
            "Costo fiscal sin financiamiento explícito — el bloque rival "
            "va a plantear sobre el rojo presupuestario y la falta de "
            "información de impacto."
        ),
        (
            "Avanza sobre competencias provinciales / autonomías locales — "
            "objeción federalista clásica que activa una porción del "
            "interbloque federal."
        ),
    ]
    # `e` se acepta por simetría con argumentos pero el texto v1 no lo usa.
    _ = e


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _autor_principal(firmantes: list[Firmante]) -> Firmante:
    """Devuelve el firmante con `orden=1`, o el primero si nadie tiene orden=1."""
    for f in firmantes:
        if f.orden == 1:
            return f
    return firmantes[0]


def _hacer_legible(texto: str) -> str:
    """Pasa MAYUSCULAS frías a una capitalización más legible.

    Reglas:
    - Si todo el texto está en mayúsculas (estilo portal HCDN), lo bajamos
      y capitalizamos la primera letra.
    - Sino, lo devolvemos tal cual.
    """
    if texto and texto.upper() == texto:
        return texto.capitalize()
    return texto


# ---------------------------------------------------------------------------
# Clasificación temática (keywords)
# ---------------------------------------------------------------------------


def _normalizar(s: str) -> str:
    """Lowercase + colapsa whitespace + saca tildes ASCII básicas.

    No usa unicodedata.NFKD a propósito: keywords sin tilde sirven igual
    porque el corpus del portal HCDN usa MAYÚSCULAS sin tilde
    consistentemente.
    """
    out = s.lower()
    # Quitar tildes manualmente (sin importar unicodedata).
    table = str.maketrans("áéíóúüñ", "aeiouun")
    out = out.translate(table)
    return re.sub(r"\s+", " ", out).strip()


# Buckets de keywords. Orden importa: el primero que matchea, gana.
# Las áreas específicas (salud, educación, ambiente) van antes que las
# transversales (economía, justicia). Mejorable con embeddings en v2.
_AREA_KEYWORDS: list[tuple[AreaTematica, tuple[str, ...]]] = [
    (
        AreaTematica.SALUD,
        (
            "salud",
            "sanitar",
            "hospital",
            "medic",
            "enferm",
            "vacun",
            "obras sociales",
            "fertilizacion asistida",
            "discapacidad",
        ),
    ),
    (
        AreaTematica.EDUCACION,
        (
            "educacion",
            "educativ",
            "escuela",
            "universidad",
            "universita",
            "docente",
            "alumn",
            "estudiantil",
            "becas",
        ),
    ),
    (
        AreaTematica.AMBIENTE,
        (
            "ambiente",
            "ambiental",
            "ecosistema",
            "climat",
            "incendio",
            "humedales",
            "bosque",
            "deforesta",
            "glaciar",
            "fauna",
            "biodiversidad",
            "contaminacion",
            "residuo",
        ),
    ),
    (
        AreaTematica.TRABAJO,
        (
            "trabajo",
            "trabajadora",
            "trabajador",
            "laboral",
            "jubilacion",
            "jubilad",
            "pension",
            "asignacion familiar",
            "remuneracion",
            "salario",
            "convenio colectivo",
        ),
    ),
    (
        # DDHH antes que SEGURIDAD: "violencia de género", "femicidios",
        # "trata de personas" son DDHH, no seguridad. Si dejamos
        # SEGURIDAD primero con "violenc" como keyword, gana mal.
        AreaTematica.DERECHOS_HUMANOS,
        (
            "derechos humanos",
            "genero",
            "feminici",
            "femicidio",
            "violencia de genero",
            "lgbt",
            "diversidad sexual",
            "trata de personas",
            "memoria",
            "lesa humanidad",
            "discriminacion",
            "inclusion",
        ),
    ),
    (
        AreaTematica.SEGURIDAD,
        (
            "seguridad",
            "policia",
            "policial",
            "fuerza de seguridad",
            "narcotrafico",
            "antinarc",
            "armas",
            "violenc",
            "delito",
            "delictiv",
            "terrorism",
        ),
    ),
    (
        AreaTematica.TRANSPORTE,
        (
            "transporte",
            "ferroviar",
            "ferrocarril",
            "aerea",
            "aeroport",
            "subte",
            "colectiv",
            "ruta nacional",
            "ruta provincial",
            "automotor",
        ),
    ),
    (
        AreaTematica.INFRAESTRUCTURA,
        (
            "infraestructura",
            "obra publica",
            "obras publicas",
            "vivienda",
            "viviendas",
            "habitacional",
            "agua potable",
            "saneamiento",
            "cloacas",
            "energetica",
            "energia",
            "electric",
        ),
    ),
    (
        AreaTematica.JUSTICIA,
        (
            "judicial",
            "codigo civil",
            "codigo penal",
            "codigo procesal",
            "magistrado",
            "fiscal",
            "fiscalia",
            "amparo",
            "habeas",
            "ministerio publico",
            "reforma judicial",
        ),
    ),
    (
        AreaTematica.RELACIONES_EXTERIORES,
        (
            "tratado",
            "convenio internacional",
            "acuerdo internacional",
            "cancilleria",
            "relaciones exteriores",
            "exterior",
            "mercosur",
            "naciones unidas",
            "consulado",
            "embajada",
        ),
    ),
    (
        AreaTematica.ECONOMIA,
        (
            "economia",
            "economic",
            "fiscal",
            "impuesto",
            "tributari",
            "presupuest",
            "deuda publica",
            "exportacion",
            "importacion",
            "moneda",
            "banco central",
            "inflacion",
            "subsidio",
            "regimen tarifario",
            "zona fria",
        ),
    ),
]


def _avance_segun_estado(estado: EstadoExpediente) -> str:
    """Texto base de probabilidad según el estado actual."""
    match estado:
        case EstadoExpediente.INGRESADO:
            return (
                "Baja en el corto plazo — todavía no fue girado a comisión "
                "ni hubo movimientos significativos."
            )
        case EstadoExpediente.EN_COMISION:
            return (
                "Moderada — está en comisión, su avance depende de la "
                "agenda y voluntad política del bloque oficialista."
            )
        case EstadoExpediente.CON_DICTAMEN:
            return "Alta — el dictamen ya está firmado, lo que habilita su tratamiento en recinto."
        case EstadoExpediente.MEDIA_SANCION_HCDN:
            return (
                "Muy alta — ya cuenta con media sanción de Diputados; "
                "necesita el visto bueno del Senado para convertirse en ley."
            )
        case EstadoExpediente.MEDIA_SANCION_HSN:
            return (
                "Muy alta — ya cuenta con media sanción del Senado; "
                "necesita el visto bueno de Diputados para convertirse en ley."
            )
        case EstadoExpediente.SANCIONADO:
            return "Ya fue sancionado — el expediente cerró su trámite con éxito."
        case EstadoExpediente.CADUCO:
            return (
                "Nula — perdió estado parlamentario por caducidad (Ley 13.640) "
                "y requiere reingreso para volver a tratarse."
            )
        case EstadoExpediente.ARCHIVADO:
            return "Nula — el expediente fue archivado y no continuará su trámite."
        case EstadoExpediente.DESCONOCIDO:
            return (
                "Indeterminada — el estado actual no fue posible inferirlo del trámite registrado."
            )


# ---------------------------------------------------------------------------
# Detección de referencias legales (para clasificar_norma_bo)
# ---------------------------------------------------------------------------


_REF_LEGAL_RE = re.compile(
    r"""
    \b(
        # "Ley NN.NNN" o "Ley NNNNN" sin punto
        Ley\s+N?[°º]?\s*(?P<ley_num>\d{1,3}\.\d{3}|\d{4,6})
      | Decreto\s+N?[°º]?\s*(?P<dec_num>\d{1,5}/\d{2,4})
      | Resolución\s+N?[°º]?\s*(?P<res_num>\d{1,5}/\d{2,4})
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _detectar_referencias_legales(texto: str) -> list[str]:
    """Extrae referencias a leyes/decretos/resoluciones mencionados en
    el texto. Devuelve lista deduplicada y normalizada."""
    refs: list[str] = []
    for m in _REF_LEGAL_RE.finditer(texto):
        if m.group("ley_num"):
            ref = f"Ley {m.group('ley_num')}"
        elif m.group("dec_num"):
            ref = f"Decreto {m.group('dec_num')}"
        elif m.group("res_num"):
            ref = f"Resolución {m.group('res_num')}"
        else:
            continue
        if ref not in refs:
            refs.append(ref)
        if len(refs) >= 10:
            break
    return refs
