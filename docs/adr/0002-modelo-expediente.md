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
