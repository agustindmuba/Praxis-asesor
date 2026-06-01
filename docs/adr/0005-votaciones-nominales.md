# 0005 — Modelo y origen de Votaciones Nominales

- **Estado**: aceptada
- **Fecha**: 2026-05-31
- **Autores**: Agustín DM
- **Supersede a**: —
- **Superseded por**: —

## Contexto

El briefing pre-sesión (spec 14) necesita, para cada proyecto del orden
del día, **recomendar al despacho cómo votar**. La heurística aprobada
requiere conocer **cómo votó cada bloque la última vez que se discutió
un proyecto similar**.

Hoy `Praxis Asesor` no tiene votaciones nominales: el modelo de dominio
cubre `Expediente`, `Tramite`, `Firmante`, `Giro`, pero **no el acto del
voto** ni quién votó qué.

Restricciones a respetar:

1. **No depender del Observatorio** (instrucción explícita del owner, ver
   `MEMORY.md`). Praxis tiene que poder scrapear y persistir sus propias
   votaciones, aunque el modelo del Observatorio sea más rico.
2. **Compatibilidad con la regla hexagonal del ADR 0001**: la fuente de
   las votaciones es un adaptador en `infrastructure/`. El dominio define
   las entidades sin saber cómo se obtuvieron.
3. **Multi-cámara**: el modelo debe servir a HCDN y a HSN aunque por ahora
   solo implementemos HCDN.
4. **Bajo costo de scope**: el briefing no necesita el voto de cada
   legislador individual con altísima precisión — basta con saber **cómo
   votó el bloque en mayoría**. El detalle por legislador es feature
   futura (alertas tipo "Juliano se desvió del bloque").

## Decisión

### Entidades de dominio nuevas

```python
@dataclass(frozen=True, slots=True)
class Votacion:
    """Una votación nominal en el recinto. Identifica el momento."""
    id: UUID | None
    camara: Camara
    fecha: date
    sesion: str                   # ej "Período 144 - Reunión 3 - Acta 20"
    asunto: str                   # texto libre del portal — el qué se votó
    expediente_id: UUID | None    # vinculado si se pudo cruzar; None si "asunto suelto"
    titulo_od: str | None         # ej "O.D. 84" parseado del asunto; permite cruce diferido vía OrdenDelDia (spec 14)
    acta_id_hcdn: int | None      # identificador propio del portal HCDN, ej 5937
    acta_pdf_url: str | None      # URL al PDF oficial /pdf/acta/{id}
    tipo: Literal["nominal", "general", "mocion", "otro"]
    resultado_afirmativos: int
    resultado_negativos: int
    resultado_abstenciones: int
    resultado_ausentes: int
    aprobada: bool
    fuente_url: str | None


@dataclass(frozen=True, slots=True)
class VotoLegislador:
    """Cómo votó UN legislador en UNA votación."""
    votacion_id: UUID
    legislador_nombre: str        # texto libre del portal, no necesariamente FK
    bloque: str | None
    distrito: str | None
    voto: Literal["afirmativo", "negativo", "abstencion", "ausente"]
```

### Por qué dos entidades y no una

El portal HCDN expone la votación como un encabezado (sesión, asunto,
totales) **+ una tabla con los votos individuales**. Separamos `Votacion`
(agregado) de `VotoLegislador` (item) por:

- Las recomendaciones de voto del briefing solo necesitan **agregados por
  bloque**, no votos individuales. Podemos calcularlos sin cargar votos.
- Si el legislador se mapea a un `Legislador` canónico en el futuro (feat
  pendiente), `VotoLegislador.legislador_nombre` se reemplaza por FK sin
  romper `Votacion`.
- Eventos futuros tipo "Juliano se desvió del bloque" se construyen
  encima de `VotoLegislador` sin tocar la lógica de recomendación.

### Cruce con `Expediente` (best-effort)

El portal HCDN identifica el asunto votado a veces con número de
expediente, a veces solo con descripción. El scraper intenta el cruce:

1. Si hay número de expediente en el texto → resolver contra `expediente`
   table.
2. Si no → dejar `expediente_id = None`. El asunto queda en texto libre.

Aceptamos pérdida de información en el cruce. Las votaciones sin
expediente son útiles igualmente (presentismo, perfil de bloque), pero
no aportan al briefing.

### Por qué no hacer FK estricta a Legislador

Hoy `Legislador` no existe como entidad persistida en Praxis (era spec 5
diferido). Postergar el módulo de votaciones nominales hasta tener el
catálogo de legisladores duplica el camino crítico del MVP.

Decisión: persistir el voto con **nombre de legislador como string + bloque
como string**. Cuando se construya el catálogo de legisladores, una
migración tira un UPDATE con LIKE para resolver FKs. La integridad
referencial se sacrifica a cambio de no bloquear el MVP.

### Fuente

`infrastructure/scrapers/hcdn/votaciones.py`: scraper async que itera el
portal de actas de votaciones, parsea la tabla nominal, persiste.

URL base: `https://votaciones.hcdn.gob.ar/` (a confirmar en spike previo).

Rate limit: 1 req/s (mismo que `HcdnScraper`).

### Persistencia

Dos tablas nuevas:

```
votacion
  id UUID PK
  camara VARCHAR(8) NOT NULL
  fecha DATE NOT NULL
  sesion TEXT NOT NULL
  asunto TEXT NOT NULL
  expediente_id UUID FK NULL → expediente.id
  titulo_od TEXT NULL                     -- ej "O.D. 84"
  acta_id_hcdn INTEGER NULL UNIQUE        -- ID propio del portal HCDN
  acta_pdf_url TEXT NULL
  tipo VARCHAR(20) NOT NULL
  resultado_afirmativos INT NOT NULL
  resultado_negativos INT NOT NULL
  resultado_abstenciones INT NOT NULL
  resultado_ausentes INT NOT NULL
  aprobada BOOLEAN NOT NULL
  fuente_url TEXT NULL
  creado_en TIMESTAMPTZ DEFAULT now()
  INDEX (camara, fecha)
  INDEX (expediente_id) WHERE expediente_id IS NOT NULL
  INDEX (titulo_od) WHERE titulo_od IS NOT NULL

voto_legislador
  votacion_id UUID FK → votacion.id ON DELETE CASCADE
  legislador_nombre TEXT NOT NULL
  bloque TEXT NULL
  distrito TEXT NULL
  voto VARCHAR(15) NOT NULL
  PRIMARY KEY (votacion_id, legislador_nombre)
  INDEX (bloque)
```

### Repo + puerto

```python
class VotacionRepository(ABC):
    async def crear(self, v: Votacion, votos: list[VotoLegislador]) -> Votacion: ...
    async def buscar_por_expediente(self, expediente_id: UUID) -> list[Votacion]: ...
    async def buscar_ultima_por_bloque_y_area(
        self,
        *,
        bloque: str,
        area_tematica: str,
        antes_de: date,
    ) -> Votacion | None: ...
```

La última query es la que alimenta la recomendación de voto del briefing
(página 3).

## Consecuencias

### Positivas

- El briefing puede recomendar voto con justificación basada en datos
  reales, no en deducción.
- Habilita alertas futuras de "Juliano se desvió del bloque" sin nuevo
  modelo.
- Habilita métricas de presentismo del despacho.

### Negativas / Trade-offs

- 3-5 días extra en el critical path del MVP.
- `VotoLegislador.legislador_nombre` como string es deuda técnica
  asumida. Se resuelve cuando se construye el catálogo (spec 5 diferida).
- Las votaciones sin expediente cruzado son ~30-40% del volumen
  (estimado por experiencia de Agustín). Aceptamos el ruido.
- No cubre HSN en v1. El briefing de senado tendrá `recomendacion = "sin
  antecedente"` en la mayoría de los casos.

### Migración / alembic

Migración nueva: `20260601_0001_votaciones.py` con las dos tablas y los
índices.

## Alternativas consideradas

- **Consumir el dataset del Observatorio**: rechazada por instrucción
  explícita del owner.
- **Modelar voto como atributo de `TramiteEvento`**: rechazada — un
  trámite es eventos del expediente, y una votación es un acto del
  recinto. Mezclarlos rompe la semántica del trámite.
- **Solo agregados, sin `VotoLegislador`**: rechazada — el costo extra
  de modelar el detalle individual es mínimo (una tabla más) y abre
  futuros casos de uso sin re-migración.
- **Esperar al catálogo de legisladores**: rechazada — bloquea el MVP
  por una mejora estructural que no es crítica para vender el briefing.

## Trabajo derivado

- feat/26.1: ADR escrito (este).
- feat/26.2: scraper `infrastructure/scrapers/hcdn/votaciones.py`.
- feat/26.3: modelos ORM + migración alembic.
- feat/26.4: `VotacionRepository` + tests.
- feat/26.5: script `scripts/seed_votaciones_hcdn.py` para sembrar
  votaciones del año en curso.
- feat/26.6: integración en `GenerarBriefing.execute()` para recomendación
  de voto en página 3.
