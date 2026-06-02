# Spec 15 — Resumen accionable del Boletín Oficial

**Estado:** borrador · **Owner:** Agustín · **Branch sugerida:** `feat/39-resumen-bo`

## Problema

Hoy un asesor parlamentario que quiere estar al día con el Boletín Oficial
tiene dos opciones malas:

1. **Leer el BO entero todos los días.** Inviable: ~60-150 normas/día entre
   leyes, decretos, resoluciones, designaciones y avisos oficiales. Aún
   filtrando por sección, son ~30 min de lectura solo para descartar.
2. **Confiar en que algún medio levante lo importante.** El medio prioriza
   lo que es noticiable, no lo que es accionable para un despacho legislativo
   específico (ej. una resolución del Ministerio de Salud que toca a un
   proyecto del despacho rara vez es noticia, pero sí es accionable).

El despacho necesita un **resumen diario, filtrado y priorizado**, que le
diga "estas 3-5 normas de hoy te importan, por estas razones concretas, y
acá tenés el link al texto original". Tiene que llegar **antes de la
reunión matinal del despacho** (~8:00 AM), no a la noche.

## Usuario y caso de uso

**Usuario primario:** Jefe de despacho / coordinador legislativo del
despacho. Es quien arma la agenda diaria del legislador y prepara los
inputs para las reuniones de bloque.

**Usuario secundario:** Legislador titular del despacho. Solo lee el
resumen si algo lo afecta directamente (ej. una designación en un área
donde tiene proyectos).

**Cliente prototipo:** despacho de Pablo Juliano (Democracia Para Siempre).

Caso de uso central:

```
DADO  el BO publicado del día anterior (~150 normas en secciones
      Legislación, Designaciones, Avisos oficiales),
Y     el perfil de intereses del despacho (temas marcados, comisiones
      del legislador, expedientes en trámite, distritos observados),
CUANDO son las 7:30 AM hora Argentina,
ENTONCES Praxis envía al despacho un único mensaje (app + WhatsApp)
         que destaca las 3-5 normas accionables del día con:
           - tipo + número de norma
           - organismo emisor
           - 1 línea de por qué le importa al despacho
           - link al texto original en boletinoficial.gob.ar
```

## Decisiones tomadas (del prompt de Agustín)

| Tema | Decisión |
|---|---|
| Fuente | `boletinoficial.gob.ar` (no agregadores) |
| Secciones cubiertas en MVP | Legislación (leyes, decretos, resoluciones), Designaciones en cargos públicos, Avisos oficiales |
| Modo de captura | Scraping respetuoso programado, una corrida nocturna ~5:00 AM ART del BO del día anterior |
| Clasificación IA | Tema + organismo emisor + tipo + **score de accionabilidad por despacho** |
| Entrega | Parte del envío único de las 7:30 AM junto con noticias (ver spec 16) |
| Canales | App (vista web) + WhatsApp (notificación con titulares + link a app) |

## Decisiones de dominio NUEVAS (resueltas)

- **D1** → **Perfil híbrido sembrado + editable.** Al onboarding del
  despacho se siembra automáticamente con (a) comisiones del legislador
  del padrón, (b) áreas temáticas de los expedientes que el despacho
  sigue, (c) distrito de la banca. El asesor lo edita libremente desde
  `/configuracion`. Si no edita, se recalcula la siembra de fondo
  cuando cambian sus seguimientos.
- **D2** → **Texto completo SE persiste para uso interno**, en tabla
  aparte `norma_bo_texto(norma_id PK, texto, capturado_en)`. Nunca se
  expone en endpoints/UI: el usuario ve metadata + link al BO oficial.
  Se usa para clasificación, detección de referencias legales y futura
  búsqueda full-text. El BO es dominio público — sin riesgo legal.
- **D3** → **Retención forever** para `NormaBO`, su texto y la
  clasificación. El valor del histórico crece con el tiempo (cruzar
  normas viejas con expedientes nuevos) y el costo de storage es
  trivial.

## Solución propuesta

Pipeline diario nocturno + entrega coordinada:

```
05:00 ART  ScrapeBoletinOficial.run(fecha=ayer)
           ↓ por sección, paginar, parsear cada norma
           ↓ NormaBO[] persistida (sin clasificar todavía)

05:30 ART  ClasificarNormasBO.run(fecha=ayer)
           ↓ LLM batch por norma (con cache por hash de sumario)
           ↓ ClasificacionNormaBO[]: tema, organismo, tipo, palabras_clave

06:00 ART  EvaluarAccionabilidadPorDespacho.run(fecha=ayer)
           ↓ por cada despacho activo, cruzar perfil de interés con
             clasificaciones del día → score 0–100 + razón en una frase

07:00 ART  ArmarBriefingDiario.run(fecha=hoy)
           ↓ junta accionables BO (top-5 por score) + noticias relevantes
             del último ciclo de 24hs (ver spec 16)
           ↓ Genera contenido del briefing diario (markdown + payload
             estructurado para plantilla WhatsApp)

07:30 ART  EntregarBriefingDiario.run()
           ↓ por cada despacho con destinatarios opt-in: enviar por canal
           ↓ Persistir EnvioBriefingDiario + EnvioWhatsApp (auditoría)
```

Cada paso es idempotente y reanudable: si falla a las 5:00, no rompe la
entrega 07:30 (queda sin BO ese día, sólo con noticias). Cada `NormaBO`
queda persistida una vez aunque se reintente.

## Estructura del entregable

### Mensaje en la app (`/briefing-diario` o card en `/dashboard`)

```
┌─────────────────────────────────────────────────────────────┐
│ BRIEFING DIARIO — Martes 3 de junio 2026                    │
│                                                             │
│ 📜 BOLETÍN OFICIAL (5 normas accionables de 142 publicadas) │
│                                                             │
│ 🔴 Decreto 412/2026 — Modifica régimen de jubilaciones      │
│    docentes nacionales.                                     │
│    ▸ Toca tu proyecto 1247-D-2025 (educación). Revisar      │
│      si necesita actualización antes del miércoles.         │
│    [Ver en BO →]                                            │
│                                                             │
│ 🟡 Resolución 88/2026 SE — Designa nuevo subsecretario      │
│    de Coordinación Educativa.                               │
│    ▸ Es contacto natural para tus proyectos del área.       │
│    [Ver en BO →]                                            │
│                                                             │
│ 🟡 Ley 27.812 — Capacitación docente continua.              │
│    ▸ Sancionada (tu despacho la cofirmó en HCDN).           │
│    [Ver en BO →]                                            │
│                                                             │
│ 🟢 Resolución 14/2026 MJ — Reglamentación parcial Ley       │
│    24.660 (régimen de ejecución penal).                     │
│    ▸ Toca tu área "justicia"; sin expediente en trámite.    │
│    [Ver en BO →]                                            │
│                                                             │
│ 🟢 Aviso Oficial — Llamado a concurso público (SAIJ).       │
│    ▸ Toca tu área "justicia".                               │
│    [Ver en BO →]                                            │
│                                                             │
│ Ver las 142 normas del día →                                │
└─────────────────────────────────────────────────────────────┘
```

Vista de **detalle** (click en una norma) muestra: metadata estructurada
+ link al texto original + lista de expedientes del despacho que la
clasificación cree que toca. **No reproduce el cuerpo del decreto/ley**
(restricción de producto + simplicidad).

### Mensaje por WhatsApp

Plantilla pre-aprobada por Meta (ver spec 17). Cuerpo único de ~7 líneas
con los titulares + un botón a la app:

```
Briefing Praxis · Mar 03/06
📜 BO: 5 normas accionables (de 142)
• Decreto 412/2026 jubilaciones docentes (🔴)
• Res 88/2026 SE designa subsec. educativo (🟡)
• Ley 27.812 capacitación docente (🟡)
+ 2 más en la app
[Abrir Praxis Asesor]
```

(El WhatsApp también incluye lo de noticias del día — spec 16; este es
sólo el fragmento BO.)

## Modelo de dominio nuevo

```python
@dataclass(frozen=True, slots=True)
class NormaBO:
    """Una norma publicada en el BO. Snapshot al momento del scrape."""
    id: UUID | None
    fecha_publicacion: date
    seccion: Literal["legislacion", "designaciones", "avisos_oficiales"]
    tipo_norma: str             # "decreto", "ley", "resolucion", "decision_administrativa", "aviso", etc.
    numero_norma: str           # "412/2026", "27.812", "88/2026"
    organismo_emisor: str       # "Poder Ejecutivo Nacional", "Ministerio de Justicia", etc.
    sumario: str                # bajada oficial del BO (esto sí es del Estado, no copyrighteado)
    url_oficial: str            # link al PDF/HTML en boletinoficial.gob.ar
    hash_sumario: str           # sha256 para dedup + cache de clasificación
    capturado_en: datetime
    # Texto completo vive en tabla aparte `norma_bo_texto(norma_id PK,
    # texto, capturado_en)` — decisión D2. Nunca se expone en UI ni
    # endpoints; sólo se consulta para clasificación y referencia
    # legal interna.

@dataclass(frozen=True, slots=True)
class ClasificacionNormaBO:
    """Clasificación general de la norma (no depende del despacho)."""
    id: UUID | None
    norma_id: UUID
    area_tematica: str          # de las 12 ya definidas en feat/27
    palabras_clave: list[str]   # 3-7 tokens, generados por LLM
    afecta_expedientes_hcdn: bool   # heurística: la norma menciona "Ley NNN", "Expte. NNN-X-YYYY", etc.
    referencias_legales: list[str]  # ["Ley 24.660", "Decreto 1.422/2020"]
    modelo: str
    prompt_version: str
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class NormaBOAccionable:
    """La misma norma vista desde el ángulo de un despacho concreto."""
    norma_id: UUID
    despacho_id: UUID
    score: int                  # 0-100
    prioridad: Literal["alta", "media", "baja"]   # derivada del score
    razon: str                  # 1 frase que justifica por qué le importa a ESTE despacho
    expedientes_tocados: list[UUID]   # del despacho, que la norma toca
    generado_en: datetime
```

`NormaBOAccionable` es la "vista por despacho". Se calcula cada noche
para todos los despachos activos; no se cachea entre días (el perfil del
despacho puede cambiar).

## Algoritmos clave

### Scraping del BO

`BoletinOficialScraper` implementa el puerto `FuenteBO`. Por fecha:

1. Por cada sección de las 3 cubiertas, navegar al índice del día.
2. Paginar (el BO devuelve listados por bloques de 25 normas).
3. Por cada norma listada: bajar metadata (tipo + número + organismo +
   sumario + URL).
4. Persistir `NormaBO` por upsert sobre `(fecha_publicacion, seccion,
   tipo_norma, numero_norma)`.

**Respetuoso:** UA identificado (`PraxisAsesor/0.x (+contacto@dominio.com)`),
rate limit 1 req/seg, retries con backoff, `robots.txt` consultado en el
arranque del job. Documentado en **ADR 0007** (política de scraping).

### Clasificación

Para cada norma sin clasificar:

```python
class LlmProvider(ABC):
    # nuevo en spec 15
    async def clasificar_norma_bo(self, norma: NormaBO) -> ClasificacionNormaBO: ...
```

System prompt cacheado (las 12 áreas + reglas de palabras_clave +
ejemplos few-shot). User content: `sumario + tipo_norma + organismo`.
Output JSON estructurado.

### Accionabilidad por despacho

```
score = 0
si la norma toca un área temática presente en el perfil del despacho:
    score += 30
si la norma toca un área de comisión del legislador (info del padrón):
    score += 20
si la norma menciona alguna referencia legal que coincide con
expedientes del despacho (por número o por título):
    score += 35
si la norma es DESIGNACIÓN en un organismo del área del despacho:
    score += 15
si la norma toca un distrito observado por el despacho:
    score += 10

prioridad = {
    score >= 60: "alta",
    score >= 30: "media",
    score >= 15: "baja",
    score <  15: descartar (no aparece en briefing)
}
```

Razón en lenguaje natural: la genera el LLM con un prompt corto que
recibe `norma`, `area_match`, `expedientes_match`, y devuelve 1 frase de
≤ 140 caracteres. Cacheado por `(norma_id, despacho_id, hash_perfil)`.

Top-5 por score por despacho → entra al briefing.

## Puertos y casos de uso

```python
class FuenteBO(ABC):
    async def listar_normas_del_dia(self, fecha: date) -> list[NormaBO]: ...
    async def obtener_texto_completo(self, norma: NormaBO) -> str | None: ...
    # implementación: BoletinOficialScraper (infraestructura)

class NormaBORepository(ABC):
    async def upsert_lote(self, normas: list[NormaBO]) -> int: ...
    async def buscar_por_fecha(self, fecha: date) -> list[NormaBO]: ...
    async def buscar_por_id(self, id: UUID) -> NormaBO | None: ...

class ClasificacionNormaBORepository(ABC):
    async def upsert(self, c: ClasificacionNormaBO) -> ClasificacionNormaBO: ...
    async def buscar_por_norma(self, norma_id: UUID) -> ClasificacionNormaBO | None: ...

class PerfilInteresDespachoRepository(ABC):
    async def obtener(self, despacho_id: UUID) -> PerfilInteresDespacho | None: ...
    # PerfilInteresDespacho vive en spec 16/17 también — entidad compartida.

class ScrapeBoletinOficial:
    async def execute(self, *, fecha: date) -> int: ...

class ClasificarNormasBO:
    async def execute(self, *, fecha: date) -> int: ...

class EvaluarAccionabilidadPorDespacho:
    async def execute(self, *, fecha: date, despacho_id: UUID | None = None) -> int: ...
```

## Endpoints API

```
GET  /api/v1/bo/normas?fecha=YYYY-MM-DD&seccion=…
     → lista normas (todas, no filtradas por despacho)

GET  /api/v1/bo/normas/{id}
     → detalle estructurado (NO texto completo; link a URL oficial)

GET  /api/v1/bo/accionables?fecha=YYYY-MM-DD
     → lista las accionables PARA EL DESPACHO del request (current_context)

POST /api/v1/bo/normas/reclasificar-perfil
     → recálculo on-demand cuando el despacho cambia su perfil
```

El briefing diario completo (BO + noticias) tiene su propio endpoint en
spec 16, no acá.

## UI

Card en `/dashboard` con las top-5 accionables del día y link a la
vista completa. Vista completa `/bo` con:

- Filtros: fecha, sección, área temática, organismo emisor.
- Tabla de normas.
- Detalle estructurado (sin texto completo).
- Link al BO oficial.

## Criterios de aceptación

- [ ] `BoletinOficialScraper` baja correctamente las 3 secciones del BO
      de una fecha dada, persistiendo `NormaBO`. Tests con fixtures HTML
      capturados, no HTTP real en CI.
- [ ] `ClasificarNormasBO` produce `ClasificacionNormaBO` válida (área
      en las 12 conocidas, palabras_clave ≥ 1, organismo no vacío) con
      `FakeLlmProvider` y con `AnthropicLlmProvider`.
- [ ] `EvaluarAccionabilidadPorDespacho` produce top-N con score
      reproducible para un perfil dado.
- [ ] Smoke real: una corrida sobre un BO real del mes corriente para
      el despacho de Juliano genera ≥ 1 accionable razonable
      (validación manual con Agustín).
- [ ] Endpoint `GET /bo/accionables` devuelve resultados consistentes
      con la corrida del job.
- [ ] Vista web muestra accionables con link a `boletinoficial.gob.ar`.
- [ ] La pieza WhatsApp del briefing diario (BO) entra en una plantilla
      Meta y se renderiza sin recortes (≤ 1024 caracteres del body
      total, considerando que se combina con noticias).
- [ ] Lint, type-check y tests verdes.

## Fuera de alcance (v1)

- **Secciones del BO no cubiertas**: Sección de Sociedades, Asociaciones
  Civiles, Convocatorias, Edictos Judiciales, etc. Reabrir en v2 si un
  despacho lo pide.
- **Resumen IA del cuerpo de la norma.** El sumario del BO es público y
  oficial, lo usamos tal cual. El cuerpo completo no lo resumimos para
  el usuario; sólo para uso interno (clasificación) si D2 lo habilita.
- **Búsqueda full-text histórica en normas BO.** Listar y filtrar sí,
  full-text no en v1 (requiere indexar texto completo, depende de D2).
- **Mapeo automático de norma BO → expediente HCDN/HSN** más allá del
  match heurístico (número o título). No se sigue trámites del PEN.
- **Alertas push intra-día por una norma BO concreta.** El BO se publica
  una vez al día por la mañana; no hay urgencia para "alertas en
  tiempo real". Si una norma altísima prioridad se publica, sigue
  llegando en el envío 7:30 del día siguiente.
- **Reportes consolidados semanal/mensual.**

## Riesgos

- **Cambios silenciosos del portal BO** → tests con fixtures + job
  programado semanal contra el portal vivo. Mitigación igual a HCDN.
- **Falsos negativos de accionabilidad** (norma le importa pero el
  score no la subió a top-5) → el usuario puede ver el listado completo
  del día y filtrar; medimos con feedback de Juliano.
- **Costos LLM si el BO mete 200+ normas un día** → clasificación es
  ~200 normas × tokens cortos × Sonnet 4.5. Estimar costo en checkpoint
  durante implementación (cap mensual ya en $5 USD). Mitigaciones:
  modelo Haiku para clasificación si Sonnet sale caro, cache por
  `hash_sumario` para no reclasificar lo idéntico al día anterior.
- **Sobrecargar boletinoficial.gob.ar** → 1 req/seg + 1 corrida/día
  por sección. Total estimado: 10-30 requests por noche. Trivial.
- **Confundir norma con expediente** → mantener `numero_norma`
  separado de `numero_expediente`; no confundir el espacio de nombres.

## Plan de tests

- **Unit (dominio)**: construcción de `NormaBO` con campos válidos,
  invariantes (`fecha_publicacion ≤ hoy`, `numero_norma` no vacío).
- **Unit (parser)**: HTML fixturizado del BO por sección → asserts
  sobre cantidad y campos extraídos.
- **Unit (scoring de accionabilidad)**: dados un perfil sintético y un
  set de normas/clasificaciones, el ranking es determinístico.
- **Contract test (FuenteBO)**: snapshot HTML real del BO de una fecha
  fija + asserts sobre cantidad de normas y campos. Estable. Si el BO
  cambia, falla acá y se actualiza el snapshot consciente.
- **Integration (no en CI)**: marker `@pytest.mark.network` para tests
  contra el portal vivo.
- **Smoke real** (manual): correr el pipeline completo sobre el BO de
  ayer para el despacho de Juliano y validar con Agustín que las 3-5
  accionables top tienen sentido.

## Dependencias

- ADR 0006 (modelo de datos BO + Noticias + Menciones + WhatsApp).
- ADR 0007 (política de scraping respetuoso).
- Spec 16 (briefing diario completo lo arma una sola pieza junto con
  noticias) — esta spec produce los inputs.
- Spec 17 (canal WhatsApp) — esta spec usa los `Destinatario` +
  `MessagingProvider` definidos ahí.
- `LlmProvider.clasificar_area_tematica` ya existe (feat/27); se le suma
  `clasificar_norma_bo` con system prompt cacheado.
- `PerfilInteresDespacho` — entidad compartida; se define en spec 17.
  Estrategia de siembra híbrida (decisión D1) implementada en el caso
  de uso `SembrarPerfilInteres` que corre al onboarding y se reinvoca
  cuando cambian los seguimientos del despacho.
