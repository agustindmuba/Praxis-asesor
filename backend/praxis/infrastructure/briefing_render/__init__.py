"""Renderizado del Briefing a HTML y PDF.

Vive en infrastructure porque es I/O — leemos templates de filesystem,
escribimos bytes de salida. El dominio (`Briefing`) es totalmente puro.

Dos servicios:
- `render_briefing_html(briefing)` → str
- `render_briefing_pdf(briefing)` → bytes (HTML + weasyprint)
"""

from praxis.infrastructure.briefing_render.renderer import (
    render_briefing_html,
    render_briefing_pdf,
)

__all__ = ["render_briefing_html", "render_briefing_pdf"]
