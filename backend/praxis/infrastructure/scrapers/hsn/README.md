# `praxis.infrastructure.scrapers.hsn`

Adaptador concreto: scraper del portal del Senado de la Nación (HSN). Implementa el puerto `praxis.application.ports.FuenteExpedientes`.

## Archivos

| Archivo | Rol |
|---|---|
| `scraper.py` | `HsnScraper`: async I/O con httpx, rate limit, retries, mapeo de enums a códigos URL. |
| `parser.py` | Parseo puro HTML → entidades. Expone también `derive_tramite_from_stages` para tests directos. |

## Endpoint usado

`GET https://www.senado.gob.ar/parlamentario/comisiones/verExp/<NUM>.<YY>/<ORIGEN>/<TIPO>`

| Componente | Valores |
|---|---|
| `<NUM>` | Número del expediente, sin ceros a la izquierda. |
| `<YY>` | Año a 2 dígitos (24 = 2024). |
| `<ORIGEN>` | `S` (Senado), `CD` (Cámara de Diputados — revisión), `PE` (Poder Ejecutivo). |
| `<TIPO>` | `PL` (Ley), `PR` (Resolución), `PD` (Declaración), `PC` (Comunicación). |

Mapeo enum ↔ URL en `scraper.py` (`_ORIGEN_A_URL`, `_TIPO_A_URL`).

## Convenciones

Idénticas a HCDN:
- **User-Agent**: `PraxisAsesor/0.1 (+contacto@dominio.com)`.
- **Rate limit**: 1 req/seg por instancia.
- **Retries**: hasta 3 con backoff exponencial.
- **Timeouts**: 20s por request.

## Derivación de trámite

HSN no expone event-log nativo: solo timestamps por etapa. El parser invoca `derive_tramite_from_stages` para generar eventos sintéticos con `fuente="derived:hsn-stages"`. Reglas en `docs/specs/02-ingesta-hsn.md` §"Derivación de TramiteEvento desde stages".

Eventos generados (cuando hay dato):
- INGRESO A MESA DE ENTRADAS
- DADO CUENTA EN SESION (con DAE en detalle si está)
- INGRESO A DIRECCION GENERAL DE COMISIONES
- GIRO A COMISION (uno por giro, con nombre comisión en detalle)
- EGRESO DE COMISION (si la comisión despachó)
- INGRESO DEL DICTAMEN A LA MESA

Orden cronológico ascendente; empates por fecha respetan el orden semántico de la lista.

## Errores

- `ExpedienteNoEncontrado`: 404 del portal, o HTML no reconocible.
- `FuenteNoDisponible`: 4xx no-404, 5xx tras retries, errores de red persistentes.
- `ValueError`: si la cámara no es HSN, si falta `tipo`, si origen/tipo no tienen código URL HSN válido (ej. `MENSAJE_PE` o `OrigenExpediente.DIPUTADO`).

## Lo que NO hace todavía

- **Listing / enumeración** de expedientes nuevos. Solo lookup directo. La feature de enumeración (vía Asuntos Entrados PDFs) es aparte.
- **Tab `#etapaDiputado`**: ignorada por ahora. Cuando exista cross-referencing entre cámaras, se incorpora.
- **Texto definitivo** vs original: solo se captura el original. El definitivo (post-sanción) es feature aparte.
- **Mapeo a `Legislador` / `Comision`**: strings libres por ahora.
- **Autores en expedientes CD-origen**: vacío por diseño del portal (los autores viven en HCDN).

## Mejoras futuras / conocidas

- **Endurecer parser de cabecera**: hoy lee la primera celda del primer row con un solo extracto. Si HSN agrega información a la cabecera (ej. estado actual), conviene mapear más columnas.
- **Tab `#etapaDiputado`** para expedientes que cruzan cámaras: incorporar cuando exista la feature de cross-cámara.
- **Tab `#textoDefinitivo`**: incorporar cuando llegue post-sanción.
- **Reintentos diferenciados por origen del 5xx**: HSN puede dar timeouts en horario pico; podríamos usar backoff más generoso en esa franja. No urgente.

## Cómo testear

Tests de contrato en `tests/integration/scrapers/test_hsn_parser.py` (HTML fixturizado, sin red).
Tests unitarios del derivador en `tests/unit/scrapers/test_hsn_tramite_deriver.py`.
Tests del scraper con `MockTransport` en `tests/integration/scrapers/test_hsn_scraper.py`.

## Referencias

- Documentación de la fuente: [`../../../docs/data-sources.md`](../../../../docs/data-sources.md) §HSN.
- Spec de la feature: [`../../../docs/specs/02-ingesta-hsn.md`](../../../../docs/specs/02-ingesta-hsn.md).
- ADR del modelo: [`../../../docs/adr/0002-modelo-expediente.md`](../../../../docs/adr/0002-modelo-expediente.md).
