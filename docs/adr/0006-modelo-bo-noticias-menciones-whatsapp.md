# 0006 — Modelo de datos BO, Noticias, Menciones y WhatsApp

- **Estado**: propuesta
- **Fecha**: 2026-06-02
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —
- **Specs que aterriza**: 15 (BO accionable), 16 (Noticias + menciones), 17 (canal WhatsApp).

## Contexto

Las specs 15, 16 y 17 introducen tres dominios nuevos al modelo de Praxis
Asesor:

1. **Boletín Oficial**: normas publicadas en `boletinoficial.gob.ar`,
   con clasificación y evaluación de "accionabilidad" por despacho.
2. **Noticias + menciones**: artículos capturados de medios (RSS,
   sitemap, scraping respetuoso) y menciones del legislador del despacho
   detectadas en esos artículos.
3. **WhatsApp**: canal proactivo de notificación, con destinatarios
   opt-in/opt-out, plantillas pre-aprobadas por Meta y registro
   auditable de envíos.

Las tres comparten una entidad transversal: **`PerfilInteresDespacho`**,
que materializa qué temas / comisiones / distritos / aliases del
legislador definen "lo que le importa a este despacho". Tanto BO como
Noticias lo consultan para evaluar relevancia; WhatsApp lo usa para
sembrar alias de detección de menciones.

Restricciones que la decisión debe respetar:

1. **Regla hexagonal** (ADR 0001): el dominio no sabe de scraping, de
   Meta API ni de cómo se rinde un mensaje. Vive en `praxis.domain`.
2. **Restricción legal del producto (spec 16)**: nunca se persiste ni
   expone el cuerpo completo de un artículo de un medio. La frontera de
   "no reproducir" se materializa en el esquema (no hay columna).
3. **Restricción de producto BO**: el sumario del BO es público y
   oficial; el cuerpo se puede persistir pero no exponer en UI.
4. **Tenancy**: todo dato pertenece a un `despacho_id`. Los datos
   "globales" (norma del BO, artículo del medio) son compartidos entre
   despachos pero su evaluación por despacho es tenant-scoped.
5. **Auditoría WhatsApp**: cada envío persiste — qué se mandó, a quién,
   cuándo, con qué plantilla, con qué resultado.
6. **Reanudabilidad**: cada pipeline (scrape BO nocturno, polling de
   medios, alertas en tiempo real) debe poder fallar y reanudarse sin
   duplicar datos.

## Decisión

### Entidades de dominio nuevas

#### Compartida — `PerfilInteresDespacho`

```python
@dataclass(frozen=True, slots=True)
class PerfilInteresDespacho:
    despacho_id: UUID
    areas_tematicas: list[str]        # subset de las 12 conocidas
    comisiones_legislador: list[str]  # nombres canónicos HCDN/HSN
    distritos_observados: list[str]
    aliases_legislador: list[str]     # ["Pablo Juliano", "Juliano", "@PJuliano"]
    actualizado_en: datetime
```

Sembrado híbrido (decisión D1): al onboarding se siembra desde
comisiones del legislador + áreas de seguimientos + distrito de banca.
El asesor edita libremente. Se re-siembra si cambian los seguimientos
**y** el asesor no ha editado el perfil después de la última siembra.

#### Spec 15 — BO

```python
@dataclass(frozen=True, slots=True)
class NormaBO:
    id: UUID | None
    fecha_publicacion: date
    # v1 persiste sólo "legislacion" y "designaciones" (spec 15 tras
    # spike 39.1.5). "avisos_oficiales" queda reservado para v2 (SAIJ).
    seccion: Literal["legislacion", "designaciones", "avisos_oficiales"]
    tipo_norma: str
    numero_norma: str
    organismo_emisor: str
    sumario: str                  # del BO, dominio público
    url_oficial: str
    hash_sumario: str             # sha256 — dedup + cache clasificación
    capturado_en: datetime

@dataclass(frozen=True, slots=True)
class NormaBOTexto:
    """El cuerpo completo. Vive en tabla aparte (D2)."""
    norma_id: UUID
    texto: str
    capturado_en: datetime

@dataclass(frozen=True, slots=True)
class ClasificacionNormaBO:
    id: UUID | None
    norma_id: UUID
    area_tematica: str
    palabras_clave: list[str]
    afecta_expedientes_hcdn: bool
    referencias_legales: list[str]
    modelo: str
    prompt_version: str
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class NormaBOAccionable:
    """Vista de una norma desde el ángulo de un despacho concreto."""
    norma_id: UUID
    despacho_id: UUID
    score: int                    # 0-100
    prioridad: Literal["alta", "media", "baja"]
    razon: str                    # 1 frase ≤ 140 chars
    expedientes_tocados: list[UUID]
    generado_en: datetime
```

#### Spec 16 — Noticias + Menciones

```python
@dataclass(frozen=True, slots=True)
class FuenteNoticia:
    id: UUID | None
    nombre: str
    dominio: str
    tipo: Literal["nacional", "politico", "distrital"]
    alcance: Literal["nacional", "provincial", "nicho"]  # catálogo fijo (D7)
    modo_acceso: Literal["rss", "sitemap", "scraping"]
    feed_url: str | None
    distrito: str | None
    robots_ok: bool
    ultima_revision: datetime | None
    activa: bool

@dataclass(frozen=True, slots=True)
class Articulo:
    """Snapshot mínimo. NUNCA tiene `texto_completo` accesible."""
    id: UUID | None
    fuente_id: UUID
    url: str
    titulo: str
    bajada_propia: str | None     # ≤ 240 chars, generada por LLM
    publicado_en: datetime | None
    capturado_en: datetime
    hash_dedup: str               # sha256(url canonicalizada)

@dataclass(frozen=True, slots=True)
class ClasificacionArticulo:
    id: UUID | None
    articulo_id: UUID
    area_tematica: str
    palabras_clave: list[str]
    modelo: str
    prompt_version: str
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class ArticuloRelevante:
    """Vista por despacho. Análoga a NormaBOAccionable."""
    articulo_id: UUID
    despacho_id: UUID
    score: int
    razon: str
    expedientes_tocados: list[UUID]
    generado_en: datetime

@dataclass(frozen=True, slots=True)
class Mencion:
    id: UUID | None
    articulo_id: UUID
    legislador_id: UUID
    despacho_id: UUID
    snippet_contexto: str         # ≤ 200 chars, persistido (D5)
    tono: Literal["positivo", "neutro", "negativo"]
    confianza_tono: float
    alcance_medio: Literal["nacional", "provincial", "nicho"]
    detectado_en: datetime
    notificada: bool
```

#### Spec 17 — WhatsApp

```python
@dataclass(frozen=True, slots=True)
class Destinatario:
    id: UUID | None
    despacho_id: UUID
    usuario_id: UUID | None
    nombre: str
    rol_interno: str
    telefono_e164: str
    recibe_briefing_diario: bool
    recibe_alertas_menciones: bool
    recibe_alertas_otras: bool
    opt_in_en: datetime | None
    opt_out_en: datetime | None
    activo: bool

@dataclass(frozen=True, slots=True)
class PlantillaWhatsApp:
    name: str
    idioma: str
    categoria: Literal["utility", "marketing", "authentication"]
    body_params: list[str]
    estado_meta: Literal["pendiente_aprobacion", "aprobada", "rechazada", "pausada"]
    aprobada_en: datetime | None
    contenido_referencia: str

@dataclass(frozen=True, slots=True)
class EnvioWhatsApp:
    id: UUID | None
    destinatario_id: UUID
    despacho_id: UUID              # desnormalizado para queries tenant-scoped
    plantilla_name: str
    tipo: Literal["briefing_diario", "mencion_individual", "mencion_agrupada", "otros"]
    payload_params: dict[str, str]
    correlativo_id: UUID | None
    enviado_en: datetime | None
    estado: Literal[
        "pendiente", "enviado", "entregado",
        "leido", "fallo", "rechazado_opt_out",
    ]
    message_id_meta: str | None
    error: str | None
```

### Esquema SQL — resumen de tablas

```
-- Compartido
perfil_interes_despacho(despacho_id PK FK → despacho.id, areas_tematicas TEXT[],
    comisiones_legislador TEXT[], distritos_observados TEXT[],
    aliases_legislador TEXT[], sembrado_at TIMESTAMPTZ NULL,
    editado_at TIMESTAMPTZ NULL, actualizado_en TIMESTAMPTZ)

-- BO
norma_bo(id PK, fecha_publicacion, seccion, tipo_norma, numero_norma,
    organismo_emisor, sumario, url_oficial, hash_sumario UNIQUE, capturado_en,
    UNIQUE(fecha_publicacion, seccion, tipo_norma, numero_norma))
norma_bo_texto(norma_id PK FK → norma_bo.id, texto, capturado_en)
clasificacion_norma_bo(id PK, norma_id FK UNIQUE, area_tematica, palabras_clave,
    afecta_expedientes_hcdn, referencias_legales, modelo, prompt_version,
    generado_en)
norma_bo_accionable(norma_id FK, despacho_id FK → despacho.id, score, prioridad,
    razon, expedientes_tocados UUID[], generado_en,
    PRIMARY KEY(norma_id, despacho_id))
    INDEX (despacho_id, fecha_publicacion DESC)

-- Noticias
fuente_noticia(id PK, nombre, dominio UNIQUE, tipo, alcance, modo_acceso,
    feed_url, distrito, robots_ok, ultima_revision, activa)
fuente_noticia_despacho(fuente_id FK, despacho_id FK,
    PRIMARY KEY(fuente_id, despacho_id))   -- distritales por despacho
articulo(id PK, fuente_id FK, url, titulo, bajada_propia, publicado_en,
    capturado_en, hash_dedup UNIQUE)
    INDEX (fuente_id, capturado_en DESC)
articulo_hash(hash_dedup PK)               -- dedup forever sin retener artículo
clasificacion_articulo(id PK, articulo_id FK UNIQUE, area_tematica,
    palabras_clave, modelo, prompt_version, generado_en)
articulo_relevante(articulo_id FK, despacho_id FK, score, razon,
    expedientes_tocados UUID[], generado_en,
    PRIMARY KEY(articulo_id, despacho_id))
mencion(id PK, articulo_id FK, legislador_id FK, despacho_id FK, snippet_contexto,
    tono, confianza_tono, alcance_medio, detectado_en, notificada)
    INDEX (despacho_id, detectado_en DESC)
    INDEX (legislador_id, detectado_en DESC)

-- WhatsApp
destinatario(id PK, despacho_id FK, usuario_id FK NULL, nombre, rol_interno,
    telefono_e164, recibe_briefing_diario, recibe_alertas_menciones,
    recibe_alertas_otras, opt_in_en, opt_out_en, activo,
    UNIQUE(despacho_id, telefono_e164))
plantilla_whatsapp(name PK, idioma, categoria, body_params TEXT[],
    estado_meta, aprobada_en, contenido_referencia)
envio_whatsapp(id PK, destinatario_id FK, despacho_id FK, plantilla_name FK,
    tipo, payload_params JSONB, correlativo_id UUID NULL,
    enviado_en, estado, message_id_meta UNIQUE NULL, error)
    INDEX (despacho_id, enviado_en DESC)
    INDEX (message_id_meta)
alerta_mencion_enviada(id PK, destinatario_id FK, tipo, menciones_ids UUID[],
    plantilla_meta, enviado_en, estado, error)
```

### Reglas de diseño que esta decisión fija

1. **Cuerpo de artículo nunca persiste.** No hay columna en `articulo`.
   El scraper baja el cuerpo a memoria del worker para detección y
   clasificación, lo descarta tras procesar. Auditable por esquema.
2. **Texto del BO sí persiste**, en tabla aparte `norma_bo_texto`. El
   esquema separa cuerpo de metadata: las queries de UI sólo hacen JOIN
   cuando un endpoint interno futuro lo pida (ej. búsqueda full-text).
3. **`despacho_id` desnormalizado en `envio_whatsapp`.** Aunque
   derivable vía `destinatario.despacho_id`, lo desnormalizamos para
   queries auditables por despacho sin JOIN. Trade-off explícito por
   read-perf + simplicidad de tenant isolation.
4. **`hash_dedup` en tabla aparte (`articulo_hash`).** Cuando un
   artículo se purga por retención (12 meses, D10), su hash queda para
   evitar re-procesar la misma URL si vuelve a aparecer en un feed.
5. **`norma_bo_accionable` y `articulo_relevante` se RECALCULAN.** No
   son inmutables: cuando el despacho cambia su perfil de interés, se
   regeneran con el nuevo perfil. No hay versionado.
6. **Clasificaciones son cacheables por hash.** `hash_sumario` en
   `norma_bo` permite saltear re-clasificación si el contenido no
   cambió y la `prompt_version` sigue igual.
7. **`Mencion` referencia `legislador_id` (no `legislador_nombre`).**
   El catálogo de legisladores existe (`feat/05`). Esto difiere de
   `voto_legislador` (ADR 0005) por contexto distinto: la mención se
   detecta tras matchear contra el padrón.
8. **`fuente_noticia` tiene dos scopes**: global (las 9 nacionales y
   políticas), por despacho (las 2-3 distritales). La tabla puente
   `fuente_noticia_despacho` cubre las distritales sin duplicar el
   catálogo.

### Retenciones (D3, D10)

- `norma_bo`, `norma_bo_texto`, `clasificacion_norma_bo`,
  `norma_bo_accionable`: **forever**.
- `articulo`, `clasificacion_articulo`, `articulo_relevante`:
  **12 meses**. Job de purga diaria Celery beat.
- `mencion`: **24 meses**. Purga diaria.
- `articulo_hash`: **forever** (peso mínimo).
- `envio_whatsapp`, `alerta_mencion_enviada`: **forever**
  (auditoría regulatoria de notificaciones).

## Alternativas consideradas

### Una tabla `notificacion` polimórfica para todos los canales

Idea: una sola tabla con `tipo_canal, tipo_payload, payload JSONB`.
Descartado:

- Acopla el modelo a la noción de "canal genérico" cuando hoy sólo
  existe WhatsApp; sobre-ingeniería.
- Las queries por tipo terminan filtrando por JSONB, peor performance.
- El día que entre email/SMS, una migración aditiva es más limpia.

### `texto_completo` en `articulo` con flag `mostrar_publicamente=false`

Descartado. Tener la columna invita a bugs: cualquier endpoint que haga
`SELECT *` la expone. La restricción legal merece materializarse en el
esquema (no existe la columna), no en lógica defensiva.

### `norma_bo_texto` embebido en `norma_bo`

Descartado. Las queries de listado (`GET /bo/normas?fecha=…`) jamás
necesitan el cuerpo; cargarlo en cada page-load infla I/O. La
separación deja la fila ligera y el cuerpo accesible sólo cuando se
necesita.

### Sin `articulo_hash`, dedup contra `articulo.hash_dedup`

Descartado. La retención de 12m purgaría el hash; tras purga, una URL
vieja podría reprocesarse generando duplicados en clasificación o
gasto LLM innecesario. Tabla aparte forever lo evita.

### `despacho_id` no desnormalizado en `envio_whatsapp`

Descartado. Las queries de auditoría por despacho son frecuentes y la
tenant isolation se simplifica con WHERE directo en lugar de JOIN.
Costo: si un destinatario cambia de despacho (raro), hay que
actualizar denormalización. Aceptable.

### Multi-legislador por despacho ahora

Descartado por D4. Si entra en v2 se agrega tabla
`legislador_observado(despacho_id FK, legislador_id FK, alias_extra
TEXT[])` y `Mencion` deja de requerir tenant-único.

## Consecuencias

### Positivas

- Tres dominios distintos con esquema cohesivo y explícito.
- Restricciones legales del producto materializadas en el esquema, no
  delegadas a lógica defensiva.
- Auditoría WhatsApp completa por desnormalización de `despacho_id`.
- Cache barata: hashes habilitan saltar trabajo LLM redundante.
- Retenciones diferenciadas optimizan storage sin perder valor.

### Negativas / Trade-offs aceptados

- **8 tablas nuevas** en una sola migración alembic. Es grande pero
  cohesiva — separarlas en 3 migraciones rompe FKs entre dominios.
- **Desnormalización de `despacho_id`** en envíos exige cuidado si un
  destinatario migra de despacho. Trigger SQL puede evitar
  inconsistencias.
- **`fuente_noticia_despacho`** introduce un nivel extra de scope que
  toca los queries de polling.
- **No hay versionado de `NormaBOAccionable`**: re-cálculo destruye
  histórico. Aceptable porque la "accionabilidad" es una vista
  derivada, no un hecho.

### Migración / alembic

Una migración: `20260603_0001_bo_noticias_menciones_whatsapp.py` con
las 13 tablas + índices + tipos enum.

Migración aditiva (no toca tablas existentes). Reversible.

## Trabajo derivado

- feat/39.1: `PerfilInteresDespacho` + `SembrarPerfilInteres`.
- feat/39.2: dominio BO (entidades + puertos + repos).
- feat/40.1: dominio Noticias + Menciones.
- feat/41.1: dominio WhatsApp.
- Migración alembic conjunta lanzada al iniciar feat/39.
