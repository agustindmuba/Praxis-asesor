# Spec 16 — Briefing de noticias + alertas de menciones

**Estado:** borrador · **Owner:** Agustín · **Branch sugerida:** `feat/40-noticias-menciones`

## Problema

Un legislador y su jefe de despacho tienen dos problemas distintos con
los medios:

1. **Mañana**: saber qué pasó en las últimas 24hs que es relevante para
   los temas del despacho, sin tener que leer 6 diarios. Hoy lo
   resuelven mal, mirando Twitter o pidiéndole a un asesor que arme un
   "monitoreo" a las 9 AM (lo que llega tarde y es manual).
2. **Durante el día**: enterarse **en el momento** cuando un medio
   menciona al legislador. Hoy: o tienen alertas de Google News que son
   ruidosas e impuntuales, o lo descubren cuando alguien del bloque les
   forwardea el link a las 3 PM. Para temas reputacionales y de manejo
   de crisis, llegar 4 horas tarde es perder la ventana.

Praxis tiene que resolver los dos: un **briefing matinal** consolidado y
**alertas push** en tiempo real cuando hay menciones.

Ambos sin reproducir el cuerpo de los artículos (restricción legal — ver
sección Restricciones legales).

## Usuario y caso de uso

**Usuarios:**

- **Jefe de despacho**: recibe el briefing diario 7:30 AM con
  noticias + BO consolidados.
- **Legislador**: recibe alertas en tiempo real cuando lo mencionan.
- **Asesor temático**: consulta el histórico de menciones en la app
  (filtrable por fecha, fuente, tono).

**Cliente prototipo:** despacho de Pablo Juliano (Democracia Para
Siempre), distrito Buenos Aires.

**Casos de uso:**

```
CU-1 (briefing matinal):
  DADO  el ciclo de scraping de noticias del último día
  Y     el perfil de intereses del despacho
  CUANDO son las 7:30 AM ART
  ENTONCES el despacho recibe (app + WhatsApp) la sección "📰 Noticias"
           del briefing diario con 5-8 titulares relevantes, ordenados
           por relevancia, con link al artículo original.

CU-2 (alerta tiempo real):
  DADO  un artículo recién publicado que menciona al legislador del
        despacho (por nombre completo, apellido en contexto o alias),
  CUANDO el scraper lo detecta,
  ENTONCES el destinatario opt-in del despacho recibe por WhatsApp
           una alerta con: título + fuente + tono (pos/neu/neg) + link.
  RESTRICCIÓN: máximo N alertas/hora; si se supera, agrupar.

CU-3 (histórico):
  El asesor entra a /menciones, ve la timeline de menciones del último
  período con filtros por fecha, fuente, tono y descarga CSV.
```

## Restricciones legales (regla dura del producto)

**Praxis nunca reproduce el cuerpo completo de un artículo de un medio.**
Esto está fuera de cualquier consideración técnica y aplica en todas las
superficies (app, WhatsApp, futuros canales).

Lo que sí se puede usar:

- **Título original** del artículo (es titularidad del medio pero su uso
  como referencia para llevar al lector al artículo original es uso
  aceptado de la práctica de monitoreo de medios).
- **Link al artículo original** (siempre presente).
- **Fuente** (nombre del medio) y fecha de publicación.
- **Bajada propia** generada por Praxis con LLM: **1 frase máximo**, no
  reproduce el texto del medio, describe el tema con palabras propias
  ("Un decreto del PEN modifica el régimen jubilatorio docente").
- **Snippet contextual de la mención**: ≤ 200 caracteres alrededor del
  nombre del legislador. **Se persiste** (decisión D5) y se muestra en
  el histórico con `...` al inicio y al final para marcar recorte.
  Práctica estándar de monitoreo de medios. El asesor lo ve sin tener
  que abrir el link del artículo.

Lo que NO se hace, en ningún caso:

- Resumen IA del cuerpo del artículo.
- Cita textual extendida (>200 chars).
- Cache local del artículo completo para mostrar offline.
- Republicar contenido del medio en cualquier formato propio.

Esta restricción se hace explícita en el modelo de dominio (`Articulo`
no tiene campo `texto_completo` accesible al renderer/UI; lo que el
scraper baja para análisis interno vive aparte y nunca cruza la frontera
de presentación).

## Decisiones tomadas (del prompt de Agustín)

| Tema | Decisión |
|---|---|
| Fuentes nacionales | La Nación, Clarín, Infobae, Página/12, Perfil, Ámbito Financiero |
| Fuentes políticas | Parlamentario, La Política Online, Letra P |
| Fuentes distritales | 2-3 por despacho, parametrizable al onboarding |
| Acceso preferente | RSS/sitemap; scraping respetuoso cuando no haya feed |
| Polling | cada 15-30 min por fuente, respetando rate limits + robots.txt |
| Restricción legal | título + bajada propia 1 frase + link; nada de cuerpo |
| Briefing | parte del envío único 7:30 AM (junto con BO, ver spec 15) |
| Alertas | en tiempo real por WhatsApp |
| Anti-flood alertas | máximo N/hora, agrupar resto |
| Clasificación IA en alerta | tema + tono + alcance del medio |
| Histórico | en app con filtros, sin WhatsApp |

## Decisiones de dominio NUEVAS (resueltas)

- **D4** → **Solo el legislador titular del despacho.** Cada despacho
  monitorea menciones de su legislador (vía `aliases_legislador` en
  `PerfilInteresDespacho`). Multi-legislador queda v2.
- **D5** → **Snippet ≤200 chars SE persiste** en `Mencion.snippet_contexto`.
  Habilita histórico útil en `/menciones` con `...` para marcar recorte.
  Práctica estándar de monitoreo de medios.
- **D6** → **Regex de candidatos + LLM disambiguator.** Pase 1:
  regex rápido (nombre completo OR apellido + contexto político) sobre
  el cuerpo. Pase 2: si match, LLM confirma que es el legislador (no
  homónimo) y clasifica tono en la misma llamada. Mejor recall + precisión.
- **D7** → **Catálogo fijo de alcance por `FuenteNoticia`.** Cada
  fuente se etiqueta al onboarding (nacional / provincial / nicho).
  No depende del artículo. Predecible y trivial de auditar.
- **D8** → ver "Anti-flood y agrupamiento" más abajo (3/hora +
  agrupamiento diferido 5 min).
- **D9** → **Castellano rioplatense neutro, estilo informativo.**
  3ª persona, sin adjetivos cargados. Ej: "Un decreto del PEN modifica
  el régimen jubilatorio docente nacional." Profesional, no compite
  con la voz del medio. System prompt cacheado con ese tono.
- **D10** → **Retención: artículos 12 meses, menciones 24 meses.**
  Purga automática Celery beat diaria. `Articulo.hash_dedup` se
  conserva en tabla aparte `articulo_hash` para no reprocesar URLs
  vistas antes (peso mínimo, vida indefinida).

## Solución propuesta

Dos pipelines distintos que comparten infra:

### Pipeline 1 — Ingesta continua de noticias

```
loop cada 15-30 min por fuente (jitter aleatorio para no sincronizar):
    1. Si la fuente tiene RSS/sitemap, leerlo.
       Si no, scrapear listado de portada respetando robots.txt.
    2. Para cada artículo nuevo (no visto antes por hash de URL):
        - Capturar metadata: título, URL, fecha publicación, autor opt.
        - Si necesitamos el cuerpo para detección/clasificación,
          bajarlo SOLO en memoria del worker, NO persistir.
        - Persistir Articulo (sin cuerpo).
    3. Disparar tareas Celery por artículo:
        - ClasificarArticulo
        - DetectarMenciones (por cada legislador "monitoreable")
        - Si hay mención → EnviarAlertaMencion (respetando anti-flood)
```

### Pipeline 2 — Briefing matinal de noticias

```
07:00 ART  ConsolidarNoticiasUltimas24h.run(despacho_id)
           ↓ articulos del último ciclo cruzados con perfil del despacho
           ↓ top-8 por score de relevancia
           ↓ generar bajada propia por artículo (LLM, cacheada)

07:30 ART  EntregarBriefingDiario (spec 15+16 juntas)
           ↓ mensaje único con BO + Noticias por canal
```

## Estructura del entregable

### Sección Noticias en la app

```
┌─────────────────────────────────────────────────────────────┐
│ 📰 NOTICIAS DEL DÍA (8 destacadas de 142 capturadas)        │
│                                                             │
│ 🟡 La Nación — "Diputados debate ley educativa esta semana" │
│    ▸ Toca tu proyecto 1247-D-2025 y áreas afines.           │
│    [Abrir nota →]                                           │
│                                                             │
│ 🟢 Parlamentario — "Bloque DPS presentó proyecto sobre…"    │
│    ▸ Mención de Juliano (ver alertas).                      │
│    [Abrir nota →]                                           │
│                                                             │
│ 🟢 Página/12 — "El Gobierno anuncia partida extraordinaria  │
│    para escuelas técnicas"                                  │
│    ▸ Área educación, sin expediente en trámite del despacho.│
│    [Abrir nota →]                                           │
│                                                             │
│ … (5 más)                                                   │
│                                                             │
│ Ver las 142 noticias del día →                              │
└─────────────────────────────────────────────────────────────┘
```

Cada item muestra **título original + bajada propia 1 frase + fuente +
link**. Click → abre el artículo original en el sitio del medio (no en
una vista interna).

### Sección Noticias en WhatsApp

Sigue la misma plantilla del briefing diario (spec 17). Body combinado
con BO; cada item es 1 línea. Ejemplo del fragmento Noticias:

```
📰 Noticias (8 destacadas, 142 capturadas)
• La Nación: debate ley educativa esta semana (🟡)
• Parlamentario: bloque DPS presenta proyecto (🟢)
• Página/12: partida extraordinaria escuelas (🟢)
+ 5 más en la app
```

### Alerta de mención en WhatsApp (tiempo real)

Plantilla aparte (`praxis_mencion_individual_v1`), pre-aprobada Meta:

```
🔔 Mención detectada
Fuente: La Política Online · 14:23
Tono: NEGATIVO · Alcance: político-nicho

"Juliano apuntó contra el oficialismo por la
demora en tratamiento de…"

[Ver nota →]   [Ver histórico de menciones →]
```

### Alerta agrupada (anti-flood)

Si en una hora el legislador acumula más alertas que el límite, se
manda **una sola** plantilla agrupada:

```
🔔 6 menciones en la última hora
3 negativas · 2 neutras · 1 positiva
Top: La Nación, Infobae, La Política Online

[Ver detalle en la app →]
```

## Modelo de dominio nuevo

```python
@dataclass(frozen=True, slots=True)
class FuenteNoticia:
    """Un medio monitoreado. Configurado en catálogo + ampliable por despacho."""
    id: UUID | None
    nombre: str                 # "La Nación"
    dominio: str                # "lanacion.com.ar"
    tipo: Literal["nacional", "politico", "distrital"]
    alcance: Literal["nacional", "provincial", "nicho"]  # ver D7
    modo_acceso: Literal["rss", "sitemap", "scraping"]
    feed_url: str | None        # si rss/sitemap
    distrito: str | None        # si tipo=distrital
    robots_ok: bool             # snapshot de robots.txt al onboarding
    ultima_revision: datetime | None
    activa: bool

@dataclass(frozen=True, slots=True)
class Articulo:
    """Snapshot mínimo de un artículo. NO contiene cuerpo accesible al UI."""
    id: UUID | None
    fuente_id: UUID
    url: str
    titulo: str
    bajada_propia: str | None   # generada por Praxis, 1 frase ≤ 240 chars
    publicado_en: datetime | None
    capturado_en: datetime
    hash_dedup: str             # sha256(url canonicalizada)

@dataclass(frozen=True, slots=True)
class ClasificacionArticulo:
    """Clasificación general del artículo (no depende del despacho)."""
    id: UUID | None
    articulo_id: UUID
    area_tematica: str          # de las 12 conocidas
    palabras_clave: list[str]
    modelo: str
    prompt_version: str
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class ArticuloRelevante:
    """Vista por despacho. Análoga a NormaBOAccionable."""
    articulo_id: UUID
    despacho_id: UUID
    score: int                  # 0-100
    razon: str
    expedientes_tocados: list[UUID]
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class Mencion:
    """Mención de un legislador en un artículo."""
    id: UUID | None
    articulo_id: UUID
    legislador_id: UUID         # del padrón
    despacho_id: UUID           # despacho que monitorea ese legislador
    snippet_contexto: str       # ≤ 200 chars, persistido (D5)
    tono: Literal["positivo", "neutro", "negativo"]
    confianza_tono: float       # 0-1, del LLM
    alcance_medio: Literal["nacional", "provincial", "nicho"]   # de la fuente o del LLM
    detectado_en: datetime
    notificada: bool            # ya se envió alerta (o se descartó por flood)

@dataclass(frozen=True, slots=True)
class AlertaMencionEnviada:
    """Auditoría de alerta efectivamente enviada."""
    id: UUID | None
    destinatario_id: UUID
    tipo: Literal["individual", "agrupada"]
    menciones_ids: list[UUID]   # 1 si individual, N si agrupada
    plantilla_meta: str         # "praxis_mencion_individual_v1" | ...
    enviado_en: datetime
    estado: Literal["enviado", "fallo", "rechazado"]
    error: str | None
```

`Articulo.bajada_propia` se genera con LLM (no es el `description` del
RSS — eso es del medio). Se cachea por `articulo_id`.

## Algoritmos clave

### Detección de menciones

```
Para un Articulo + lista de legisladores monitoreados:
    1. Bajar cuerpo del artículo SOLO en memoria del worker.
    2. Por cada legislador:
        - Buscar (nombre_completo OR (apellido AND contexto_politico))
          donde contexto_politico = uno de {"diputado", "senador",
          "legislador", "bloque", "@aliasTwitter", … }.
        - Si match → extraer snippet ≤ 200 chars alrededor del match.
        - Pasar snippet al LLM para confirmar (es realmente sobre
          ESE legislador, no homónimo) + clasificar tono.
    3. Persistir Mencion para los confirmados.
    4. Descartar cuerpo del artículo de la memoria.
```

Implementación de "contexto político": **D6** — propuesta inicial:
regex sobre keywords + LLM para casos ambiguos. Si Agustín prefiere
algo más simple en v1 (solo nombre exacto y apellido + "diputado",
sin LLM disambiguator), se baja una capa.

### Bajada propia (LLM)

```python
class LlmProvider(ABC):
    # nuevos
    async def generar_bajada_propia(self, articulo: Articulo, *, texto: str) -> str: ...
    async def clasificar_tono_mencion(self, *, snippet: str, legislador: str) -> tuple[str, float]: ...
    async def clasificar_articulo(self, articulo: Articulo, *, texto: str) -> ClasificacionArticulo: ...
```

System prompt cacheado por tipo de tarea. `texto` se pasa por valor y
no se persiste. Salida estructurada (JSON).

### Anti-flood y agrupamiento (D8)

Propuesta concreta (a aprobar):

```
Ventana móvil de 60 minutos por destinatario.
Cuota: 3 alertas individuales por hora.
Si llega una 4ª mención dentro de la ventana:
    - No se envía individual.
    - Se acumula en buffer pendiente para ese destinatario.
    - Se programa una alerta AGRUPADA para 5 min después.
    - Cualquier mención posterior dentro de los 5 min se suma a la
      misma alerta agrupada.
    - Cuando dispara la agrupada, manda 1 mensaje con el resumen
      (cantidad + distribución por tono + top-3 fuentes) y link al
      histórico de la app filtrado por el rango.
Una mención NUNCA queda sin notificar (siempre cae en individual o en
agrupada).
```

Esto requiere un `BufferAlertasMencion` en Redis (TTL 65 min) y un
job Celery `enviar_agrupada(destinatario_id)` programado.

## Puertos y casos de uso

```python
class FuenteNoticias(ABC):
    """Por implementación: RssFeedAdapter, SitemapAdapter, MedioScraper."""
    async def listar_articulos_nuevos(
        self, fuente: FuenteNoticia, *, desde: datetime
    ) -> list[Articulo]: ...
    async def obtener_texto_articulo(self, articulo: Articulo) -> str: ...
    # texto se devuelve, NO se persiste

class ArticuloRepository(ABC):
    async def upsert_lote(self, articulos: list[Articulo]) -> int: ...
    async def buscar_relevantes_ultimas_24h(self, despacho_id: UUID) -> list[Articulo]: ...

class MencionRepository(ABC):
    async def crear(self, m: Mencion) -> Mencion: ...
    async def listar_historico(
        self, *, despacho_id: UUID, desde: date, hasta: date,
        tono: str | None = None, fuente_id: UUID | None = None,
    ) -> list[Mencion]: ...

class IngestarFuente:
    async def execute(self, *, fuente_id: UUID) -> int: ...
    # corre por scheduler cada 15-30 min

class ProcesarArticulo:
    """Pipeline por artículo: clasificar + detectar menciones."""
    async def execute(self, *, articulo_id: UUID) -> None: ...

class EnviarAlertaMencion:
    async def execute(self, *, mencion_id: UUID) -> None: ...
    # respeta anti-flood, decide individual vs buffer agrupado
```

## Endpoints API

```
GET /api/v1/noticias/relevantes?fecha=YYYY-MM-DD
    → top-N artículos del día para el despacho del request

GET /api/v1/noticias/articulos?fuente_id=&desde=&hasta=
    → listado paginado

GET /api/v1/menciones?desde=&hasta=&tono=&fuente_id=
    → histórico del despacho del request

GET /api/v1/menciones/{id}

POST /api/v1/fuentes-distritales       (admin/onboarding)
    body: { nombre, dominio, distrito, feed_url? }
    → registra una fuente distrital para el despacho
```

## UI

- Card "📰 Noticias del día" en `/dashboard`.
- Ruta `/noticias` — listado filtrable por fuente, área, fecha, "solo
  con mención".
- Ruta `/menciones` — timeline con filtros (fecha, fuente, tono),
  badge de tono, link al artículo, exporta CSV.
- En `/configuracion` (nueva): pantalla para administrar **perfil de
  interés** + fuentes distritales + destinatarios WhatsApp (esto último
  está en spec 17).

## Criterios de aceptación

- [ ] Cada fuente tiene su adaptador (`FuenteNoticias`) con tests de
      contrato sobre fixtures.
- [ ] Polling programado por Celery beat respeta rate limits (1 req/seg
      por dominio mínimo) y `robots.txt`.
- [ ] `Articulo` nunca se persiste con `texto_completo`. Auditable por
      esquema (no existe la columna).
- [ ] Bajada propia se genera con LLM y se cachea por `articulo_id`.
- [ ] Detección de menciones encuentra ≥ 90% de los casos en un set
      manual de 50 artículos de prueba con/sin mención de Juliano
      (recall objetivo).
- [ ] Clasificación de tono coincide ≥ 80% con etiquetas manuales en
      ese mismo set (precisión objetivo).
- [ ] Anti-flood: en un test sintético con 10 menciones en 30 min se
      envían exactamente 3 individuales + 1 agrupada con 7.
- [ ] Endpoint `GET /menciones` devuelve el histórico filtrable.
- [ ] Vista `/menciones` muestra timeline + filtros + export CSV.
- [ ] Plantillas WhatsApp pre-aprobadas y conectadas (ver spec 17).
- [ ] Smoke real con un día de captura para el despacho de Juliano.
- [ ] Lint, type-check y tests verdes.

## Fuera de alcance (v1)

- **Twitter/X y otras redes sociales** como fuente — costo de API,
  postergado a v2.
- **Resumen IA del cuerpo del artículo** — restricción legal +
  simplicidad.
- **Análisis de evolución temporal del tono** (cómo viene la imagen
  semanal) — v2.
- **Reportes consolidados semanal/mensual** — v2.
- **Email como canal alternativo** — posiblemente v2.
- **Detección de menciones del bloque (no del legislador titular)** —
  abierto en D4.
- **Embeddings semánticos para detección de menciones** — v2 si el
  recall con regex+contexto resulta bajo.
- **Captura de imágenes/captions/tapas de papel** — sólo texto web.
- **Push browser nativo** (Service Worker) — sólo WhatsApp + app
  para v1.

## Riesgos

- **Medios cambian estructura HTML / RSS muere** → desacoplar por
  fuente, tests por fuente con fixtures, job semanal contra portal
  vivo que alerta si rompió. Mismo patrón que HCDN.
- **Costos LLM se descontrolan** (clasificar + bajada + tono por
  artículo × 11 fuentes × 200 artículos/día). Mitigación: clasificar
  con Haiku, sólo escalar a Sonnet en menciones; cachear agresivo;
  límite duro en Anthropic ($5/mes); monitorear costo diario por
  Anthropic Console. Si el costo sube, **stop loss automático**:
  desactivar `LlmProvider` y caer en bajadas heurísticas (primera
  oración del RSS description si existe).
- **Falsos positivos de menciones** (homónimos) → confirmar con LLM,
  no enviar alerta si confianza < umbral; medir con set de validación.
- **Falsos negativos** (no detectar una mención) → más caro de medir,
  pero crítico para confianza del usuario. Set de validación + medición
  recall por sprint.
- **Tono mal clasificado** en alerta de crisis → la confianza se muestra
  ("Tono: negativo · confianza media") y se ofrece reportar mal-clase
  desde la app para retroalimentar prompts.
- **Anti-flood demasiado agresivo** y se pierden alertas importantes →
  un test cualitativo durante la primera semana con Juliano; ajustar N
  si hace falta.
- **Saturación del scraping a un medio** → backoff exponencial al
  primer 429/503, ventana de respeto durante 1h, alertar en `/health`
  interno.
- **Responsabilidad de archivado** → al no persistir cuerpos, no
  asumimos responsabilidad de archivado web. Solo metadata + link al
  original.

## Plan de tests

- **Unit (dominio)**: Articulo + Mencion + ClasificacionArticulo, hash
  de dedup estable, validaciones.
- **Unit (adapters)**: fixtures de RSS + HTML por fuente; adapter
  extrae N artículos con campos correctos.
- **Unit (detector de menciones)**: cases con/sin mención, homónimos,
  apellido en contexto, abreviado.
- **Unit (anti-flood)**: secuencias sintéticas validan exactamente la
  distribución individual/agrupada.
- **Contract (FuenteNoticias)**: snapshot HTML/RSS por fuente.
- **Integration (no en CI)**: marker `network` contra cada fuente
  viva, scheduled weekly.
- **Smoke real**: 1 semana de captura para Juliano, revisar manualmente
  con Agustín la calidad del top-8 diario y de las alertas.
- **Eval del LLM**: set de 50 artículos etiquetados manualmente
  (mención sí/no + tono); medir recall y precisión por release.

## Dependencias

- ADR 0006 (modelo de datos consolidado).
- ADR 0007 (política de scraping respetuoso).
- ADR 0008 (integración WhatsApp Cloud API) — para alertas y briefing.
- ADR 0009 sugerido (anti-flood) — formaliza la decisión D8.
- Catálogo de legisladores (`feat/05-catalogo-legisladores`) ya
  existente — para `legislador_id` y nombres canónicos.
- `PerfilInteresDespacho` — entidad compartida con spec 15; se define
  en spec 17 o micro-spec previa (depende de D1).
- `LlmProvider` extendido con bajada + clasificación + tono.
- Spec 17 (canal WhatsApp) — esta spec consume `Destinatario`,
  `PlantillaWhatsApp`, `MessagingProvider`.
