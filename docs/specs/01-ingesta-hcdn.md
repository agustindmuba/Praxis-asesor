# 01 — Ingesta de expedientes HCDN

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 1
- **Depende de**: ADR 0001 (stack), ADR 0002 (modelo Expediente), spike `feat/scraping-spike` (validado).

## Problema

El despacho parlamentario necesita ver la información de un expediente sin tener que abrir el portal oficial, copiar/pegar, ni recordar la URL exacta. Hoy ese flujo es manual, propenso a error, y depende de que el usuario tenga abierta la pestaña del portal.

Como **primera feature del MVP**, queremos que Praxis Asesor pueda **traer un expediente de HCDN dado su número** (`NNNN-X-YYYY`) y representarlo internamente con la estructura completa: número, tipo, extracto, sumario, firmantes (con bloque y distrito), giros, trámite y enlace al texto original.

## Usuario y caso de uso

El consumidor de esta feature son las siguientes features del MVP (búsqueda, seguimiento, alertas), no el usuario final directamente. Esta feature es **infraestructura de datos**.

Caso de uso técnico:

```
DADO un número de expediente "1497-D-2024"
CUANDO el sistema pide ese expediente vía FuenteExpedientes
ENTONCES devuelve un Expediente con todos los campos del dominio,
         o lanza ExpedienteNoEncontrado si no existe.
```

## Solución propuesta

Adaptador HCDN que implementa el puerto `praxis.application.ports.FuenteExpedientes`. Bajo el capó:

1. Descompone el número en sus tres partes: `1497`, `D`, `2024`.
2. POST al buscador oficial (`https://www.diputados.gob.ar/proyectos/resultado.html`) con el form correcto (ver `docs/data-sources.md` §HCDN).
3. Parsea la HTML resultante hacia entidades de dominio (Expediente + Trámite + Firmante + Giro).
4. Devuelve el objeto al caso de uso que lo pidió.

Sin persistencia en esta feature. Esto lo agrega un PR siguiente cuando definamos las primeras migraciones reales con Alembic.

## Criterios de aceptación

- [ ] Existe `praxis.domain.expediente.Expediente` con todos los campos modelados en ADR 0002.
- [ ] Existe `praxis.application.ports.FuenteExpedientes` (abstract class).
- [ ] Existe `praxis.infrastructure.scrapers.hcdn.HcdnScraper` implementando el puerto.
- [ ] El scraper extrae correctamente, para `1497-D-2024`, `0001-D-2024` y `0001-PE-2024`:
  - Número, tipo, cámara.
  - Extracto y sumario completo.
  - Lista de firmantes con `(nombre, distrito, bloque)`.
  - Giros a comisiones (lista).
  - Trámite como event-log (puede estar vacío).
  - URL del PDF original (cuando exista).
- [ ] Tests de contrato pasan usando HTML capturado del spike como fixtures — **no hacen HTTP real** en CI.
- [ ] Lint, type-check y tests verdes (`uv run ruff check`, `uv run mypy praxis`, `uv run pytest`).
- [ ] Documentación del adaptador en `praxis/infrastructure/scrapers/hcdn/README.md`.

## Fuera de alcance

Explícitamente NO entra en esta feature (se aborda en features siguientes):

- **Enumeración / búsqueda paginada** de expedientes nuevos. Solo "traeme este número exacto". La feature 2 (HSN) y la 3 (normalización) sí cubren listings.
- **Persistencia en Postgres**. Lo que devuelve el scraper se queda en memoria. Persistencia llega cuando arranque el módulo de DB.
- **Sistema de cache** (HTTP/Redis) más allá del rate limit y los retries básicos. Caching agresivo es un PR siguiente.
- **Manejo de versionado** del expediente (cambios entre fetches). Por ahora cada fetch devuelve un snapshot.
- **PDF parsing**. El texto del expediente se referencia por URL; no se descarga ni se parsea su contenido todavía.
- **Comisión como entidad**. El campo `comision` en Giro es un string libre (el nombre como aparece en HCDN). Mapear a una entidad `Comision` viene con la feature 6 (catálogo de comisiones).
- **Legislador como entidad**. Lo mismo: `firmante.nombre` es string libre. Vinculación al padrón viene con la feature 5.

## Notas técnicas

Toda la información de cómo HCDN expone los datos está en [`../data-sources.md`](../data-sources.md) §HCDN. Resumen ultra-corto:

- **Endpoint**: `POST https://www.diputados.gob.ar/proyectos/resultado.html`.
- **Form fields clave**: `strNumExp`, `strNumExpOrig`, `strNumExpAnio`, más `strMostrar*` en `on`.
- **Parsing**:
  - Extracto: `div.dp-texto`.
  - Sumario: `div[id^="sumario"]`.
  - Firmantes: tabla con headers `FIRMANTE / DISTRITO / BLOQUE`.
  - Trámite: tabla con `CÁMARA / MOVIMIENTO / FECHA / RESULTADO`.
  - PDF: `<a href>` a `www4.hcdn.gob.ar/.../<exp>.pdf`.
- **Encoding**: UTF-8.
- **Rate limit**: 1 req/seg por dominio (también para `www4.hcdn.gob.ar`, que es un dominio distinto).
- **UA**: `PraxisAsesor/0.x (+contacto@dominio.com)`.

El parser **NO debe ser frágil a cambios cosméticos** del portal:
- Anclar a labels y headers semánticos, no a XPath posicionales.
- Si HCDN agrega columnas, no debe romperse mientras los headers conocidos sigan presentes.
- Cubrir con tests de contrato HTML real para que cualquier cambio del portal dispare CI roja.

## Plan de tests

- **Unit (dominio)**: construcción de `Expediente`, parseo de `NumeroExpediente` desde string, invariantes de las entidades.
- **Unit (parser)**: alimentar el parser con HTML fixturizado, verificar que extrae lo esperado.
- **Contract test**: para cada uno de los 3 expedientes validados en el spike, snapshot del HTML real y aserciones sobre el `Expediente` parseado. Estos tests son **estables**: si HCDN cambia el portal, fallan acá y se actualiza el snapshot consciente.
- **Integration (opcional, no en CI)**: marker `@pytest.mark.network` para tests que hacen HTTP real al portal. No corren en CI por default.

## Riesgos

- **El portal cambia silenciosamente** y los tests con HTML viejo siguen pasando aunque el adaptador real falle en producción. Mitigación: agregar un job programado (semanal) que corra los tests con `@pytest.mark.network` contra el portal vivo y alerte si rompen. Fuera de scope de esta feature, agendar.
- **Latencia y disponibilidad** del portal en horario pico. Mitigación: retries con backoff exponencial, timeout corto, circuit breaker en una iteración futura.
- **Tipos no estándar de expediente** (ej. `OV-`, `P-`, `CD-`) que no probamos en el spike. Mitigación: el parser es genérico por design, debería funcionar — pero documentar en el README del adaptador qué tipos están confirmados.
