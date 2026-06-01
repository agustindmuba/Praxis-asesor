"""Renderizado del Briefing a HTML y (opcional) PDF.

El template Jinja2 vive en `templates/briefing.html.j2`. Está pensado
para que el HTML sea autocontenido (CSS inline) y se vea bien tanto en
browser (preview en la UI) como impreso a PDF.

Si `weasyprint` no está instalado o falla (ej. dependencias nativas en
Windows), `render_briefing_pdf` lanza `RuntimeError` con instrucciones —
el caller puede ofrecer al usuario "imprimir desde el browser" como
fallback de v1.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from praxis.domain import AREA_LABELS, Briefing

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)


# Labels legibles para el PDF.
_ESTADO_LABEL = {
    "ingresado": "Ingresado",
    "en_comision": "En comisión",
    "con_dictamen": "Con dictamen",
    "media_sancion_hcdn": "Media sanción HCDN",
    "media_sancion_hsn": "Media sanción HSN",
    "sancionado": "Sancionado",
    "archivado": "Archivado",
    "caduco": "Caduco",
    "desconocido": "Sin estado claro",
}

_PRIORIDAD_BADGE = {
    "alta": ("#dc2626", "ALTA"),
    "media": ("#d97706", "MEDIA"),
    "baja": ("#65a30d", "BAJA"),
}

_REC_LABEL = {
    "a_favor": ("#16a34a", "A FAVOR"),
    "abstencion": ("#a16207", "ABSTENCIÓN"),
    "en_contra": ("#dc2626", "EN CONTRA"),
    "sin_recomendacion": ("#6b7280", "SIN RECOMENDACIÓN"),
}

_ROL_LABEL = {"autor": "Autor", "cofirmante": "Cofirmante"}


def render_briefing_html(briefing: Briefing) -> str:
    """Devuelve el HTML del briefing listo para mostrar o convertir a PDF."""
    template = _env.get_template("briefing.html.j2")
    return template.render(
        briefing=briefing,
        area_label=AREA_LABELS,
        estado_label=_ESTADO_LABEL,
        prioridad_badge=_PRIORIDAD_BADGE,
        recomendacion_label=_REC_LABEL,
        rol_label=_ROL_LABEL,
    )


def render_briefing_pdf(briefing: Briefing) -> bytes:
    """Devuelve bytes PDF del briefing. Levanta RuntimeError si no hay weasyprint."""
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depende del environment
        raise RuntimeError(
            "weasyprint no está instalado. En Windows requiere "
            "GTK runtime; en Linux libpango/libcairo. Como fallback "
            "usar render_briefing_html() y dejar que el usuario imprima "
            "desde el browser."
        ) from exc

    html_str = render_briefing_html(briefing)
    return HTML(string=html_str).write_pdf()  # type: ignore[no-any-return]
