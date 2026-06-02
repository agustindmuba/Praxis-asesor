"""Adaptador del Boletín Oficial — `FuenteBO`.

Implementación: `BoletinOficialPdfClient` baja los PDFs del día desde
`s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/<seccion>.pdf` y los parsea con
`pdfplumber`. Ver `docs/spikes/39-boletin-oficial.md` para el rationale.
"""

from praxis.infrastructure.bo.pdf_client import BoletinOficialPdfClient

__all__ = ["BoletinOficialPdfClient"]
