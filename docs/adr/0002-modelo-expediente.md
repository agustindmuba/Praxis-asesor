# 0002 — Modelo de Expediente, Trámite y Firmante

- **Estado**: aceptada
- **Fecha**: 2026-05-27
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —

## Contexto

La feature 1 del MVP (ver `docs/specs/01-ingesta-hcdn.md`) requiere introducir las primeras entidades de dominio. El spike (`feat/scraping-spike`) validó que ambas cámaras (HCDN y HSN) exponen información rica sobre cada expediente, pero la **forma es distinta**:

- **HCDN** entrega un trámite como **event-log**: tabla con filas `(cámara, movimiento, fecha, resultado)`. Apta para `list[TramiteEvento]`.
- **HSN** entrega un trámite como **timestamps de etapas**: fechas de Mesa de Entradas, Dado Cuenta, Dir. Gral. Comisiones, dictamen, más giros con fechas in/out. NO hay un event-log.

Necesitamos una **forma común** que el dominio entienda sin saber de qué cámara viene el dato. La regla hexagonal (ADR 0001) dice que las particularidades de cada fuente viven en `infrastructure/`, no en `domain/`.

Restricciones que la decisión debe respetar:

1. **Un solo tipo `Expediente`** sirve a ambas cámaras (no `ExpedienteHcdn` y `ExpedienteHsn` separados).
2. **`Trámite` es event-log** en el dominio. El adaptador HSN deriva eventos sintéticos a partir de los timestamps de etapas (preservando el orden cronológico).
3. **Value objects** para campos con invariantes propias (`NumeroExpediente`, `Camara`, `EstadoExpediente`, `TipoExpediente`).
4. **Sin acoplamiento a infraestructura**: nada de `texto_url` con la lógica de cómo construirlo, nada de IDs de DB.
5. **Inmutabilidad** donde sea natural: las entidades de dominio que vienen del scraper son snapshots, no mutables.

## Decisión

### Value objects

#### `Camara` (enum)

```python
class Camara(StrEnum):
    HCDN = "HCDN"  # Honorable Cámara de Diputados de la Nación
    HSN = "HSN"    # Honorable Senado de la Nación
```

#### `TipoExpediente` (enum)

```python
class TipoExpediente(StrEnum):
    LEY = "ley"
    RESOLUCION = "resolucion"
    DECLARACION = "declaracion"
    COMUNICACION = "comunicacion"
    DECRETO = "decreto"           # uso interno (DPCD, DSCO, etc.)
    OTRO = "otro"
```

#### `OrigenExpediente` (enum)

Origen del expediente (quién lo presenta). Distinto de `Camara` (dónde se trata):

```python
class OrigenExpediente(StrEnum):
    DIPUTADO = "D"     # firmado por un diputado en HCDN
    SENADOR = "S"      # firmado por un senador en HSN
    EJECUTIVO = "PE"   # mensaje del Poder Ejecutivo
    JEFATURA = "JGM"   # Jefatura de Gabinete (raro)
    OTRO = "OTRO"      # tipos menos frecuentes (OV, P, CD, etc.)
```

#### `NumeroExpediente` (frozen dataclass / value object)

```python
@dataclass(frozen=True, slots=True)
class NumeroExpediente:
    numero: int              # 1497
    origen: OrigenExpediente # D
    anio: int                # 2024
    camara: Camara           # HCDN (la cámara DONDE se trata)
```

Representación canónica como string:
- HCDN: `"NNNN-X-YYYY"` (ej. `"1497-D-2024"`).
- HSN: `"NNNN/YY"` con `origen` y `tipo` accesibles por separado (HSN no los embebe en el número; la URL es `/verExp/NNN.YY/ORIGEN/TIPO`).

Métodos de paseo: `NumeroExpediente.parse(s: str, camara: Camara) -> NumeroExpediente`.

#### `EstadoExpediente` (enum, evolución a futuro)

```python
class EstadoExpediente(StrEnum):
    INGRESADO = "ingresado"
    EN_COMISION = "en_comision"
    CON_DICTAMEN = "con_dictamen"
    APROBADO_PARCIAL = "aprobado_parcial"  # media sanción en una cámara
    SANCIONADO = "sancionado"
    ARCHIVADO = "archivado"
    CADUCO = "caduco"  # Ley 13.640
    DESCONOCIDO = "desconocido"
```

Para esta feature, el scraper devuelve `DESCONOCIDO` salvo que el portal explicite el estado. Inferencia de estado desde el trámite va en una feature posterior.

### Entidades

#### `Firmante` (frozen dataclass)

```python
@dataclass(frozen=True, slots=True)
class Firmante:
    nombre: str           # tal cual aparece en el portal
    distrito: str | None  # ej. "BUENOS AIRES" (None en HSN para algunos casos)
    bloque: str | None    # ej. "UNIÓN POR LA PATRIA"
    orden: int = 1        # 1 = autor principal; 2..N = co-firmantes
```

`nombre` queda como string libre por ahora. Mapeo a `Legislador` (feature 5) va por un servicio aparte.

#### `Giro` (frozen dataclass)

```python
@dataclass(frozen=True, slots=True)
class Giro:
    comision: str                  # nombre tal cual aparece
    fecha_ingreso: date | None
    fecha_egreso: date | None
    orden: int | None              # "ORDEN DE GIRO: 1" en HSN; cabecera/complementario en HCDN
```

#### `TramiteEvento` (frozen dataclass)

```python
@dataclass(frozen=True, slots=True)
class TramiteEvento:
    fecha: date | None             # algunos eventos antiguos no tienen fecha
    camara: Camara
    evento: str                    # movimiento, ej "GIRO A COMISION"
    detalle: str | None = None     # resultado o info adicional
    fuente: str | None = None      # "scraper:hcdn" | "derived:hsn-stages" | etc.
```

El campo `fuente` deja trazabilidad: cuando un evento se deriva de timestamps (caso HSN), queda marcado como tal.

#### `Expediente` (mutable dataclass)

```python
@dataclass(slots=True)
class Expediente:
    numero: NumeroExpediente
    tipo: TipoExpediente
    titulo: str                    # extracto / sumario corto
    sumario: str | None = None     # versión larga si está disponible
    fecha_ingreso: date | None = None
    estado: EstadoExpediente = EstadoExpediente.DESCONOCIDO
    firmantes: list[Firmante] = field(default_factory=list)
    giros: list[Giro] = field(default_factory=list)
    tramite: list[TramiteEvento] = field(default_factory=list)
    texto_url: str | None = None   # URL al PDF / HTML original
    fuente_url: str | None = None  # URL del portal de donde se obtuvo este snapshot
```

Mutable porque a futuro un caso de uso puede enriquecer la entidad (ej. inferir estado desde trámite, vincular firmantes con legisladores).

### Convenciones

- **Fechas siempre `date`**, no `str`. El parser convierte `"12-03-2024"` o `"2024-03-12"` a `date(2024, 3, 12)` en infraestructura. Si no puede parsear, deja `None` y loguea warning.
- **Strings se preservan tal cual** del portal cuando no hay valor agregado en normalizar (nombres de personas, nombres de comisiones). La normalización liviana (whitespace, casing) sí se aplica.
- **Trámite siempre ordenado cronológicamente ascendente**, eventos sin fecha al final.
- **`slots=True`** en todos los dataclass para ahorrar memoria y prevenir typos.

## Alternativas consideradas

### Modelos separados por cámara (`ExpedienteHcdn`, `ExpedienteHsn`)

Descartado. Llevaría a duplicar todos los casos de uso (`BuscarExpedientes` tendría que ramificar por cámara). Rompe el principio hexagonal: las diferencias entre cámaras son cosa de infraestructura, no de dominio.

### Trámite como list[StageInfo] (estilo HSN nativo)

Descartado. Sería un downgrade desde HCDN (perdemos el detalle de cada movimiento). HCDN ofrece el dato más rico; modelar al nivel del peor adaptador habría sido subóptimo.

### TramiteEvento como string libre

Descartado. El campo `evento` necesita ser inspeccionable programáticamente para alertas ("nuevo dictamen", "votación en recinto", "giro"). Lo dejamos `str` por ahora, pero la regla es que esos strings se irán normalizando a un set cerrado a medida que aparezcan. Cuando se cierre el set, se promueve a enum.

### `NumeroExpediente` como string plano

Descartado. La descomposición `(numero, origen, anio, camara)` es necesaria para:
- Buscar por año, por tipo de origen.
- Renderizar en formato amigable.
- Reconstruir URLs hacia portales.

Mantenerlo como value object con `parse()` y `__str__()` da type safety y formateo consistente.

### `id` interno autogenerado en domain

Descartado por ahora. Los IDs son cosa de la capa de persistencia (DB). El dominio identifica expedientes por `NumeroExpediente`. Cuando llegue la DB, el ORM mapeará a un PK.

## Consecuencias

### Que ganamos

- Un único modelo de dominio que sirve a ambas cámaras.
- Trámite uniformemente consultable como event-log (la unidad mínima sobre la que se construyen alertas).
- Trazabilidad explícita (`fuente`) de qué eventos vienen del portal vs. son derivados.
- Type safety en code crítico: `mypy --strict` aplica a `praxis.domain` (ADR 0001).
- Inmutabilidad de los value objects + slots = previene una clase entera de bugs.

### Que aceptamos como costo

- **Trabajo extra en el adaptador HSN** para derivar `TramiteEvento` desde timestamps de etapas. Aceptable: la complejidad se queda contenida en `infrastructure/scrapers/hsn/`.
- **Strings libres** en `firmante.nombre` y `giro.comision` hasta que las features 5/6 introduzcan vinculación. Aceptable como deuda explícita.
- **`EstadoExpediente.DESCONOCIDO`** como default mientras no haya inferencia. Aceptable: mejor que mentir.

### Lo que esta decisión bloquea

Cualquier cambio al modelo de dominio (agregar/quitar campos en `Expediente`, `Tramite`, `Firmante`, `Giro`) requiere un ADR que supersede a éste, **salvo**:

- Agregar valores nuevos a enums existentes (`TipoExpediente`, `OrigenExpediente`, `EstadoExpediente`).
- Agregar campos opcionales (defaultados a `None` o vacío) a entidades, si no rompen invariantes.

## Próximos pasos

1. Implementar value objects en `praxis/domain/value_objects.py`.
2. Implementar entidades en `praxis/domain/expediente.py`.
3. Tests unitarios de dominio (parseo, invariantes).
4. ADR siguiente cuando llegue persistencia (mapeo dominio ↔ tablas SQLAlchemy).

---

## Amendment 1 — 2026-05-27 — Expansión de orígenes, tipos, estado, relación, caducidad

> El cuerpo del ADR anterior se mantiene como histórico. Esta enmienda modifica los enums `OrigenExpediente`, `TipoExpediente` y `EstadoExpediente`, agrega 4 campos a `Expediente`, y refina la lógica del parser HCDN para distinguir mensajes del PE de proyectos de ley. La decisión raíz (un solo modelo común a ambas cámaras, trámite como event-log con `fuente` para trazabilidad, value objects frozen+slots, reglas hexagonales) sigue vigente sin cambios.

### Cambios

#### 1. `OrigenExpediente` se expande

Antes: `DIPUTADO, SENADOR, EJECUTIVO, JEFATURA, OTRO`.

Después:
```python
DIPUTADO            = "D"
SENADOR             = "S"
EJECUTIVO           = "PE"
JEFATURA_GABINETE   = "JGM"    # renombrado desde JEFATURA
REVISION_DIPUTADOS  = "CD"     # nuevo
REVISION_SENADO     = "CS"     # nuevo
PARTICULAR          = "P"      # nuevo
OFICIAL_VARIOS      = "OV"     # nuevo
OTRO                = "OTRO"
```

**Justificación**: `CD`/`CS` son expedientes bicamerales en revisión y tienen tratamiento procedimental propio — no son "otros". `P` (particular) y `OV` (oficial varios) tienen tratamiento diferenciado en el trabajo cotidiano del despacho. Renombrar `JEFATURA → JEFATURA_GABINETE` evita ambigüedad con cualquier otra jefatura institucional.

#### 2. `TipoExpediente` se refactoriza

Antes: `LEY, RESOLUCION, DECLARACION, COMUNICACION, DECRETO, OTRO`.

Después:
```python
PROYECTO_LEY            = "proyecto_ley"           # renombrado desde LEY
PROYECTO_RESOLUCION     = "proyecto_resolucion"    # renombrado desde RESOLUCION
PROYECTO_DECLARACION    = "proyecto_declaracion"   # renombrado desde DECLARACION
PROYECTO_COMUNICACION   = "proyecto_comunicacion"  # renombrado desde COMUNICACION
MENSAJE_PE              = "mensaje_pe"             # nuevo
DECRETO                 = "decreto"
OTRO                    = "otro"
```

**Justificación**: Praxis trabaja con expedientes **en trámite**, no con normas sancionadas. Un proyecto de ley en estudio no es lo mismo que la ley que resultaría: el prefijo `PROYECTO_*` evita la ambigüedad semántica. Un **mensaje del PE** es un objeto procedimental específico — aunque suele contener un proyecto adjunto, su tratamiento parlamentario es distinto.

#### 3. `EstadoExpediente.APROBADO_PARCIAL` se desdobla

Antes: `APROBADO_PARCIAL = "aprobado_parcial"`.

Después:
```python
MEDIA_SANCION_HCDN = "media_sancion_hcdn"
MEDIA_SANCION_HSN  = "media_sancion_hsn"
```

**Justificación**: al asesor le importa saber en qué cámara debe actuar a continuación. El estado genérico no aporta información operativa. Los string values usan siglas (`hcdn`/`hsn`) en lugar de "diputados"/"senado" para consistencia con el enum `Camara`.

#### 4. Nuevo campo `Expediente.expediente_relacionado`

```python
expediente_relacionado: NumeroExpediente | None = None
```

**Justificación**: deja el modelo preparado para vincular el mismo proyecto entre cámaras (caso CD/CS, o reproducciones de proyectos previos). En esta enmienda **no hay matching automático**: el campo se completa manualmente o vía una feature futura.

**Aclaración de semántica**: el campo es **informativo y unidireccional**. No implica que el sistema garantice consistencia bidireccional: si A apunta a B, B no necesariamente apunta a A. La consistencia, cuando importe, será responsabilidad de una feature futura que se encargue de matching/vinculación.

**Alternativa evaluada y descartada**: tabla `expediente_relaciones` con múltiples vínculos por expediente (refundiciones, reproducciones, revisión múltiple). Más expresiva, pero excede el MVP. Si la necesidad se materializa, se promueve con un ADR de migración propio.

#### 5. Nuevos campos `Expediente` para caducidad (Ley 13.640)

```python
fecha_caducidad: date | None = None
fecha_caducidad_original: date | None = None
prorrogado: bool = False
```

**Justificación**: la alerta de caducidad es uno de los gestos de valor más concretos para el despacho. Esta enmienda solo agrega el modelo; la lógica de cálculo (inferir caducidad desde fechas y trámite) va en una feature posterior — ver propuesta de feature "inferencia de estado parlamentario desde trámite" priorizada para bloque 2 del PRODUCT.md.

`fecha_caducidad_original` permite mostrar al usuario "vence el X, originalmente vencía el Y" cuando hubo prórroga.

#### 6. Heurística refinada del parser HCDN para tipo de expediente

El parser HCDN (`praxis.infrastructure.scrapers.hcdn.parser._inferir_tipo`) ahora recibe también el `OrigenExpediente` y aplica la siguiente heurística:

```
Si origen ∈ {EJECUTIVO, JEFATURA_GABINETE}:
    1. Si el texto (extracto + sumario) contiene la palabra completa "mensaje"
       (regex \bmensaje\b, case-insensitive) → MENSAJE_PE.
    2. Si contiene "proyecto de ley" o "proyecto de" → PROYECTO_LEY.
    3. Else (ambiguo) → MENSAJE_PE  (default conservador).

Resto de orígenes (D, S, CD, CS, P, OV, OTRO):
    Comportamiento previo del parser, con renombre LEY → PROYECTO_LEY:
    - Si los primeros 80 caracteres mencionan "declaraci" → PROYECTO_DECLARACION.
    - Si mencionan "resoluci" → PROYECTO_RESOLUCION.
    - Si mencionan "comunicaci" → PROYECTO_COMUNICACION.
    - Else → PROYECTO_LEY.
```

**Justificación de la heurística**: La regla simplista "origen=PE → MENSAJE_PE" sería incorrecta porque el PE también presenta proyectos de ley directos. La heurística inspecciona el texto del sumario para distinguir mensaje (vehículo procedimental) de proyecto (contenido). El default conservador en caso ambiguo es `MENSAJE_PE` porque los mensajes son la mayoría en este origen.

**Decisión adoptada por compromiso**: tener `MENSAJE_PE` en el enum sin que el parser lo use generaría data inconsistente (todos los expedientes PE seguirían siendo PROYECTO_LEY); por eso esta enmienda al modelo se entrega junto con la actualización del parser, no por separado.

### Compatibilidad y migración

- Sin DB todavía → no hay migración de schema.
- Refactor en compile-time: cualquier código que importe el viejo `TipoExpediente.LEY` o `OrigenExpediente.JEFATURA` rompe inmediatamente (deseable: no se puede olvidar de actualizar referencias).
- **Los string values de los enums se eligen ahora con cuidado porque persistirán cuando llegue DB.** Renombrarlos después implicaría migración de datos. Específicamente:
  - `TipoExpediente.*` usa `proyecto_*` y `mensaje_pe` en lowercase con guiones bajos.
  - `OrigenExpediente.*` mantiene los códigos oficiales (`D`, `S`, `PE`, `JGM`, `CD`, `CS`, `P`, `OV`, `OTRO`).
  - `EstadoExpediente.MEDIA_SANCION_*` usa siglas (`hcdn`/`hsn`) por consistencia con `Camara`.

### Lo que se preserva del ADR original

- Modelo único `Expediente` para ambas cámaras.
- `TramiteEvento` como event-log uniforme con `fuente`.
- Value objects frozen + slots.
- Reglas hexagonales y restricciones de dependencias.
- Convenciones de fecha y orden cronológico.
- Invariantes en las dataclasses.
