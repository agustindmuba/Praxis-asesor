"""Caso de uso: generar un Accionable enriquecido con el perfil
opositor del despacho (feat-42.2 — A+B+F).

Toma:
- El perfil opositor del despacho (bandera, tono, adversarios, aliados,
  temas de cuidado).
- Un payload del evento (norma BO o artículo) con título y resumen.

Devuelve un `AccionableEvento` con:
- Razón política específica para este despacho (no genérica).
- Acción sugerida (enum cerrada del catálogo).
- 2-3 tweets sugeridos con tonos consistentes con el perfil.
- Confianza global.

Cache: si ya hay un accionable para `(despacho_id, tipo_evento,
evento_id)`, lo devuelve salvo que se fuerce regenerar=True.

Costo aprox por llamada: ~$0.02-0.04 USD (Sonnet 4.5 con perfil de
~3KB + payload del evento + JSON output ~2KB).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from praxis.application.ports import (
    AccionableEventoRepository,
    LlmProvider,
    PerfilOpositorRepository,
)
from praxis.domain import (
    ACCIONABLE_PROMPT_VERSION,
    AccionableEvento,
    AccionSugerida,
    ConfianzaAccionable,
    PerfilOpositorDespacho,
    TipoEvento,
    TweetSugerido,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Sos un jefe de asesores parlamentario senior. Tu
trabajo es decirle al asesor más junior QUÉ hacer ante un evento que
le acaba de aparecer en el radar.

Te paso:
1. El perfil opositor del despacho (bandera principal, tono comunicacional,
   adversarios, aliados, temas de cuidado, línea de bloque).
2. El evento concreto que apareció (norma del Boletín Oficial o noticia
   en medios).

Devolvé EXACTAMENTE este JSON, sin texto antes ni después:

{
  "razon_para_despacho": "1-2 oraciones que conectan ESTE evento con LA bandera/banderas del despacho. Si no conecta con nada del perfil, decilo: 'No conecta con la línea actual del despacho'.",
  "accion_sugerida": "uno de: pedido_informes | proyecto_contraposicion | declaracion_camara | silencio_estrategico | retweet_critico | retweet_apoyo | articulo_opinion | interpelacion | otro",
  "explicacion_accion": "1-2 oraciones que explican POR QUÉ esa acción es la correcta dada la línea del despacho. Mencioná aliados que podrían acompañar, si corresponde.",
  "tweets_sugeridos": [
    {"tono": "frontal", "texto": "..."},
    {"tono": "técnico", "texto": "..."},
    {"tono": "irónico", "texto": "..."}
  ],
  "confianza": "alta | media | baja"
}

Reglas duras:
- Si el perfil indica tema_de_cuidado relacionado al evento → `silencio_estrategico` + tweets vacíos.
- Si el evento toca un adversario directo del perfil → tono más frontal/crítico.
- Si toca un aliado → tono dialogal/de apoyo (si corresponde).
- Los tweets DEBEN respetar el `tono_comunicacional` del perfil base (si es técnico-jurídico, no podés sugerir tono militante puro). Los 3 son variaciones DENTRO de ese tono.
- Cada tweet < 280 caracteres, sin hashtags excesivos (máx 2), con datos concretos (números, leyes, fechas) cuando sea posible.
- NO inventes datos. Si la evidencia es escasa, baja confianza a "baja" y mencionalo.
- Cuando la acción sea `silencio_estrategico`, devolvé "tweets_sugeridos": [].
"""


@dataclass(frozen=True, slots=True)
class PayloadEvento:
    """Snapshot mínimo del evento para alimentar al LLM."""

    titulo: str
    resumen: str
    tipo: TipoEvento
    evento_id: UUID
    metadata_extra: dict[str, object]    # bloque emisor, fuente, fecha, etc.


class GenerarAccionableConPerfil:
    """Use case core de feat-42.2."""

    def __init__(
        self,
        *,
        accionables: AccionableEventoRepository,
        perfiles: PerfilOpositorRepository,
        llm: LlmProvider,
    ) -> None:
        self._accionables = accionables
        self._perfiles = perfiles
        self._llm = llm

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        payload: PayloadEvento,
        regenerar: bool = False,
    ) -> AccionableEvento:
        if not regenerar:
            cacheado = await self._accionables.buscar_por_evento(
                despacho_id=despacho_id,
                tipo_evento=payload.tipo,
                evento_id=payload.evento_id,
            )
            if cacheado is not None:
                return cacheado

        perfil = await self._perfiles.buscar_por_despacho(despacho_id)
        if perfil is None:
            raise ValueError(
                "El despacho no tiene perfil opositor cargado. "
                "Generá uno desde /configuracion/perfil-opositor primero.",
            )

        parsed, modelo = await self._razonar(perfil, payload)
        ahora = datetime.now(UTC)
        accionable = self._construir_accionable(
            despacho_id=despacho_id,
            payload=payload,
            parsed=parsed,
            modelo=modelo,
            ahora=ahora,
        )
        return await self._accionables.upsert(accionable)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _razonar(
        self, perfil: PerfilOpositorDespacho, payload: PayloadEvento,
    ) -> tuple[dict, str]:
        contenido = (
            f"=== PERFIL OPOSITOR DEL DESPACHO ===\n"
            f"{self._perfil_a_texto(perfil)}\n\n"
            f"=== EVENTO ({payload.tipo.value}) ===\n"
            f"Título: {payload.titulo}\n"
            f"Resumen: {payload.resumen[:1500]}\n"
            f"Metadata: {json.dumps(payload.metadata_extra, ensure_ascii=False)[:500]}\n\n"
            "Generá el JSON del accionable según las reglas."
        )
        raw, modelo = await self._llm.razonar_libre(
            system=SYSTEM_PROMPT,
            user=contenido,
            max_tokens=1500,
        )
        return self._parsear_json(raw), modelo

    def _perfil_a_texto(self, perfil: PerfilOpositorDespacho) -> str:
        adv = "\n".join(f"  - {a.nombre}: {a.razon}" for a in perfil.adversarios[:5])
        ali = "\n".join(f"  - {a.nombre}: {a.razon}" for a in perfil.aliados[:5])
        return (
            f"Bandera principal: {perfil.bandera_principal}\n"
            f"Banderas secundarias: {', '.join(perfil.banderas_secundarias[:5])}\n"
            f"Temas de cuidado (no tocar): {', '.join(perfil.temas_de_cuidado[:5])}\n"
            f"Tono comunicacional: {perfil.tono_comunicacional.value}\n"
            f"Línea de bloque: {perfil.linea_de_bloque}\n"
            f"Adversarios:\n{adv or '  (ninguno declarado)'}\n"
            f"Aliados:\n{ali or '  (ninguno declarado)'}\n"
        )

    def _parsear_json(self, raw: str) -> dict:
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s[:-3].strip()
            if s.startswith("json"):
                s = s[4:].strip()
        return json.loads(s)

    def _construir_accionable(
        self,
        *,
        despacho_id: UUID,
        payload: PayloadEvento,
        parsed: dict,
        modelo: str,
        ahora: datetime,
    ) -> AccionableEvento:
        try:
            accion = AccionSugerida((parsed.get("accion_sugerida") or "").strip())
        except ValueError:
            accion = AccionSugerida.OTRO
        try:
            confianza = ConfianzaAccionable((parsed.get("confianza") or "").strip())
        except ValueError:
            confianza = ConfianzaAccionable.MEDIA

        tweets_raw = parsed.get("tweets_sugeridos") or []
        tweets = []
        for t in tweets_raw[:3]:
            texto = (t.get("texto") or "").strip()
            if not texto:
                continue
            tweets.append(
                TweetSugerido(
                    tono=(t.get("tono") or "neutro").strip(),
                    texto=texto[:280],
                ),
            )

        return AccionableEvento(
            despacho_id=despacho_id,
            tipo_evento=payload.tipo,
            evento_id=payload.evento_id,
            razon_para_despacho=(parsed.get("razon_para_despacho") or "").strip(),
            accion_sugerida=accion,
            explicacion_accion=(parsed.get("explicacion_accion") or "").strip(),
            tweets_sugeridos=tweets,
            confianza=confianza,
            generado_en=ahora,
            modelo=modelo,
            prompt_version=ACCIONABLE_PROMPT_VERSION,
        )
