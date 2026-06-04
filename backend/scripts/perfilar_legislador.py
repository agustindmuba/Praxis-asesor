"""Perfilamiento automático de un legislador a partir de su huella
parlamentaria (feat-42.0 — Fase 1 del bot de perfil).

Toma del Postgres del despacho:
- Expedientes donde es autor/cofirmante (titulos + áreas temáticas)
- Votaciones donde participó (asunto + voto + bloque del momento)
- Cofirmantes recurrentes (con qué bancada articula)
- Áreas temáticas dominantes

Lo pasa a Sonnet 4.5 con un prompt estructurado que devuelve un
borrador de perfil opositor en JSON:

- bandera_principal: una frase
- banderas_secundarias: 3-5 items
- temas_de_cuidado: temas donde el silencio es estratégico
- tono_comunicacional: técnico / militante / dialogal / etc.
- adversarios_inferidos: votaciones donde votó contrario a oficialismo
- aliados_inferidos: cofirmantes recurrentes
- justificacion_evidencia: qué señales soportan cada inferencia
- confianza_global: low/med/high según volumen de datos

Output a stdout en JSON formateado. El asesor lo lee, lo edita, y
lo carga como `PerfilOpositorDespacho` (Fase 1.5, no en este script).

Uso:
    PYTHONUTF8=1 uv run python -m scripts.perfilar_legislador \\
        --nombre "JULIANO, PABLO"

    PYTHONUTF8=1 uv run python -m scripts.perfilar_legislador \\
        --nombre "MANES" --max-votaciones 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("perfilar_legislador")
log.setLevel(logging.INFO)


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
  "tono_comunicacional": "uno de: tecnico-juridico | militante-bloque | dialogal-conciliador | frontal-confrontativo | irónico | mixto",
  "adversarios_inferidos": [
    {"nombre": "...", "razon": "qué señal lo indica"}
  ],
  "aliados_inferidos": [
    {"nombre": "...", "razon": "qué señal lo indica"}
  ],
  "linea_de_bloque": "cómo se posiciona el bloque frente al oficialismo (dialogal / oposición dura / colaboración táctica / cambiante)",
  "justificacion_evidencia": "1-2 párrafos con las señales concretas que usaste para inferir lo de arriba",
  "confianza_global": "alta | media | baja",
  "advertencias": ["cosas que el asesor debería verificar manualmente porque la inferencia es débil"]
}

Reglas duras:
- NO inventes datos que no surjan de la evidencia.
- Si la evidencia es escasa para un campo, ponelo en confianza baja y mencionalo en advertencias.
- Para temas_de_cuidado: razoná por AUSENCIA — qué áreas NO firma, qué votaciones se ausentó, qué temas evita.
- adversarios_inferidos: de las votaciones donde votó NEGATIVO, qué bloque/figura impulsaba esa ley.
- aliados_inferidos: cofirmantes recurrentes con quien comparte ≥3 proyectos.
- Sé concreto. "Cuida la salud pública" es ruido; "Vota contra arancelamientos de OOSS y firma 2 proyectos de cobertura universal" es señal.
"""


async def fetch_huella(session, nombre_legislador: str, max_vot: int):  # type: ignore[no-untyped-def]
    """Trae toda la actividad documentada del legislador."""
    out: dict = {"nombre_buscado": nombre_legislador}

    # Identidad: variantes del nombre + bloque más reciente.
    r = await session.execute(text("""
        SELECT DISTINCT nombre, bloque, distrito, COUNT(*) c
        FROM firmante
        WHERE LOWER(nombre) LIKE :n
        GROUP BY nombre, bloque, distrito
        ORDER BY c DESC LIMIT 5
    """), {"n": f"%{nombre_legislador.lower()}%"})
    out["identidades"] = [
        {"nombre": n, "bloque": b, "distrito": d, "proyectos": c}
        for n, b, d, c in r.all()
    ]

    # Expedientes firmados con áreas.
    r = await session.execute(text("""
        SELECT e.tipo, e.titulo, e.anio, e.numero, e.origen,
               COALESCE(eat.area, 'sin_clasificar') area,
               f.orden, f.bloque
        FROM firmante f
        JOIN expediente e ON e.id = f.expediente_id
        LEFT JOIN expediente_area_tematica eat ON eat.expediente_id = e.id
        WHERE LOWER(f.nombre) LIKE :n
        ORDER BY e.anio DESC, e.numero DESC
        LIMIT 80
    """), {"n": f"%{nombre_legislador.lower()}%"})
    out["expedientes_firmados"] = [
        {
            "tipo": tipo, "titulo": titulo[:200], "anio": anio,
            "numero": numero, "origen": origen, "area": area,
            "orden_firma": orden, "bloque_al_firmar": bloque,
        }
        for tipo, titulo, anio, numero, origen, area, orden, bloque in r.all()
    ]

    # Áreas dominantes (agregadas).
    r = await session.execute(text("""
        SELECT COALESCE(eat.area, 'sin_clasificar') area, COUNT(*) c
        FROM firmante f
        JOIN expediente_area_tematica eat ON eat.expediente_id = f.expediente_id
        WHERE LOWER(f.nombre) LIKE :n
        GROUP BY eat.area ORDER BY c DESC
    """), {"n": f"%{nombre_legislador.lower()}%"})
    out["areas_dominantes"] = [{"area": a, "n_proyectos": c} for a, c in r.all()]

    # Cofirmantes recurrentes.
    r = await session.execute(text("""
        SELECT f2.nombre, f2.bloque, COUNT(DISTINCT f2.expediente_id) c
        FROM firmante f1
        JOIN firmante f2 ON f2.expediente_id = f1.expediente_id AND f2.id != f1.id
        WHERE LOWER(f1.nombre) LIKE :n
        GROUP BY f2.nombre, f2.bloque
        HAVING COUNT(DISTINCT f2.expediente_id) >= 2
        ORDER BY c DESC LIMIT 15
    """), {"n": f"%{nombre_legislador.lower()}%"})
    out["cofirmantes_recurrentes"] = [
        {"nombre": n, "bloque": b, "proyectos_compartidos": c}
        for n, b, c in r.all()
    ]

    # Votaciones (asunto + voto).
    r = await session.execute(text("""
        SELECT v.fecha, v.asunto, v.titulo_od, vl.voto, vl.bloque, v.aprobada,
               v.resultado_afirmativos, v.resultado_negativos, vl.que_dijo
        FROM voto_legislador vl
        JOIN votacion v ON v.id = vl.votacion_id
        WHERE LOWER(vl.legislador_nombre) LIKE :n
        ORDER BY v.fecha DESC
        LIMIT :lim
    """), {"n": f"%{nombre_legislador.lower()}%", "lim": max_vot})
    out["votaciones"] = [
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

    return out


async def llamar_llm(huella: dict):  # type: ignore[no-untyped-def]
    """Llama a Anthropic con la huella y devuelve el dict del perfil."""
    from anthropic import AsyncAnthropic
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_content = (
        f"Huella parlamentaria documental del legislador buscado "
        f"'{huella['nombre_buscado']}':\n\n"
        f"```json\n{json.dumps(huella, ensure_ascii=False, indent=2)[:30000]}\n```\n\n"
        "Generá el JSON del perfil opositor según las reglas."
    )
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = resp.content[0].text.strip()
    # Sacar fences ```json si los hay
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[: -3].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw), {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "modelo": settings.anthropic_model,
    }


async def main(args: argparse.Namespace) -> int:
    engine = create_async_engine(str(get_settings().database_url))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as s:
            huella = await fetch_huella(s, args.nombre, args.max_votaciones)
        if not huella["expedientes_firmados"] and not huella["votaciones"]:
            print(f"ERROR: no encontré actividad para '{args.nombre}'", file=sys.stderr)
            return 1
        log.info(
            "Huella: %d expedientes, %d votaciones, %d cofirmantes",
            len(huella["expedientes_firmados"]),
            len(huella["votaciones"]),
            len(huella["cofirmantes_recurrentes"]),
        )
        perfil, meta = await llamar_llm(huella)
    finally:
        await engine.dispose()

    print()
    print("=" * 78)
    print(f"PERFIL OPOSITOR INFERIDO — {args.nombre}")
    print(f"Modelo: {meta['modelo']}  |  In/Out tokens: "
          f"{meta['input_tokens']}/{meta['output_tokens']}")
    print("=" * 78)
    print(json.dumps(perfil, ensure_ascii=False, indent=2))
    print()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nombre", required=True,
                   help='Substring del nombre, ej: "JULIANO, PABLO" o "MANES"')
    p.add_argument("--max-votaciones", type=int, default=50,
                   help="Cuántas votaciones recientes incluir (default 50)")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
