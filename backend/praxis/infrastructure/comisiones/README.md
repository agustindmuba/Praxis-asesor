# `praxis.infrastructure.comisiones`

Adaptador de catálogo de comisiones. Implementa
`praxis.application.ports.CatalogoComisiones`.

## Archivos

| Archivo | Rol |
|---|---|
| `local_repository.py` | `LocalCatalogoComisiones`: carga CSV HCDN + JSON HSN al construir. |

## Fuentes vendored

`backend/data/comisiones/`:

### HCDN — `comisiones_hcdn_paridad.csv`

Origen: [Observatorio de Comportamiento Parlamentario Nacional](https://github.com/agustindmuba/observatorio) (Quórum, 2026), licencia **CC BY 4.0**.

- 2236 filas, **row-per-integrante**. El repo deduplica por `comision_slug` → 93 comisiones distintas.
- **Caveat**: el CSV upstream se centra en comisiones permanentes; **no expone el tipo de comisión explícitamente**. Por eso TODAS las comisiones HCDN se modelan como `TipoComision.PERMANENTE`. Cuando aparezca una fuente con tipo discriminado, refinar.
- Snapshot: 2026-05-24.

### HSN — `comisiones_hsn.json`

Origen: endpoint oficial `https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas`.

- 48 comisiones, estructura `{table: {rows: [{NOMBRE, TIPO_COMISION}, ...]}}`.
- Tipo discriminado: `UNICAMERAL PERMANENTE`, `BICAMERAL PERMANENTE`, `BICAMERAL ESPECIAL`. Mapeo a `TipoComision` via `from_text`.
- Snapshot fetcheado durante el desarrollo de esta feature.

## Refresco

Cuando convenga (cambios estructurales, no por movimientos internos):

```bash
# HCDN: re-copiar desde Observatorio.
cp ../Observatorio/frontend/descargas/comisiones_paridad.csv \
   backend/data/comisiones/comisiones_hcdn_paridad.csv

# HSN: re-fetchear endpoint oficial.
uv run python -c "
import httpx, json
r = httpx.get('https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas',
              headers={'User-Agent': 'PraxisAsesor/0.1 (+contacto@dominio.com)'}, timeout=30)
with open('backend/data/comisiones/comisiones_hsn.json', 'w', encoding='utf-8') as f:
    json.dump(r.json(), f, ensure_ascii=False, indent=2)
"
```

## Lo que NO hace todavía

- **Composición** (integrantes con cargos): el CSV HCDN lo tiene, pero no lo exponemos; feature aparte.
- **Deduplicación bicameral**: una comisión bicameral aparece tanto en HCDN como en HSN. Se las modela como entradas separadas hasta que una feature requiera matching.
- **Subcomisiones**: ignoradas.
- **Refresh automático**: manual.

## Referencias

- Spec: [`../../../docs/specs/06-catalogo-comisiones.md`](../../../../docs/specs/06-catalogo-comisiones.md).
- Fuente HCDN: Observatorio del usuario.
- Fuente HSN: portal oficial, endpoint datos abiertos.
