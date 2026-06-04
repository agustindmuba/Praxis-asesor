"""Caso de uso: inferir perfil opositor de un legislador desde su
huella parlamentaria documentada en la propia DB del despacho
(feat-42.1).

Toma como input el nombre del legislador (substring) y el despacho_id
al que asociar el perfil resultante. Junta:

- Expedientes firmados (con áreas temáticas)
- Votaciones nominales con voto + bloque
- Cofirmantes recurrentes
- Áreas temáticas dominantes

Pasa todo al LLM con un prompt estructurado y devuelve un
`PerfilOpositorDespacho` listo para upsert. Si ya existe un perfil
editado manualmente, el caller decide si pisarlo o no.

Diseño deliberado: la lógica de query SQL vive acá porque es
inherente al caso de uso (NO al repo). El repo del perfil solo
persiste. El repo no tiene "buscar huella" porque eso es responsabilidad
del caso de uso.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import LlmProvider, PerfilOpositorRepository
from praxis.domain import (
    PERFIL_OPOSITOR_PROMPT_VERSION,
    ConfianzaGlobal,
    FiguraReferida,
    PerfilOpositorDespacho,
    TonoComunicacional,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Sos un analista político senior especializado en
comportamiento parlamentario argentino. Te paso la huella documental
de un/a legislador/a en HCDN: proyectos firmados, votaciones nominales,
áreas temáticas dominantes y cofirmantes recurrentes.

Tu trabajo: inferir un PERFIL OPOSITOR ACCIONABLE — el tipo de documento
que un jefe de asesores usaría para orientar la línea política del
despacho. NO es una biografía. Es una herramienta operativa.

Devolvé EXACTAMENTE este JSON (sin texto antes ni después):

{
  "bandera_principal": "1 frase con el eje político central (qué milita)",
  "banderas_secundarias": ["3-5 items, cada uno una frase corta"],
  "temas_de_cuidado": ["3-5 temas que probablemente prefiere no tocar (con razón)"],
  "tono_comunicacional": "uno de: tecnico-juridico | militante-bloque | dialogal-conciliador | frontal-confrontativo | ironico | mixto",
  "adversarios_inferidos": [
    {"nombre": "...", "razon": "qué señal lo indica"}
  ],
  "aliados_inferidos": [
    {"nombre": "...", "razon": "qué señal lo indica"}
  ],
  "linea_de_bloque": "cómo se posiciona el bloque frente al oficialismo",
  "justificacion_evidencia": "1-2 párrafos con las señales concretas",
  "confianza_global": "alta | media | baja",
  "advertencias": ["cosas que el asesor debería verificar manualmente"]
}

Reglas duras:
- NO inventes datos que no surjan de la evidencia.
- Si la evidencia es escasa para un campo, ponelo en confianza baja y mencionalo en advertencias.
- Para temas_de_cuidado: razoná por AUSENCIA — qué áreas NO firma, qué votaciones se ausentó.
- adversarios_inferidos: de las votaciones donde votó NEGATIVO, qué bloque/figura impulsaba esa ley.
- aliados_inferidos: cofirmantes recurrentes con quien comparte ≥3 proyectos.
- Sé concreto con números. "Cuida la salud" es ruido; "Vota contra arancelamientos y firma 2 proyectos de cobertura universal" es señal.
"""


@dataclass(frozen=True, slots=True)
class HuellaParlamentaria:
    """Snapshot crudo de la actividad documental del legislador."""

    nombre_buscado: str
    identidades: list[dict]
    expedientes_firmados: list[dict]
    areas_dominantes: list[dict]
    cofirmantes_recurrentes: list[dict]
    votaciones: list[dict]

    def total_evidencia(self) -> int:
        return (
            len(self.expedientes_firmados)
            + len(self.votaciones)
            + len(self.cofirmantes_recurrentes)
        )


class InferirPerfilOpositor:
    """Use case principal de feat-42.1."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        perfiles: PerfilOpositorRepository,
        llm: LlmProvider,
    ) -> None:
        self._session = session
        self._perfiles = perfiles
        self._llm = llm

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        nombre_legislador: str,
        max_votaciones: int = 50,
    ) -> PerfilOpositorDespacho:
        huella = await self._fetch_huella(nombre_legislador, max_votaciones)
        if huella.total_evidencia() == 0:
            raise ValueError(
                f"No encontré actividad parlamentaria para '{nombre_legislador}'",
            )
        log.info(
            "Huella %s: %d expedientes, %d votaciones, %d cofirmantes",
            nombre_legislador,
            len(huella.expedientes_firmados),
            len(huella.votaciones),
            len(huella.cofirmantes_recurrentes),
        )
        perfil = await self._llamar_llm(despacho_id, huella)
        return await self._perfiles.upsert(perfil)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    async def _fetch_huella(
        self, nombre_legislador: str, max_vot: int,
    ) -> HuellaParlamentaria:
        p = f"%{nombre_legislador.lower()}%"

        r = await self._session.execute(text("""
            SELECT DISTINCT nombre, bloque, distrito, COUNT(*) c
            FROM firmante WHERE LOWER(nombre) LIKE :n
            GROUP BY nombre, bloque, distrito ORDER BY c DESC LIMIT 5
        """), {"n": p})
        identidades = [
            {"nombre": n, "bloque": b, "distrito": d, "proyectos": c}
            for n, b, d, c in r.all()
        ]

        r = await self._session.execute(text("""
            SELECT e.tipo, e.titulo, e.anio, e.numero, e.origen,
                   COALESCE(eat.area, 'sin_clasificar') area,
                   f.orden, f.bloque
            FROM firmante f
            JOIN expediente e ON e.id = f.expediente_id
            LEFT JOIN expediente_area_tematica eat ON eat.expediente_id = e.id
            WHERE LOWER(f.nombre) LIKE :n
            ORDER BY e.anio DESC, e.numero DESC LIMIT 80
        """), {"n": p})
        expedientes = [
            {
                "tipo": tipo, "titulo": titulo[:200], "anio": anio,
                "numero": numero, "origen": origen, "area": area,
                "orden_firma": orden, "bloque_al_firmar": bloque,
            }
            for tipo, titulo, anio, numero, origen, area, orden, bloque in r.all()
        ]

        r = await self._session.execute(text("""
            SELECT COALESCE(eat.area, 'sin_clasificar') area, COUNT(*) c
            FROM firmante f
            JOIN expediente_area_tematica eat ON eat.expediente_id = f.expediente_id
            WHERE LOWER(f.nombre) LIKE :n
            GROUP BY eat.area ORDER BY c DESC
        """), {"n": p})
        areas = [{"area": a, "n_proyectos": c} for a, c in r.all()]

        r = await self._session.execute(text("""
            SELECT f2.nombre, f2.bloque, COUNT(DISTINCT f2.expediente_id) c
            FROM firmante f1
            JOIN firmante f2 ON f2.expediente_id = f1.expediente_id AND f2.id != f1.id
            WHERE LOWER(f1.nombre) LIKE :n
            GROUP BY f2.nombre, f2.bloque
            HAVING COUNT(DISTINCT f2.expediente_id) >= 2
            ORDER BY c DESC LIMIT 15
        """), {"n": p})
        cofirmantes = [
            {"nombre": n, "bloque": b, "proyectos_compartidos": c}
            for n, b, c in r.all()
        ]

        r = await self._session.execute(text("""
            SELECT v.fecha, v.asunto, v.titulo_od, vl.voto, vl.bloque,
                   v.aprobada, v.resultado_afirmativos, v.resultado_negativos,
                   vl.que_dijo
            FROM voto_legislador vl
            JOIN votacion v ON v.id = vl.votacion_id
            WHERE LOWER(vl.legislador_nombre) LIKE :n
            ORDER BY v.fecha DESC LIMIT :lim
        """), {"n": p, "lim": max_vot})
        votaciones = [
            {
                "fecha": str(fecha) if fecha else None,
                "asunto": (asunto or titulo_od or "")[:200],
                "voto": voto,
                "bloque_en_ese_momento": bloque,
                "ley_aprobada": aprobada,
                "afirmativos_totales": afir,
                "negativos_totales": neg,
                "que_dijo": (qd or "")[:200] if qd else None,
            }
            for fecha, asunto, titulo_od, voto, bloque, aprobada, afir, neg, qd in r.all()
        ]

        return HuellaParlamentaria(
            nombre_buscado=nombre_legislador,
            identidades=identidades,
            expedientes_firmados=expedientes,
            areas_dominantes=areas,
            cofirmantes_recurrentes=cofirmantes,
            votaciones=votaciones,
        )

    async def _llamar_llm(
        self, despacho_id: UUID, huella: HuellaParlamentaria,
    ) -> PerfilOpositorDespacho:
        # Usamos el LlmProvider directamente como cliente Anthropic. El
        # método `crear_mensaje_libre` es un escape hatch — si el provider
        # es Anthropic, lo usa; si es Fake, devuelve un payload mínimo.
        contenido = (
            f"Huella parlamentaria documental del legislador "
            f"'{huella.nombre_buscado}':\n\n```json\n"
            f"{self._huella_a_json(huella)[:30000]}\n```\n\n"
            "Generá el JSON del perfil opositor según las reglas."
        )
        raw, modelo = await self._llm.razonar_libre(
            system=SYSTEM_PROMPT,
            user=contenido,
            max_tokens=3000,
        )
        parsed = self._parsear_json(raw)
        ahora = datetime.now(UTC)
        return PerfilOpositorDespacho(
            despacho_id=despacho_id,
            bandera_principal=parsed.get("bandera_principal", ""),
            banderas_secundarias=parsed.get("banderas_secundarias", []),
            temas_de_cuidado=parsed.get("temas_de_cuidado", []),
            tono_comunicacional=self._tono(parsed.get("tono_comunicacional")),
            adversarios=[
                FiguraReferida(nombre=a.get("nombre", ""), razon=a.get("razon", ""))
                for a in parsed.get("adversarios_inferidos", [])
            ],
            aliados=[
                FiguraReferida(nombre=a.get("nombre", ""), razon=a.get("razon", ""))
                for a in parsed.get("aliados_inferidos", [])
            ],
            linea_de_bloque=parsed.get("linea_de_bloque", ""),
            justificacion_evidencia=parsed.get("justificacion_evidencia", ""),
            advertencias=parsed.get("advertencias", []),
            confianza_global=self._confianza(parsed.get("confianza_global")),
            inferido_en=ahora,
            editado_en=None,
            modelo_inferencia=modelo,
            prompt_version=PERFIL_OPOSITOR_PROMPT_VERSION,
        )

    def _huella_a_json(self, huella: HuellaParlamentaria) -> str:
        return json.dumps(
            {
                "nombre_buscado": huella.nombre_buscado,
                "identidades": huella.identidades,
                "expedientes_firmados": huella.expedientes_firmados,
                "areas_dominantes": huella.areas_dominantes,
                "cofirmantes_recurrentes": huella.cofirmantes_recurrentes,
                "votaciones": huella.votaciones,
            },
            ensure_ascii=False,
            indent=2,
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

    def _tono(self, raw: str | None) -> TonoComunicacional:
        try:
            return TonoComunicacional((raw or "").strip())
        except ValueError:
            return TonoComunicacional.MIXTO

    def _confianza(self, raw: str | None) -> ConfianzaGlobal:
        try:
            return ConfianzaGlobal((raw or "").strip())
        except ValueError:
            return ConfianzaGlobal.MEDIA
