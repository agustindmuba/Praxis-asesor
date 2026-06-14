"""Seed inicial de efemérides argentinas + internacionales (feat-53.2).

Lista curada manualmente combinando:
- Calendario de la Diputada Carla Carrizo (UCR), año 2022 — priorización
  política real de un despacho radical.
- Efemérides argentinas oficiales (leyes y decretos declaratorios).
- Días internacionales ONU más reconocidos.
- Aniversarios históricos argentinos relevantes.

Categorías de relevancia:
  ALTA   → aparece destacada en dashboard + briefing WhatsApp del día
  MEDIA  → aparece en /efemerides y en briefing si hay espacio
  BAJA   → solo en /efemerides cuando el asesor consulta activamente

Uso:
    uv run python -m scripts.seed_efemerides

Idempotente: usa ON CONFLICT DO NOTHING en el INSERT (clave única
(mes, dia, titulo)). Re-ejecutable sin riesgo.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from praxis.config import get_settings

log = structlog.get_logger()


# (mes, dia, titulo, tipo, relevancia, descripcion, fuente, areas, anio_unico)
EFEMERIDES: list[tuple[int, int, str, str, str, str | None, str | None, list[str], int | None]] = [
    # --- ENERO ---
    (1, 1, "Año Nuevo", "tematica", "media", None, "Costumbre", [], None),
    (1, 6, "Día de Reyes", "tematica", "baja", None, "Costumbre", [], None),
    (1, 27, "Día Internacional de Conmemoración de las Víctimas del Holocausto", "internacional", "alta",
     "ONU — recuerdo de las víctimas del nazismo.",
     "ONU Resolución 60/7 (2005)", ["derechos_humanos"], None),
    # --- FEBRERO ---
    (2, 11, "Día Internacional de las Mujeres y las Niñas en la Ciencia", "internacional", "alta",
     "Promoción de la equidad de género en STEM.",
     "ONU Resolución A/RES/70/212", ["educacion", "derechos_humanos"], None),
    (2, 20, "Día Mundial de la Justicia Social", "internacional", "media",
     None, "ONU", ["derechos_humanos", "trabajo"], None),
    (2, 24, "Día Internacional de la Lengua Materna", "internacional", "baja",
     None, "UNESCO", ["educacion"], None),
    # --- MARZO ---
    (3, 3, "Día Mundial de la Naturaleza", "internacional", "media",
     None, "ONU", ["ambiente"], None),
    (3, 5, "Día Mundial de la Eficiencia Energética", "internacional", "media",
     None, "ONU", ["ambiente", "economia"], None),
    (3, 7, "Día Nacional de Lucha contra la Violencia de Género en los Medios de Comunicación",
     "nacional", "alta",
     "Ley 26.485 — visibilizar violencia mediática contra mujeres.",
     "Ley 26.485", ["derechos_humanos"], None),
    (3, 8, "Día Internacional de la Mujer", "internacional", "alta",
     "Conmemoración de las luchas por la igualdad de género.",
     "ONU Resolución 32/142 (1977)", ["derechos_humanos", "trabajo"], None),
    (3, 11, "Día Mundial de la Endometriosis", "internacional", "media",
     None, "Costumbre médica internacional", ["salud", "derechos_humanos"], None),
    (3, 17, "Día Nacional de las Personas Trans / Día Internacional contra la Discriminación Racial",
     "nacional", "alta",
     None, "Costumbre", ["derechos_humanos"], None),
    (3, 24, "Día Nacional de la Memoria por la Verdad y la Justicia", "nacional", "alta",
     "Conmemoración del Golpe de Estado de 1976.",
     "Ley 26.085 (2006)", ["derechos_humanos", "justicia"], None),
    (3, 31, "Día Internacional de la Visibilidad Trans", "internacional", "alta",
     None, "Costumbre internacional", ["derechos_humanos"], None),
    # --- ABRIL ---
    (4, 2, "Día del Veterano y los Caídos en Malvinas", "nacional", "alta",
     "Aniversario del desembarco argentino en las Islas Malvinas (1982).",
     "Ley 25.370", ["relaciones_exteriores"], None),
    (4, 7, "Día Mundial de la Salud", "internacional", "media",
     None, "OMS", ["salud"], None),
    (4, 11, "Día del Investigador Científico (Argentina) / Día Mundial de la Ciencia y la Tecnología",
     "nacional", "media",
     "Nacimiento de Bernardo Houssay (1887), premio Nobel.",
     "Decreto", ["educacion"], None),
    (4, 15, "Día Mundial del Arte", "internacional", "baja", None, "UNESCO", [], None),
    (4, 19, "Día Internacional para la Lucha contra el Maltrato Infantil", "internacional", "alta",
     None, "ONU", ["derechos_humanos"], None),
    (4, 22, "Día Internacional de la Madre Tierra", "internacional", "alta",
     None, "ONU Resolución 63/278", ["ambiente"], None),
    (4, 23, "Día Internacional del Libro y del Derecho de Autor", "internacional", "media",
     None, "UNESCO", ["educacion"], None),
    # --- MAYO ---
    (5, 1, "Día Internacional de los Trabajadores", "internacional", "alta",
     "Conmemoración de los mártires de Chicago (1886).",
     "Costumbre internacional", ["trabajo"], None),
    (5, 3, "Día Mundial de la Libertad de Prensa", "internacional", "alta",
     None, "ONU", ["derechos_humanos", "justicia"], None),
    (5, 9, "Sanción de la Ley de Identidad de Género (Argentina)", "nacional", "alta",
     "Ley 26.743 — primera del mundo en reconocer identidad autopercibida sin patologización.",
     "Ley 26.743 (2012)", ["derechos_humanos", "salud"], None),
    (5, 13, "Día Nacional del Niño Hospitalizado", "nacional", "media",
     None, "Costumbre", ["salud", "derechos_humanos"], None),
    (5, 15, "Día Internacional de la Familia", "internacional", "baja",
     None, "ONU", ["derechos_humanos"], None),
    (5, 17, "Día Internacional contra la Discriminación por Orientación Sexual e Identidad de Género (IDAHOT)",
     "internacional", "alta",
     "Aniversario de la despatologización de la homosexualidad por la OMS (1990).",
     "Costumbre internacional", ["derechos_humanos"], None),
    (5, 18, "Día Mundial del Reciclaje", "internacional", "media",
     None, "Costumbre", ["ambiente"], None),
    (5, 22, "Día Internacional de la Biodiversidad", "internacional", "media",
     None, "ONU", ["ambiente"], None),
    (5, 25, "Día de la Revolución de Mayo (Argentina)", "nacional", "alta",
     "Aniversario de la Revolución de Mayo de 1810.",
     "Decreto nacional", [], None),
    (5, 28, "Día Internacional de Acción por la Salud de las Mujeres", "internacional", "alta",
     None, "OMS", ["salud", "derechos_humanos"], None),
    # --- JUNIO ---
    (6, 1, "Día Mundial de la Infancia", "internacional", "media",
     None, "ONU", ["derechos_humanos"], None),
    (6, 3, "Día Nacional 'Ni Una Menos'", "nacional", "alta",
     "Aniversario de la primera movilización argentina contra los femicidios (2015).",
     "Costumbre", ["derechos_humanos"], None),
    (6, 5, "Día Mundial del Medio Ambiente", "internacional", "alta",
     None, "ONU", ["ambiente"], None),
    (6, 7, "Día del Periodista (Argentina)", "nacional", "media",
     "Aniversario de la 'Gazeta de Buenos Ayres' (1810).",
     "Costumbre", ["derechos_humanos"], None),
    (6, 12, "Día Mundial contra el Trabajo Infantil", "internacional", "alta",
     None, "OIT", ["trabajo", "derechos_humanos"], None),
    (6, 14, "Día Mundial del Donante de Sangre", "internacional", "media",
     None, "OMS", ["salud"], None),
    (6, 15, "Día Nacional del Libro (Argentina)", "nacional", "baja",
     None, "Decreto", ["educacion"], None),
    (6, 17, "Día de la Reforma Universitaria (Argentina)", "nacional", "media",
     "Aniversario del Manifiesto de la Reforma Universitaria de 1918.",
     "Costumbre", ["educacion"], None),
    (6, 20, "Día de la Bandera (Argentina)", "nacional", "alta",
     "Fallecimiento de Manuel Belgrano (1820).",
     "Ley 12.361", [], None),
    (6, 28, "Día Internacional del Orgullo LGBT+", "internacional", "alta",
     "Aniversario de la revuelta de Stonewall (1969).",
     "Costumbre internacional", ["derechos_humanos"], None),
    # --- JULIO ---
    (7, 9, "Día de la Independencia (Argentina)", "nacional", "alta",
     "Aniversario de la Declaración de la Independencia (1816).",
     "Ley nacional", [], None),
    (7, 11, "Día Mundial de la Población", "internacional", "media",
     None, "ONU", ["salud"], None),
    (7, 18, "Recordatorio del atentado a la AMIA-DAIA / Día Internacional de Nelson Mandela",
     "nacional", "alta",
     "Aniversario del atentado a la AMIA (1994).",
     "Ley nacional", ["derechos_humanos", "justicia"], None),
    (7, 20, "Día del Amigo (Argentina)", "tematica", "baja",
     None, "Costumbre", [], None),
    (7, 30, "Día Mundial contra la Trata de Personas", "internacional", "alta",
     None, "ONU", ["derechos_humanos", "justicia"], None),
    # --- AGOSTO ---
    (8, 9, "Día Internacional de los Pueblos Indígenas", "internacional", "media",
     None, "ONU", ["derechos_humanos"], None),
    (8, 12, "Día Internacional de la Juventud", "internacional", "media",
     None, "ONU", ["educacion", "derechos_humanos"], None),
    (8, 17, "Aniversario del fallecimiento de San Martín (Argentina)", "nacional", "alta",
     "José de San Martín (1850).",
     "Ley nacional", [], None),
    (8, 19, "Día Mundial de la Asistencia Humanitaria", "internacional", "media",
     None, "ONU", ["derechos_humanos"], None),
    (8, 26, "Día Internacional de la Igualdad de las Mujeres", "internacional", "alta",
     "Aniversario del voto femenino en EE.UU. (1920).",
     "Costumbre", ["derechos_humanos"], None),
    # --- SEPTIEMBRE ---
    (9, 8, "Día Internacional de la Alfabetización", "internacional", "media",
     None, "UNESCO", ["educacion"], None),
    (9, 11, "Día del Maestro (Argentina)", "nacional", "alta",
     "Aniversario del fallecimiento de Sarmiento (1888).",
     "Decreto", ["educacion"], None),
    (9, 15, "Día Internacional de la Democracia", "internacional", "media",
     None, "ONU", ["justicia", "derechos_humanos"], None),
    (9, 16, "Día Nacional de la Juventud (Argentina) — Noche de los Lápices",
     "nacional", "alta",
     "Aniversario del secuestro de estudiantes secundarios platenses en 1976.",
     "Ley 26.318", ["derechos_humanos", "educacion"], None),
    (9, 21, "Día Internacional de la Paz / Día del Estudiante (Argentina)", "nacional", "alta",
     None, "ONU + Costumbre AR", ["educacion"], None),
    (9, 23, "Día Internacional contra la Explotación Sexual y Trata", "internacional", "alta",
     None, "ONU", ["derechos_humanos", "justicia"], None),
    (9, 28, "Día por la Despenalización del Aborto en América Latina y el Caribe",
     "internacional", "alta",
     None, "Movimiento regional", ["derechos_humanos", "salud"], None),
    # --- OCTUBRE ---
    (10, 1, "Día Internacional de las Personas de Edad", "internacional", "media",
     None, "ONU", ["derechos_humanos", "salud"], None),
    (10, 2, "Día Internacional de la No Violencia", "internacional", "media",
     "Natalicio de Mahatma Gandhi.",
     "ONU", ["derechos_humanos"], None),
    (10, 10, "Día Mundial de la Salud Mental", "internacional", "alta",
     None, "OMS", ["salud"], None),
    (10, 11, "Día de la Niña", "internacional", "alta",
     None, "ONU", ["derechos_humanos"], None),
    (10, 12, "Día del Respeto a la Diversidad Cultural (Argentina)", "nacional", "alta",
     None, "Decreto 1584/2010", ["derechos_humanos"], None),
    (10, 16, "Día Mundial de la Alimentación", "internacional", "media",
     None, "FAO", ["salud"], None),
    (10, 17, "Día Internacional para la Erradicación de la Pobreza", "internacional", "media",
     None, "ONU", ["derechos_humanos", "economia"], None),
    (10, 17, "Día de la Lealtad Peronista (Argentina)", "nacional", "media",
     "Conmemoración del 17 de octubre de 1945.",
     "Costumbre política", [], None),
    (10, 19, "Día Mundial de la Lucha contra el Cáncer de Mama", "internacional", "alta",
     None, "OMS", ["salud", "derechos_humanos"], None),
    (10, 25, "Día Internacional de las Personas con Discapacidad (visibilización)",
     "internacional", "media",
     None, "Costumbre", ["derechos_humanos"], None),
    # --- NOVIEMBRE ---
    (11, 14, "Día Mundial de la Diabetes", "internacional", "media",
     None, "OMS", ["salud"], None),
    (11, 16, "Día Internacional de la Tolerancia", "internacional", "media",
     None, "UNESCO", ["derechos_humanos"], None),
    (11, 19, "Día Mundial para la Prevención del Abuso contra los Niños/as",
     "internacional", "alta",
     None, "ONU", ["derechos_humanos"], None),
    (11, 20, "Día Universal del Niño", "internacional", "media",
     None, "ONU", ["derechos_humanos"], None),
    (11, 25, "Día Internacional de la Eliminación de la Violencia contra la Mujer",
     "internacional", "alta",
     "Conmemoración del asesinato de las hermanas Mirabal (1960).",
     "ONU", ["derechos_humanos", "justicia"], None),
    # --- DICIEMBRE ---
    (12, 1, "Día Mundial de la Lucha contra el SIDA", "internacional", "alta",
     None, "OMS", ["salud", "derechos_humanos"], None),
    (12, 3, "Día Internacional de las Personas con Discapacidad", "internacional", "alta",
     None, "ONU", ["derechos_humanos"], None),
    (12, 10, "Día de los Derechos Humanos / Día de la Restauración de la Democracia (Argentina)",
     "nacional", "alta",
     "Aniversario de la Declaración Universal de DDHH (1948) y retorno a la democracia en Argentina (1983).",
     "ONU + Costumbre AR", ["derechos_humanos", "justicia"], None),
    (12, 18, "Día Internacional del Migrante", "internacional", "media",
     None, "ONU", ["derechos_humanos"], None),
    (12, 20, "Aniversario de la rebelión popular de 2001 (Argentina)",
     "aniversario", "media",
     "Conmemoración de las jornadas del 19 y 20 de diciembre de 2001.",
     "Costumbre", [], None),
    (12, 25, "Navidad", "tematica", "baja", None, "Costumbre", [], None),
]


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[seed-efemerides] DB: {settings.database_url}")
    print(f"[seed-efemerides] Efemérides a sembrar: {len(EFEMERIDES)}")
    print()

    creadas = 0
    duplicadas = 0
    errores = 0

    try:
        async with sm() as session:
            for (
                mes, dia, titulo, tipo, relevancia,
                descripcion, fuente, areas, anio_unico,
            ) in EFEMERIDES:
                try:
                    result = await session.execute(
                        text("""
                            INSERT INTO efemeride (
                                id, mes, dia, titulo, tipo, relevancia,
                                descripcion, fuente, areas_tematicas,
                                anio_unico
                            )
                            VALUES (
                                :id, :mes, :dia, :titulo, :tipo, :relevancia,
                                :descripcion, :fuente, CAST(:areas AS json),
                                :anio_unico
                            )
                            ON CONFLICT (mes, dia, titulo) DO NOTHING
                            RETURNING id
                        """),
                        {
                            "id": uuid4(),
                            "mes": mes,
                            "dia": dia,
                            "titulo": titulo,
                            "tipo": tipo,
                            "relevancia": relevancia,
                            "descripcion": descripcion,
                            "fuente": fuente,
                            "areas": __import__("json").dumps(areas),
                            "anio_unico": anio_unico,
                        },
                    )
                    row = result.first()
                    if row:
                        creadas += 1
                        print(f"  + {mes:02d}-{dia:02d}: {titulo[:65]}")
                    else:
                        duplicadas += 1
                except Exception as exc:
                    errores += 1
                    print(f"  ✗ {mes:02d}-{dia:02d} {titulo[:30]}: {exc}")
            await session.commit()
    finally:
        with suppress(Exception):
            await engine.dispose()

    print()
    print("=" * 60)
    print(f"  Creadas:    {creadas}")
    print(f"  Duplicadas: {duplicadas}")
    print(f"  Errores:    {errores}")
    print("=" * 60)
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
