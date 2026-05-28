# `praxis.infrastructure.padron`

Adaptador de catálogo del padrón legislativo. Implementa
`praxis.application.ports.CatalogoLegisladores`.

## Archivos

| Archivo | Rol |
|---|---|
| `csv_repository.py` | `CsvPadronRepository`: carga los CSVs vendored al construir. |

## Fuente de datos

Los CSVs vendored en `backend/data/padron/` vienen del [Observatorio de Comportamiento Parlamentario Nacional](https://github.com/agustindmuba/observatorio) (Quórum, 2026), licenciados **CC BY 4.0**.

- `padron_diputados.csv` — 257 diputados vigentes (mandatos 2023-2027), snapshot 2026-02-17.
- `padron_senado.csv` — 72 senadores vigentes (mandatos 2023-2029), snapshot 2026-05-23.

**Atribución obligatoria al redistribuir o derivar** según términos de CC BY 4.0:

> Quórum (2026), *Observatorio de Comportamiento Parlamentario Nacional*. Datos extraídos del padrón oficial HCDN/HSN. CC BY 4.0.

## Refresco

Cuando el padrón cambie (asunciones, recambio bicameral en diciembre, etc.):

1. En Observatorio, regenerar los CSVs:
   ```bash
   python -m padron.scraper_padron --all
   ```
2. En Praxis Asesor, copiar de vuelta:
   ```bash
   cp ../Observatorio/frontend/descargas/padron_*.csv backend/data/padron/
   ```
3. PR con título `data(padron): refresh snapshot YYYY-MM-DD`.

No automatizamos el refresh: el padrón cambia poco y un PR manual permite reviewar cambios masivos antes de que entren a producción.

## Convenciones

- Eager loading: el repositorio carga ambos CSVs al construirse. ~330 filas en memoria; trivial.
- Caches en memoria por cámara y por slug.
- Comentarios del CSV (`# Dataset: ...`) se filtran antes del parseo.
- Fechas en ISO `YYYY-MM-DD`. `edad_anios` y otros campos pueden venir vacíos.

## Lo que NO hace todavía

- **Bloques como entidad rica**: `Bloque` es solo `(nombre, camara)`. Atributos (presidente, secretario, integrantes) son feature aparte.
- **Histórico de mandatos**: solo legisladores vigentes. Para legisladores que ya no están, esperar feature dedicada.
- **Refresh automático**: manual. Razón: el padrón es estable y permite review.
- **Vinculación con `Firmante.nombre`**: el catálogo está; el matching desde firmantes va en otra feature.

## Referencias

- Spec: [`../../../docs/specs/05-catalogo-legisladores.md`](../../../../docs/specs/05-catalogo-legisladores.md).
- Fuente upstream: el Observatorio en el repo del usuario.
