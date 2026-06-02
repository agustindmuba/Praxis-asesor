# 0007 — Política de scraping respetuoso para BO y medios

- **Estado**: propuesta
- **Fecha**: 2026-06-02
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —
- **Specs que aterriza**: 15 (BO accionable), 16 (Noticias + menciones).

## Contexto

Las specs 15 y 16 introducen scraping contra **sitios públicos de
terceros**:

- Spec 15: `boletinoficial.gob.ar` (1 corrida nocturna del día anterior).
- Spec 16: 11 medios fijos (La Nación, Clarín, Infobae, Página/12,
  Perfil, Ámbito, Parlamentario, La Política Online, Letra P) + 2-3
  distritales por despacho. Polling **continuo** cada 15-30 min.

A diferencia del scraping previo de Praxis (`HcdnScraper`, `HsnScraper`,
`HcdnVotacionesScraper`), que apunta a portales públicos del Estado
nacional con tolerancia explícita para uso institucional, **los medios
son privados**. Su tolerancia es operativa, no jurídica, y depende de
que nuestro tráfico sea **inocuo**:

- Identificable (no parecemos un bot anónimo agresivo).
- Bajo en volumen (no impactamos sus servers).
- Respetuoso de las reglas que el sitio publica explícitamente
  (robots.txt, rate limits, headers de cache).
- Sin reproducción no autorizada del contenido (restricción legal
  paralela — ver ADR 0006 y spec 16).

Esta política tiene que valer para todos los adapters de
`infrastructure/scrapers/*` que esta y futuras features agreguen.
Restricciones que debe respetar:

1. **Sin lock-in legal**: si un medio nos pide formalmente parar, se
   para sin debate.
2. **Sin reproducción de cuerpo de artículos** (regla dura del
   producto). El scraper baja cuerpo a memoria sólo si lo necesita
   para análisis interno y lo descarta tras procesar.
3. **Identificación obligatoria**: User-Agent con contacto. Quien
   recibe el request puede saber quiénes somos.
4. **Robusto frente a cambios cosméticos** del HTML (lección del spike
   HCDN). Los tests con fixtures atrapan rupturas en CI.
5. **Sin tumbar a Praxis cuando el medio cae**: scraper resiliente,
   con backoff y circuit breaker.

## Decisión

### Reglas obligatorias para todo scraper de Praxis

#### 1. User-Agent identificable

Todos los adapters envían:

```
User-Agent: PraxisAsesor/0.x (+https://praxisasesor.com/contacto;
              monitoreo legislativo y políticas públicas)
```

Sin User-Agent ofuscado, sin imitación de browser. Si un sitio
discrimina por UA y nos bloquea, **no rotamos UA** — abrimos canal con
el sitio o bajamos esa fuente del catálogo.

Configurado en `praxis.config.Settings.scraper_user_agent`, único punto
de cambio. Variable de entorno `SCRAPER_USER_AGENT` puede override en
dev.

#### 2. Rate limit por dominio

- **Default**: 1 request por segundo por dominio.
- **Para BO** (ráfaga nocturna sola): 1 req/s, paginación serial por
  sección.
- **Para medios** (polling): 1 req/s por dominio + **jitter aleatorio
  ±30%** en el intervalo de polling para evitar sincronizar todas las
  fuentes en el mismo segundo.

Implementado vía `aiolimiter.AsyncLimiter(rate=1, per=1.0)` por
dominio, no global. Garantiza que múltiples fuentes en paralelo no se
saboteen entre sí.

#### 3. Lectura de `robots.txt` al arranque

Al onboarding de cada `FuenteNoticia` (o `FuenteBO`) y al re-cargar el
catálogo, el adapter consulta `https://<dominio>/robots.txt` y guarda
en la entidad:

- `robots_ok: bool` — si nuestro UA está permitido para las rutas que
  vamos a tocar.
- `ultima_revision: datetime`.

Re-evaluación: cada 7 días vía Celery beat. Si robots cambia y nos
prohíbe, **la fuente se marca `activa=false`** y se loguea para
revisión humana.

#### 4. Backoff y circuit breaker

Por dominio:

- **429 o 503** → backoff exponencial: 30s, 60s, 120s, 300s. Tras 4
  fallos consecutivos, dominio queda en **ventana de respeto** de 1
  hora antes de reintentar.
- **5xx genérico** → backoff lineal: 5s, 10s, 20s. Tras 3 fallos en 10
  min, mismo lockout de 1h.
- **Timeout** → 1 retry inmediato, después espera 10s. No insistimos
  agresivo.

Estado del circuit breaker en Redis con TTL. El loop de polling consulta
antes de cada request.

#### 5. Prioridad RSS / sitemap sobre HTML scraping

Si la fuente expone feed estándar (RSS, Atom, sitemap.xml), el adapter
lo usa **siempre primero**. Scraping HTML del listado de portada queda
para fuentes sin feed. Razón: feeds están diseñados para ser leídos por
automatización, son más livianos y menos propensos a romper.

Si la fuente tiene RSS truncado (sólo bajada, no cuerpo) y necesitamos
el cuerpo para detección de menciones, **bajamos artículo por artículo
a su URL canónica** respetando el rate limit. Cuerpo se descarta tras
clasificar (regla legal).

#### 6. Cache HTTP

Adapter envía `If-Modified-Since` y `ETag` cuando los tiene cacheados
en Redis. Si el servidor responde `304 Not Modified`, no se procesa
nada (ahorra LLM también).

#### 7. Manejo del cuerpo del artículo

El cuerpo se baja **sólo cuando hace falta** (detección de menciones,
clasificación). Vive en `bytes` o `str` dentro del worker Celery. **No
toca DB ni file system.** Tras `ProcesarArticulo.execute()`, el cuerpo
se descarta. Lo que persiste:

- Metadata: título, URL, fuente, fecha (en `articulo`).
- Bajada propia generada por LLM (≤240 chars, voz Praxis).
- Si hay mención: snippet ≤200 chars alrededor del nombre (`mencion`).

Auditable: el esquema no tiene `articulo.texto_completo`.

#### 8. Identificación en headers extra

Para hosts que lo soporten:

- `From: contacto@praxisasesor.com`
- `X-Praxis-Purpose: legislative-monitoring`

Ambos opcionales, ambos para que el operador del sitio pueda ubicar
quién genera el tráfico si tiene una pregunta.

#### 9. Stop on demand

Praxis publica un endpoint público `GET /.well-known/scraper-info` con:

- Lista de fuentes monitoreadas.
- UA exacto.
- Email de contacto.
- Texto en lenguaje natural: "si tu sitio aparece en esta lista y
  querés que paremos, contactanos y bajamos la fuente del catálogo
  dentro de las 24hs".

#### 10. Inmediatez del opt-out

Cualquier email a `contacto@praxisasesor.com` pidiendo parar dispara:

1. Marcar `fuente_noticia.activa = false` para esa fuente.
2. Confirmar al solicitante.
3. Documentar en un changelog interno.

Sin negociación.

### Reglas adicionales sólo para medios privados (spec 16)

- **No reproducir títulos en formato que parezca contenido editorial
  propio.** El título original aparece siempre con la fuente y un link
  visible. La bajada generada por Praxis nunca se confunde con la del
  medio.
- **Si un medio tiene paywall o login**, Praxis no intenta romperlo.
  Sólo trabajamos con lo que el medio publica libremente a su robot
  default.
- **No descargamos imágenes ni archivos multimedia** del medio.

### Reglas adicionales sólo para BO (spec 15)

- BO es dominio público (norma estatal de obligatoria publicación). El
  cuerpo sí se persiste (`norma_bo_texto`) pero no se expone en UI —
  el usuario va al BO oficial.
- 1 corrida nocturna ~5:00 AM ART, 1 retry a las 5:30 si falla la
  primera. Si falla la segunda, ese día queda sin BO; el briefing
  diario 7:30 incluye solo noticias.

### Aplicabilidad

Esta política aplica a:

- `BoletinOficialScraper` (spec 15).
- `RssFeedAdapter`, `SitemapAdapter`, `MedioScraper` (spec 16).
- `HcdnScraper`, `HsnScraper`, `HcdnVotacionesScraper`: **revisión
  retroactiva** para asegurar UA + rate limit alineados; ya cumplen el
  espíritu pero no documentaban el UA.

## Alternativas consideradas

### Usar un proveedor SaaS de monitoreo de medios

Idea: contratar a Mention, Meltwater o similar y delegar el scraping.
Descartado:

- Costo prohibitivo para v1 (planes empresariales > USD 500/mes).
- Pérdida de control sobre fuentes (no podemos agregar Parlamentario o
  un distrital chico fácilmente).
- Dependencia externa para algo central al producto.

### Headless browser para fuentes con JS-rendered content

Idea: Playwright para fuentes que necesitan JS. Descartado en v1:

- Suma 200-300 MB de runtime, complejidad de mantenimiento.
- Las 11 fuentes del catálogo v1 tienen versiones HTML/RSS sin JS.
- Reabrir si una fuente futura lo exige.

### Rotar UA o usar IPs residenciales

Categóricamente descartado. Ofuscar quiénes somos rompe la base de la
política y nos pone en territorio legalmente gris.

### Rate limit más agresivo (10 req/s)

Tentador para el polling continuo. Descartado:

- 1 req/s × 11 fuentes × cada 20 min = 33 req/20 min = trivial para
  cualquier sitio.
- Ratchet conservador para no llamar la atención de operadores.

### Ignorar robots.txt

Algunos scrapers de monitoreo industrial lo hacen porque robots no es
legalmente vinculante. Descartado por principio de respetuoso.

## Consecuencias

### Positivas

- Política única para todo scraping, fácil de auditar.
- Bajo riesgo de bloqueo o fricción con medios.
- UA identificable convierte un eventual conflicto en una conversación,
  no en una escalada.
- Documentación pública (`.well-known/scraper-info`) demuestra
  transparencia.

### Negativas / Trade-offs

- Polling cada 15-30 min introduce **latencia** entre publicación y
  detección de menciones. Para un escenario de crisis real el SLA es
  ~30 min, no real-time puro. Aceptable v1, mejorable v2 con webhooks
  donde el medio los soporte.
- Rate limit 1 req/s limita el throughput total si en el futuro
  agregamos muchas fuentes. Reabrir si pasamos de 30 fuentes.
- Cache HTTP requiere mantener Redis con persistencia mínima (ya está
  desplegado para anti-flood).

### Operación

- **Dashboard interno** muestra para cada fuente: última corrida,
  tasa de éxito, estado de circuit breaker, `robots_ok`.
- **Alerta interna** cuando una fuente entra en circuit-breaker
  prolongado (>4h) para que un humano revise.
- **Backup runbook**: cómo bajar una fuente del catálogo en < 5 min si
  recibimos un opt-out.

## Trabajo derivado

- feat/39.3: `BoletinOficialScraper` aplica esta política.
- feat/40.2: adapters de medios aplican esta política.
- Endpoint `/.well-known/scraper-info` (router público) — feat/41.x o
  feat/40.6 según convenga.
- Revisión retroactiva de scrapers HCDN/HSN para alinear UA — tarea
  chica, oportunidad cuando se toque algo de scrapers.
