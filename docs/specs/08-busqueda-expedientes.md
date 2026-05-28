# Spec 08 — Búsqueda y filtrado de expedientes

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/13-busqueda`

## Contexto

Un asesor parlamentario rara vez busca un expediente por número. La interacción
típica es:

- "Mostrame los proyectos de Diputados sobre presupuesto del 2024."
- "¿Qué expedientes firmó Massot que estén en comisión?"
- "¿Qué hay en Salud Pública con dictamen?"

La capa de persistencia ya sabe traer un expediente por id o por número. Falta
filtrar el catálogo por criterios estructurados + un texto libre simple sobre
título y sumario.

## Decisiones

Las tres decisiones de diseño se tomaron arriba (chat de Agustín, 2026-05-28):

1. **Query API**: dataclass `ExpedienteQuery` con campos opcionales. El repo
   expone `buscar(query)` y `contar(query)`. Caso de uso recibe el query como
   value object.
2. **Texto libre**: `ILIKE %texto%` sobre `titulo` + `sumario`. Es portable a
   SQLite (necesario para tests de integración con `aiosqlite`) y a Postgres.
   Se reemplaza por `tsvector` cuando el volumen lo justifique.
3. **Paginación**: `limit/offset` clásico. `limit` default 50, max 200.

## Filtros del MVP

| Campo                    | Tipo               | Match                                |
|--------------------------|--------------------|--------------------------------------|
| `texto`                  | `str`              | `ILIKE %texto%` en titulo + sumario  |
| `anio`                   | `int`              | igualdad exacta                      |
| `tipo`                   | `TipoExpediente`   | igualdad                             |
| `camara`                 | `Camara`           | igualdad                             |
| `origen`                 | `OrigenExpediente` | igualdad                             |
| `estado`                 | `EstadoExpediente` | igualdad                             |
| `autor_nombre`           | `str`              | `ILIKE %nombre%` sobre `firmante.nombre` vía EXISTS |
| `comision`               | `str`              | `ILIKE %comision%` sobre `giro.comision` vía EXISTS |
| `fecha_ingreso_desde`    | `date`             | `>=`                                 |
| `fecha_ingreso_hasta`    | `date`             | `<=`                                 |
| `limit` / `offset`       | `int`              | paginación                           |

Reglas:

- Todos los filtros son `AND`. No hay `OR` en esta iteración.
- `autor_nombre` y `comision` usan **EXISTS** (no JOIN) para evitar inflar el
  result set por hijos múltiples — un expediente con 5 firmantes no se duplica.
- Texto libre: case-insensitive, sin escapado de wildcards `%` y `_` por ahora
  (riesgo bajo: input viene de UI nuestra; los wildcards los puede usar a su
  favor el asesor). Si esto pasa por un endpoint público sin sanitizar, hay
  que escapar.
- Orden por defecto: `fecha_ingreso DESC NULLS LAST, id DESC`.

## Validaciones del `ExpedienteQuery`

- `limit` ∈ [1, 200], default 50.
- `offset` ≥ 0, default 0.
- `fecha_ingreso_desde <= fecha_ingreso_hasta` si ambos están seteados.
- `texto`, `autor_nombre`, `comision`: si se setean, no pueden ser solo
  whitespace (`.strip()` antes de validar).

Violaciones → `ValueError` en `__post_init__`.

## Estructura del resultado

```python
@dataclass(frozen=True, slots=True)
class ResultadoBusqueda:
    items: list[Expediente]
    total: int       # total que matchea el filtro (independiente de limit)
    limit: int
    offset: int
```

`total` se obtiene con un `COUNT(*)` separado sobre el mismo predicate (sin
limit/offset). Es una query adicional, pero la UI lo necesita para mostrar
"mostrando 1-50 de 234".

## Casos de uso

Esta feature no introduce un caso de uso nuevo todavía (eso vendrá con el
endpoint HTTP). El repositorio queda listo para que se le encadene un
`BuscarExpedientes` cuando arme FastAPI.

## Out of scope

- Búsqueda fuzzy / tolerante a typos.
- Ranking por relevancia.
- Búsqueda en texto completo de PDFs adjuntos.
- Filtros `OR` o expresiones booleanas.
- Cursor pagination.
- Búsqueda por trámite (eventos del histórico).

Todo eso entra cuando duela.
