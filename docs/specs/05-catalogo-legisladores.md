# 05 — Catálogo de legisladores y bloques

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 5
- **Depende de**: ADR 0001 (stack), ADR 0002 (modelo).

## Problema

Las features 1-4 modelan expedientes y trámites pero referencian a legisladores como string libre (`Firmante.nombre`). Para alertas, filtros por autor, vinculación cruzada y dashboards de bloque, se necesita un catálogo del padrón vigente: lista canónica de diputados y senadores activos con sus atributos (distrito, bloque, mandato, etc.).

## Decisión de fuente de datos

Se reusan los CSVs del [Observatorio de Comportamiento Parlamentario Nacional](../../../Observatorio), licenciados como CC BY 4.0. **No se modifica código del Observatorio**: los CSVs se copian (vendor) a `backend/data/padron/` y se versionan en este repo.

**Justificación**: el Observatorio ya hizo el trabajo de scrapeo y limpieza. Re-implementar sería duplicar esfuerzo. La regla guardada en memoria del usuario admite reuso si no implica modificar Observatorio (ver [[feedback project_praxis_asesor]] §"Regla de reutilización de datos del Observatorio"). Vendor + snapshot es lo más limpio: cero acoplamiento path-time, refresco manual cuando convenga.

**Refresco**: cuando el padrón cambie (recambio bicameral, asunciones, etc.), re-copiar los CSVs del Observatorio a este repo en un PR de refresh. Se documenta en el README del adaptador.

**Atribución**: los headers de los CSVs ya incluyen la cita CC BY 4.0. El README del módulo la repite.

## Solución propuesta

### Modelo de dominio

`praxis/domain/legislador.py`:

- `Legislador` (frozen dataclass): identificador `slug` + atributos.
- `Bloque` (frozen dataclass): `nombre` + `camara`.

### Puerto

`praxis/application/ports.py` agrega:

- `CatalogoLegisladores` (ABC):
  - `listar(camara) -> list[Legislador]`.
  - `buscar_por_slug(slug, camara) -> Legislador`.
  - `buscar_por_nombre(query) -> list[Legislador]` — match case-insensitive sobre apellido + nombre.

### Adaptador

`praxis/infrastructure/padron/csv_repository.py`:

- `CsvPadronRepository` implementa `CatalogoLegisladores`. Lee los CSVs vendored al inicio (cache en memoria).

## Caso de uso técnico

```
DADO un slug "haguirre" + Camara.HCDN
CUANDO se invoca catalogo.buscar_por_slug(slug, camara)
ENTONCES devuelve Legislador con apellido="Aguirre", nombre="Hilda",
         distrito="LA RIOJA", bloque=Bloque(nombre="UNIÓN POR LA PATRIA", camara=HCDN), etc.
```

## Criterios de aceptación

- [ ] CSVs vendored en `backend/data/padron/`.
- [ ] `praxis.domain.legislador` con `Legislador` y `Bloque` (frozen dataclasses).
- [ ] `praxis.application.ports.CatalogoLegisladores` definido.
- [ ] `praxis.infrastructure.padron.CsvPadronRepository` implementa el puerto.
- [ ] El repo carga 257 diputados + 72 senadores desde los CSVs vendored.
- [ ] Búsqueda por slug, por nombre, listado por cámara funcionan.
- [ ] Tests unit de dominio + integración del repo con datos reales.
- [ ] Lint + type-check + tests verdes.
- [ ] README del adaptador con la atribución CC BY 4.0.

## Fuera de alcance

- **Bloques como entidad standalone** con presidente/secretario/etc. Por ahora `Bloque` es solo nombre+cámara; ampliarlo es feature aparte.
- **Histórico de mandatos** (legisladores pasados). El padrón actual es solo vigentes.
- **Refresh automático** de los CSVs. Manual por ahora.
- **Vinculación de `Firmante.nombre` con `Legislador`**. La feature 5 expone el catálogo; el matching desde firmantes va en una feature siguiente.
- **Senadores anteriores a 2023**: el CSV trae solo vigentes 2023-2029.

## Notas técnicas

- Los CSVs tienen comentarios al inicio (`# Dataset: ...`). Filtrarlos al parsear.
- Los campos de fecha (`fecha_inicio_mandato`, `fecha_fin_mandato`, `fecha_nacimiento`, `padron_snapshot_fecha`) vienen en formato ISO `YYYY-MM-DD`.
- `edad_anios` puede venir vacío (especialmente en senadores donde fecha_nacimiento no siempre se publica). Parsearlo como `int | None`.
- `genero` es `F`/`M`/vacío.
- Slug es ID natural: para HCDN es estilo `haguirre` (h+apellido inicial+apellido), para HSN es estilo `s546` (s+número). Distintos formatos por cámara, pero únicos.
