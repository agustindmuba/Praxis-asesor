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

from datetime import date

from praxis.application.ports import LlmProvider
from praxis.domain import EstadoExpediente, Expediente, Firmante

FAKE_MODEL_NAME = "fake"


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
