# Spec 14 — Briefing pre-sesión

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/26-briefing-pre-sesion`

## Objetivo

Que **cada lunes a las 18hs** el jefe de asesores de un despacho reciba un
**PDF de 3 páginas** con todo lo que necesita para preparar la sesión del
miércoles. Hoy ese trabajo le toma 6-8 horas; queremos que con el briefing
le tome 30 minutos (revisar + ajustar, no investigar de cero).

Es la **killer feature** del MVP de Praxis Asesor. El resto de la app
existe para alimentar este PDF.

**Cliente prototipo:** despacho de Pablo Juliano (Democracia Para Siempre).

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Formato de salida | PDF, 3 páginas, listo para imprimir |
| Trigger v1 | Botón explícito "Generar briefing" desde la UI |
| Trigger v2 | Scheduler automático cada lunes 18hs + envío email |
| Carga del OD | Upload manual del HTML/PDF del bloque (v1) → scraping automático del portal HCDN (v2) |
| LLM | `FakeLlmProvider` por defecto (cero gasto). Sonnet 4.5 cuando Agustín lo enchufe |
| Votaciones nominales | **Adentro del MVP** — módulo nuevo, ver ADR 0005 |
| Cofirmantes naturales | Adentro — matching por keywords (v1) → embeddings (v2) |
| Antecedente más parecido | Adentro — heurística por título + tipo + área temática |
| Recomendación de voto | Heurística por bloque sobre votaciones nominales históricas |
| Comparación con peers | **Fuera** del briefing — vive solo en la ficha del expediente |
| Áreas temáticas | LLM call cacheado por expediente. 12 áreas predefinidas (educación, salud, justicia, trabajo, etc.) |

## Out of scope (v1)

- WhatsApp Business API para entrega.
- Generación de fundamentos completos (eso es spec 15 a futuro).
- Riesgo de quórum estimado (requiere histórico de presentismo + modelo).
- Resumen audio (texto a voz).
- Briefing multi-despacho (un asesor que trabaja para dos diputados).

## Estructura del PDF

### Página 1 — Resumen ejecutivo

Pensada para que el jefe de despacho lea en 2 minutos y se haga una idea.

```
┌─────────────────────────────────────────────────────────────┐
│ PRAXIS ASESOR · DESPACHO PABLO JULIANO (DPS)                │
│                                                             │
│ BRIEFING SESIÓN HCDN — Miércoles 3 de junio 2026, 14:00 hs │
│                                                             │
│ ▸ Tu despacho tiene 5 proyectos en el OD                    │
│   3 como autor · 2 como cofirmante                          │
│                                                             │
│ ▸ Alertas priorizadas                                       │
│                                                             │
│   🔴 ALTA   Proyecto 1247-D-2025 (Juliano autor) está en    │
│             condiciones de obtener media sanción hoy.       │
│             Bloque oficialista preanunció no acompañar.     │
│                                                             │
│   🟡 MEDIA  Proyecto 0982-D-2024 (Juliano autor) caduca en  │
│             17 días por Ley 13.640. Pedir prórroga antes    │
│             del viernes.                                    │
│                                                             │
│   🟡 MEDIA  Proyecto 1830-D-2025 entra en OD por primera    │
│             vez. Es del bloque rival y toca educación.      │
│                                                             │
│   🟢 BAJA   Proyecto 0411-D-2025 (Juliano cofirma) sumó     │
│             4 cofirmas nuevas esta semana.                  │
│                                                             │
│ ▸ Hay 38 proyectos más en el OD. Ver páginas siguientes.    │
└─────────────────────────────────────────────────────────────┘
```

Criterios de selección de alertas (jerarquía, top-5 por prioridad):

1. **🔴 ALTA**: proyecto del despacho a punto de votarse (media sanción / sanción).
2. **🔴 ALTA**: proyecto del despacho caduca en ≤ 30 días.
3. **🟡 MEDIA**: proyecto del despacho cambia de etapa (dictamen, giro, OD).
4. **🟡 MEDIA**: proyecto del bloque rival entra al OD en el área temática del despacho.
5. **🟢 BAJA**: cambios menores (cofirmas nuevas, comentarios, etc.).

### Página 2 — Proyectos del despacho

Una sección por cada proyecto del despacho que está en el OD.
Compacta — debe entrar ~4 proyectos por página.

```
┌─────────────────────────────────────────────────────────────┐
│ ── 1247-D-2025 · Educación como servicio estratégico ──     │
│                                                             │
│ Estado: media sanción HCDN · Días en etapa: 655             │
│ Autor principal: Pablo Juliano (DPS, Buenos Aires)          │
│                                                             │
│ ▸ Argumentos sugeridos (FakeLLM por ahora)                  │
│   • La educación es el principal vector de movilidad social │
│     en Argentina (datos: INDEC, SITEAL).                    │
│   • 7 provincias ya tienen leyes equivalentes; este         │
│     proyecto las unifica.                                   │
│   • Sin protección legal, el sistema queda expuesto a       │
│     decisiones discrecionales del PE.                       │
│                                                             │
│ ▸ Contraargumentos esperados                                │
│   • "Avanza sobre competencias provinciales".               │
│   • "Genera gasto público sin financiamiento claro".        │
│                                                             │
│ ▸ Quién más lo presentaría (cofirmantes naturales)          │
│   1. Diputada X (UCR) — firmó 3 proyectos similares.        │
│   2. Diputado Y (CC) — firmó 2 proyectos similares.         │
│   3. Diputado Z (FdT) — área específica afín.               │
│                                                             │
│ ▸ Antecedente más parecido                                  │
│   8245-D-2018 "Régimen educativo de garantías" —            │
│   sancionado 2020 con 142 votos. Mismo planteo central.     │
└─────────────────────────────────────────────────────────────┘
```

### Página 3 — Resto del OD por área temática

Para que el asesor pueda anticipar qué se va a tratar en el resto y sepa
cómo el despacho debería posicionarse.

```
┌─────────────────────────────────────────────────────────────┐
│ RESTO DEL ORDEN DEL DÍA (38 proyectos)                      │
│                                                             │
│ EDUCACIÓN (7)                                               │
│   • 1830-D-2025 Régimen de jornada extendida (PRO)          │
│     📍 Recomendación: NEGATIVO. Antecedente histórico:      │
│        7104-D-2022, similar, votado en contra por DPS.      │
│   • 1502-D-2025 Capacitación docente continua (UCR)         │
│     📍 Recomendación: A FAVOR. Alineado con plataforma.     │
│   • [otros 5 proyectos cortos]                              │
│                                                             │
│ SALUD (6)                                                   │
│   ...                                                       │
│                                                             │
│ JUSTICIA (4)                                                │
│   ...                                                       │
│                                                             │
│ [otras áreas con 1-3 proyectos: agrupadas como "OTROS"]     │
└─────────────────────────────────────────────────────────────┘
```

## Fuentes de datos

| Dato | Fuente | Estado actual |
|---|---|---|
| Expedientes + trámite + firmantes | `expediente` table | ✅ |
| Estado inferido + caducidad | feat/25 | ✅ |
| Seguimientos del despacho | `seguimiento_expediente` table | ✅ |
| Orden del día (lista de expedientes a tratar) | Upload manual (v1) o scraping HCDN (v2) | ❌ — modelo nuevo |
| Votaciones nominales históricas (cómo votó cada bloque) | Scraping del portal HCDN | ❌ — ver ADR 0005 |
| Área temática de cada expediente | LLM call cacheado | ❌ — usa `LlmProvider` |
| Cofirmantes naturales | Matching por keywords + bloques | ❌ — algoritmo nuevo |
| Antecedente más parecido | Búsqueda por título + tipo + área | ❌ — algoritmo nuevo |
| Argumentos sugeridos | `LlmProvider.generar_argumentos(expediente)` | ❌ — extender puerto |
| Contraargumentos esperados | Idem | ❌ — extender puerto |

## Modelo de dominio nuevo

```python
@dataclass(frozen=True, slots=True)
class OrdenDelDia:
    """Lista de expedientes a tratar en una sesión específica."""
    id: UUID | None
    camara: Camara
    fecha_sesion: date
    hora_sesion: time | None
    expedientes_ids: list[UUID]   # referencia a Expediente
    fuente: str                    # "upload_manual" | "scraping_hcdn"
    creado_en: datetime

@dataclass(frozen=True, slots=True)
class AlertaBriefing:
    """Un ítem destacable que aparece en la página 1 del briefing."""
    prioridad: Literal["alta", "media", "baja"]
    titulo: str
    detalle: str
    expediente_id: UUID | None

@dataclass(frozen=True, slots=True)
class SeccionProyectoBriefing:
    """Una sección de página 2 (un proyecto del despacho)."""
    expediente_id: UUID
    rol_despacho: Literal["autor", "cofirmante"]
    argumentos: list[str]                # 3 bullets
    contraargumentos: list[str]          # 2 bullets
    cofirmantes_naturales: list[dict]    # [{nombre, bloque, razon}]
    antecedente_mas_parecido: dict | None  # {numero, titulo, resultado}

@dataclass(frozen=True, slots=True)
class SeccionAreaBriefing:
    """Una sección de página 3 (un área temática)."""
    area: str                             # "educacion", "salud", etc.
    expedientes: list[dict]               # [{numero, titulo, autor_bloque, recomendacion, razon}]

@dataclass(frozen=True, slots=True)
class Briefing:
    """El briefing completo, listo para renderizar a PDF."""
    id: UUID | None
    despacho_id: UUID
    orden_del_dia_id: UUID
    generado_en: datetime
    modelo_llm: str                       # "fake" | "claude-sonnet-4-5-..."
    # Página 1
    proyectos_del_despacho_total: int
    proyectos_como_autor: int
    proyectos_como_cofirmante: int
    alertas: list[AlertaBriefing]
    # Página 2
    secciones_proyectos: list[SeccionProyectoBriefing]
    # Página 3
    secciones_areas: list[SeccionAreaBriefing]
    # Persistencia
    pdf_bytes: bytes | None               # cache opcional del PDF generado
```

## Algoritmos clave

### Clasificación temática

Por cada expediente, el `LlmProvider` devuelve el área de las 12 predefinidas:

```
educacion, salud, trabajo, seguridad, justicia, economia,
ambiente, derechos_humanos, infraestructura, transporte,
relaciones_exteriores, otros
```

Se cachea en una nueva tabla `expediente_area_tematica(expediente_id PK, area, modelo, prompt_version, generado_en)`. Inferencia perezosa: solo se calcula cuando el expediente aparece en un OD.

`FakeLlmProvider` usa keywords sobre título + sumario.

### Cofirmantes naturales

Para un expediente E del despacho:

1. Buscar expedientes con misma área temática + último año.
2. De esos, listar los firmantes (excluyendo Juliano y bloque del despacho).
3. Rankear por cantidad de proyectos similares firmados.
4. Devolver top-5 con bloque + razón.

Heurística v1: similitud = (misma área temática) + (mismo tipo) + (palabra clave del título compartida).

### Antecedente más parecido

Para un expediente E:

1. Buscar todos los expedientes históricos con misma área temática + mismo tipo + estado terminal (sancionado / caduco / archivado).
2. Rankear por similitud del título (tokens compartidos, Jaccard simple).
3. Devolver el top-1 con su resultado.

Si no hay ninguno con similitud > umbral (Jaccard > 0.3), devolver `None`.

### Recomendación de voto (página 3)

Para un expediente E no-del-despacho que aparece en el OD:

1. Buscar antecedente más parecido (algoritmo anterior).
2. Si lo hay y tiene votación nominal del despacho/bloque registrada → usar esa decisión como recomendación.
3. Si no hay antecedente → recomendar "abstención" + razón "sin antecedente histórico claro".

Requiere **votaciones nominales** (ADR 0005).

## Puertos y casos de uso

```python
class LlmProvider(ABC):
    # ya existe
    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str: ...

    # nuevos en feat/26
    async def generar_argumentos(self, expediente: Expediente, *, contraargumentos: bool = False) -> list[str]: ...
    async def clasificar_area_tematica(self, expediente: Expediente) -> str: ...


class OrdenDelDiaRepository(ABC):
    async def crear(self, od: OrdenDelDia) -> OrdenDelDia: ...
    async def buscar_por_id(self, id: UUID) -> OrdenDelDia | None: ...
    async def ultimo_por_camara(self, camara: Camara) -> OrdenDelDia | None: ...


class BriefingRepository(ABC):
    async def crear(self, b: Briefing) -> Briefing: ...
    async def buscar_por_od_y_despacho(self, od_id: UUID, despacho_id: UUID) -> Briefing | None: ...


class GenerarBriefing:
    """Caso de uso principal. Orquesta todo."""
    async def execute(
        self,
        *,
        despacho_id: UUID,
        orden_del_dia_id: UUID,
        regenerar: bool = False,
    ) -> Briefing:
        # 1. Cache hit → devolver
        # 2. Cargar OD + expedientes
        # 3. Cruzar con seguimientos del despacho → proyectos_del_despacho
        # 4. Por cada proyecto del despacho: secciones de página 2
        # 5. Construir alertas (página 1)
        # 6. Clasificar áreas + organizar página 3
        # 7. Persistir Briefing
        # 8. Devolver
```

El renderizado del PDF vive en `infrastructure/pdf/` (un adaptador, no en application).

## Endpoints API

```
POST /api/v1/ordenes-del-dia
     body: { camara, fecha_sesion, hora_sesion, expedientes_numeros[] }
     → crea un OD a partir de números (texto plano que el asesor pega)

GET  /api/v1/ordenes-del-dia/{id}

POST /api/v1/briefings
     body: { orden_del_dia_id, regenerar?: bool }
     → genera (o devuelve cacheado) el Briefing para el despacho del request

GET  /api/v1/briefings/{id}
GET  /api/v1/briefings/{id}/pdf      → bytes
```

## UI

Una sola ruta nueva: `/briefings`

- Lista los briefings del despacho ordenados por fecha de sesión.
- Botón "Nuevo briefing" → abre wizard de 2 pasos:
  1. Pegar/uploadear el OD (texto plano con números de expediente, uno por línea).
  2. Mostrar preview del briefing en HTML + botón "Descargar PDF".

Después del v2 (scraping automático del OD), el botón "Nuevo briefing" agarra el OD del último portal scrapeado automáticamente.

## Flujo end-to-end (v1)

```
Lunes 18:00 — el bloque de Juliano publica el OD del miércoles
   ↓
Asesor abre Praxis → /briefings → "Nuevo briefing"
   ↓
Pega los 43 números del OD (texto plano)
   ↓
Backend crea OrdenDelDia
   ↓
Asesor click "Generar briefing"
   ↓
GenerarBriefing.execute():
   • Para cada expediente del OD: asegurar área temática (LLM si falta)
   • Cruzar con seguimientos del despacho → 5 proyectos
   • Para cada proyecto del despacho:
       - argumentos via LlmProvider
       - contraargumentos via LlmProvider
       - cofirmantes naturales (algoritmo local)
       - antecedente más parecido (algoritmo local)
   • Construir alertas (página 1) según jerarquía
   • Organizar página 3 por área + recomendación (votaciones nominales)
   • Persistir Briefing
   ↓
UI muestra HTML preview → asesor revisa → descarga PDF
   ↓
Asesor lo imprime y lo lleva el martes a la reunión de bloque
```

## Dependencias previas a construir

1. **Votaciones nominales** — bloqueante. Ver `ADR 0005`. **3-5 días**.
2. **Clasificación temática** — feat/27 chico. **1 día**.
3. **Cofirmantes naturales + antecedente más parecido** — feat/28. **1-2 días**.
4. **OrdenDelDia + Briefing + GenerarBriefing** — feat/29. **2-3 días**.
5. **Render PDF + UI** — feat/30. **2 días**.

Total estimado: **9-13 días de trabajo**.

## Métricas de éxito

- **Funcional**: un jefe de asesores genera y descarga el briefing para una sesión real sin asistencia técnica.
- **Tiempo de generación**: < 60 segundos contra Sonnet 4.5 real, < 5 segundos con FakeLlm.
- **Tiempo de revisión humana**: ≤ 30 minutos (lo medimos con Agustín contra una sesión real de Juliano).
- **Vendible**: 3 de cada 5 despachos a los que se les muestre, dicen "esto lo pagaría". Muestreo informal de Agustín.

## Limitaciones conocidas

- **Áreas temáticas son 12, fijas**. Los proyectos transversales se etiquetan como "otros" o forzados al mejor match. Aceptable para v1.
- **Antecedente más parecido es heurística**, no semántica real. Va a errar en proyectos donde el título no comparte tokens con el antecedente (ej: paráfrasis). Mejorable con embeddings (v2).
- **Recomendación de voto asume que el bloque del despacho vota consistente**. Si Juliano es disidente respecto a DPS en algún tema, la recomendación va a estar mal. Se documenta en la salida ("recomendación basada en bloque, validar con jefe").
- **Sin riesgo de quórum**: requiere modelo de presentismo. Out of scope v1.
- **Un solo despacho por usuario en v1**. Multi-despacho se modeló pero el briefing asume `current_context.despacho_id`.

## Próximos pasos (post-v1)

- v2: scraping automático del OD del portal HCDN (lo publica martes mañana).
- v2: scheduler cada lunes 18hs + envío por email del PDF.
- v2: embeddings para cofirmantes + antecedentes (mejor calidad).
- v3: WhatsApp Business para entrega del briefing.
- v3: spec 15 — asistente de redacción de fundamentos.
