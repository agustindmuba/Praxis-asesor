"""`BoletinOficialPdfClient`: implementación de `FuenteBO` que baja
los PDFs del día desde S3 y los parsea con `pdfplumber`.

Estrategia (ver `docs/spikes/39-boletin-oficial.md`):

1. Descargar `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/<seccion>.pdf`.
2. Parsear con `pdfplumber.open(BytesIO(...))`.
3. Extraer normas via `parser.extraer_normas_bo()`.
4. Cachear `(seccion, fecha) → (list[NormaBO], list[NormaBOTexto])` en
   memoria del proceso para que `obtener_texto_completo()` no requiera
   re-bajar el PDF.

Respeta ADR 0007:
- UA identificable (default desde Settings).
- Rate limit 1 req/seg (trivial — son 2 PDFs por noche).
- Timeout 30s.
- Sin retries agresivos: 1 retry con backoff 5s.

Limitaciones v1:
- Sólo PDFs del día corriente (S3 sólo sirve `pdf-del-dia/*`).
- `obtener_texto_completo()` devuelve None si la norma no fue procesada
  en una corrida previa de la misma instancia (no persistimos cache
  entre procesos).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from io import BytesIO
from uuid import UUID

import httpx
import pdfplumber

from praxis.application.ports import FuenteBO
from praxis.domain import (
    SECCIONES_ACTIVAS_V1,
    FuenteNoDisponible,
    NormaBO,
    NormaBOTexto,
    SeccionBO,
)
from praxis.infrastructure.bo.parser import extraer_normas_bo

log = logging.getLogger(__name__)


# UA identificable (ADR 0007). El caller puede overridear via constructor.
DEFAULT_UA = (
    "PraxisAsesor/0.1 (+contacto@dominio.com; "
    "monitoreo legislativo Praxis Asesor)"
)

# Base URL del CDN público del BO.
BASE_S3 = "https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia"


# Mapping de SeccionBO a path en S3.
#
# Solo LEGISLACION → primera está activo. Tras feat-39.3 confirmamos que
# la "Cuarta Sección" del BO es "Registro de Dominios" (no
# designaciones); las designaciones se publican como decretos dentro de
# Primera. Los otros mappings son placeholders para v2.
_SECCION_A_PATH: dict[SeccionBO, str] = {
    SeccionBO.LEGISLACION: "primera",
    SeccionBO.DESIGNACIONES: "primera",     # mismo PDF; filtrado por LLM en v2
    SeccionBO.AVISOS_OFICIALES: "segunda",  # reservado v2 vía SAIJ; no usar
}


class BoletinOficialPdfClient(FuenteBO):
    """Adaptador `FuenteBO` que consume PDFs del día desde S3."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_UA,
        base_url: str = BASE_S3,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent, "Accept": "application/pdf"},
            follow_redirects=True,
        )
        self._base_url = base_url.rstrip("/")
        # Cache por (seccion, fecha) → (normas, textos).
        self._cache: dict[
            tuple[SeccionBO, date],
            tuple[list[NormaBO], list[NormaBOTexto]],
        ] = {}

    async def listar_normas_del_dia(
        self, fecha: date, seccion: SeccionBO,
    ) -> list[NormaBO]:
        if seccion not in SECCIONES_ACTIVAS_V1:
            log.warning(
                "Sección %s no está activa en v1; devolviendo lista vacía.",
                seccion.value,
            )
            return []

        # S3 sólo sirve "pdf-del-dia". Si nos piden otra fecha, no hay
        # PDF para esa fecha y devolvemos vacío con warning.
        hoy = datetime.now(UTC).date()
        if fecha != hoy:
            log.warning(
                "Solicitada fecha %s pero S3 sólo sirve día corriente "
                "(%s). Devolviendo vacío.",
                fecha, hoy,
            )
            return []

        key = (seccion, fecha)
        if key not in self._cache:
            pdf_bytes = await self._bajar_pdf(seccion)
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                normas, textos = extraer_normas_bo(
                    pdf,
                    fecha_publicacion=fecha,
                    seccion=seccion,
                )
            self._cache[key] = (normas, textos)

        normas, _ = self._cache[key]
        return list(normas)

    async def obtener_texto_completo(self, norma: NormaBO) -> str | None:
        """Devuelve el texto de la norma si fue procesada en una
        corrida previa de `listar_normas_del_dia` en esta instancia.

        Para encontrar el texto, matcheamos por `hash_sumario` (único
        por norma) en las entradas cacheadas.
        """
        for normas_cache, textos_cache in self._cache.values():
            for n, t in zip(normas_cache, textos_cache, strict=False):
                if n.hash_sumario == norma.hash_sumario:
                    return t.texto
        return None

    async def aclose(self) -> None:
        """Cierra el HTTP client si lo creamos nosotros."""
        if self._owns_client:
            await self._client.aclose()

    async def _bajar_pdf(self, seccion: SeccionBO) -> bytes:
        path = _SECCION_A_PATH[seccion]
        url = f"{self._base_url}/{path}.pdf"
        log.info("Bajando PDF BO sección %s desde %s", seccion.value, url)

        # 1 intento + 1 retry con backoff de 5s.
        for intento in (1, 2):
            try:
                resp = await self._client.get(url)
            except httpx.RequestError as exc:
                if intento == 1:
                    log.warning("Error transitorio bajando %s: %s; retry en 5s",
                                url, exc)
                    await asyncio.sleep(5)
                    continue
                raise FuenteNoDisponible("BO_PDF", str(exc)) from exc

            if resp.status_code == 200 and resp.content[:5] == b"%PDF-":
                return resp.content
            if intento == 1 and resp.status_code in (502, 503, 504):
                log.warning("BO devolvió %d; retry en 5s", resp.status_code)
                await asyncio.sleep(5)
                continue

            raise FuenteNoDisponible(
                "BO_PDF",
                f"GET {url} → status {resp.status_code} "
                f"(esperaba 200 con %PDF header)",
            )

        # Unreachable; el loop siempre retorna o raise.
        raise FuenteNoDisponible("BO_PDF", "lógica inconsistente")


# Conveniencia: para uso desde scripts/seeds, una factory que arma el
# cliente y lo cierra solo. La pattern recomendada es contextmanager
# async, pero acá no hace falta — los caller son scripts cortos.


def hidratar_norma_id_en_textos(
    textos: list[NormaBOTexto], normas: list[NormaBO],
) -> list[NormaBOTexto]:
    """Helper: tras persistir las NormaBO y obtener sus IDs, reemplazamos
    el placeholder UUID(0) en NormaBOTexto.norma_id por el id real.

    Las dos listas vienen alineadas por orden de `extraer_normas_bo()`.
    """
    placeholder = UUID(int=0)
    resultado: list[NormaBOTexto] = []
    for n, t in zip(normas, textos, strict=True):
        if n.id is None:
            raise ValueError(
                f"No se puede hidratar texto: norma {n.numero_norma} sin id"
            )
        if t.norma_id != placeholder:
            resultado.append(t)
            continue
        resultado.append(
            NormaBOTexto(
                norma_id=n.id,
                texto=t.texto,
                capturado_en=t.capturado_en,
            )
        )
    return resultado
