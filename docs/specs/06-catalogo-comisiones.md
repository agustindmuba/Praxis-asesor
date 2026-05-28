# 06 — Catálogo de comisiones por cámara

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 6
- **Depende de**: ADR 0001 (stack), ADR 0002 (modelo).

## Problema

Las features 1-4 referencian comisiones como string libre (`Giro.comision`). Para filtros por comisión, mapeo de integrantes y rutas de trámite, se necesita un catálogo canónico.

## Fuentes de datos

Como en feature 5, **vendor**: snapshot de datos en `backend/data/comisiones/`, refresh manual cuando convenga.

- **HCDN**: vendor de `comisiones_paridad.csv` del [Observatorio](https://github.com/agustindmuba/observatorio) (CC BY 4.0). Snapshot 2026-05-24. Estructura row-per-integrante; el repo deduplica por `comision_slug` y devuelve 93 comisiones distintas. **Caveat**: el CSV upstream se centra en comisiones permanentes; no expone explícitamente el tipo, así que TODAS se modelan como `PERMANENTE`. Cuando aparezca data discriminada, refinar.
- **HSN**: fetch one-shot del endpoint oficial `https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas` → guardado como `comisiones_hsn.json`. Snapshot fetcheado durante el desarrollo de esta feature. 48 comisiones con tipo discriminado (`BICAMERAL ESPECIAL` | `BICAMERAL PERMANENTE` | `UNICAMERAL PERMANENTE`).

## Solución propuesta

### Dominio

`praxis/domain/comision.py`:
- `TipoComision` (StrEnum): `PERMANENTE`, `ESPECIAL`, `BICAMERAL_PERMANENTE`, `BICAMERAL_ESPECIAL`, `OTRO`. Helper `from_text` para mapear strings libres del portal.
- `Comision` (frozen dataclass): `nombre`, `tipo`, `camara`, `slug` (opcional — solo HCDN tiene), `categoria_tematica` (opcional — solo HCDN tiene).

### Puerto

`praxis/application/ports.py` agrega:
- `CatalogoComisiones` (ABC):
  - `listar(camara) -> list[Comision]`.
  - `buscar_por_nombre(query, camara=None) -> list[Comision]`. Case-insensitive substring. Si `camara=None`, busca en ambas.

### Adaptador

`praxis/infrastructure/comisiones/local_repository.py`:
- `LocalCatalogoComisiones`: lee CSV HCDN + JSON HSN al construirse. Eager + cache.

## Caso de uso técnico

```
DADO "ASUNTOS CONSTITUCIONALES" como query
CUANDO catalogo.buscar_por_nombre("Asuntos Constitucionales")
ENTONCES devuelve la comisión HCDN con slug=caconstitucionales,
         tipo=PERMANENTE, categoria_tematica="Justicia, Seguridad y Derechos".
```

## Criterios de aceptación

- [ ] CSVs/JSON vendored en `backend/data/comisiones/`.
- [ ] `praxis.domain.comision` con `Comision` + `TipoComision` (helper `from_text`).
- [ ] `praxis.application.ports.CatalogoComisiones` definido.
- [ ] `praxis.infrastructure.comisiones.LocalCatalogoComisiones` implementa el puerto.
- [ ] El repo carga 93 comisiones HCDN (deduplicadas) + 48 HSN.
- [ ] Búsqueda por nombre case-insensitive, con o sin filtro de cámara.
- [ ] Tests unit de dominio + integración del repo con datos reales.
- [ ] Lint + type-check + tests verdes.
- [ ] README del adaptador con la atribución y caveats.

## Fuera de alcance

- **Composición de comisiones** (integrantes con sus cargos): el CSV HCDN ya tiene la data, pero modelarla como entidad rica (`MiembroComision`) es feature aparte. Por ahora solo el catálogo "qué comisiones existen".
- **Deduplicación bicameral**: una comisión bicameral aparece tanto en HCDN como en HSN. No las dedupeamos automáticamente; se las modela como entrades separadas. Cuando una feature lo necesite, se hace matching.
- **Subcomisiones**: si HCDN/HSN las exponen, no las distinguimos.
- **Refresh automático**: manual.
- **Discriminación de tipo para HCDN**: no podemos por la fuente de datos actual. Todas como PERMANENTE.

## Notas técnicas

- El CSV HCDN tiene una fila por integrante; el repo deduplica por `comision_slug`.
- El JSON HSN tiene `{table: {rows: [{NOMBRE, TIPO_COMISION}, ...]}}`. El tipo viene como texto libre (`"BICAMERAL ESPECIAL"`, etc.); `TipoComision.from_text` lo mapea.
- Tanto el CSV como el JSON se cachean en memoria al construir el repo.
