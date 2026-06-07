"""Scraper del Plan de Labor / Orden del Día de HCDN (feat-45).

El portal expone el temario de cada sesión en `procesar.html` que devuelve
un HTML wrapper con el PDF embebido en base64 (función JS `abrirPDF`).

Pipeline:
1. Listar sesiones disponibles en `/secparl/dclp/plan_de_labor/plt.html`.
2. Descargar el HTML de cada sesión (`id_sesion=NNNN&tipo=temario`).
3. Extraer el base64 del PDF embebido y decodificarlo.
4. Parsear el PDF con pdfplumber → lista de items del temario.
"""

from praxis.infrastructure.scrapers.hcdn.orden_del_dia.parser import (
    ItemOrdenDelDia,
    OrdenDelDiaParseado,
    extraer_pdf_base64,
    parsear_pdf_temario,
)
from praxis.infrastructure.scrapers.hcdn.orden_del_dia.scraper import (
    HcdnOrdenDelDiaScraper,
    SesionDisponible,
)

__all__ = [
    "ItemOrdenDelDia",
    "OrdenDelDiaParseado",
    "extraer_pdf_base64",
    "parsear_pdf_temario",
    "HcdnOrdenDelDiaScraper",
    "SesionDisponible",
]
