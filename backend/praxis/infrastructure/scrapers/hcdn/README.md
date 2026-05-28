# `praxis.infrastructure.scrapers.hcdn`

Adaptador concreto: scraper del portal de la Cámara de Diputados (HCDN). Implementa el puerto `praxis.application.ports.FuenteExpedientes`.

## Archivos

| Archivo | Rol |
|---|---|
| `scraper.py` | `HcdnScraper`: async I/O con httpx, rate limit, retries. |
| `parser.py` | Parseo puro de HTML → entidades de dominio. Sin I/O, fácil de testear. |

## Endpoint usado

`POST https://www.diputados.gob.ar/proyectos/resultado.html`

Form data con el número descompuesto (`strNumExp`, `strNumExpOrig`, `strNumExpAnio`) más `strMostrar*=on` para incluir firmantes, comisiones, trámite y dictámenes.

## Convenciones

- **User-Agent**: `PraxisAsesor/0.1 (+contacto@dominio.com)`. El portal bloquea `Scrapy`, `HeadlessChrome` y otros bots genéricos; nuestro UA está OK.
- **Rate limit**: 1 req/seg por instancia del scraper (`asyncio.Lock` + timestamp).
- **Retries**: hasta 3 con backoff exponencial (`2^attempt` segundos). 4xx no se reintentan. 5xx y timeouts sí.
- **Timeouts**: 20s por request.

## Errores

- `ExpedienteNoEncontrado`: el portal no encontró el número (detectado por contenido del HTML, ya que devuelve 200 siempre).
- `FuenteNoDisponible`: 4xx, 5xx tras retries, o errores de red persistentes.
- `ValueError`: si se le pasa un `NumeroExpediente.camara != HCDN`.

## Lo que NO hace todavía

- **Listing / enumeration**: no descubre expedientes nuevos por su cuenta. Solo "traeme este número exacto". Cubierto por features siguientes.
- **Mapeo a `Comision` / `Legislador`**: los nombres viven como string libre. Features 5 y 6.
- **Cache HTTP**: cada `buscar_por_numero` hace red. Un cache (Redis/in-memory) es feature aparte.
- **Detección de cambios**: no compara con snapshots anteriores. Sin BD, no aplica todavía.

## Cómo testear

Tests de contrato en `tests/integration/scrapers/test_hcdn_parser.py`: usan HTML fixturizado en `tests/fixtures/hcdn/` (capturado del spike), sin red.

Para correr contra el portal vivo (no en CI):
```bash
uv run pytest -m network
```

## Mejoras futuras / conocidas

- **Detección de "MENSAJE NRO:" en `<h4>` para precisar `TipoExpediente` en expedientes PE/JGM.** Hallazgo concreto del Amendment 1 ADR 0002: el fixture `hcdn_0001-PE-2024.html` contiene `<h4>MENSAJE NRO: 0015/24 Y PROYECTO DE LEY</h4>` pero el parser no lo lee — solo lee `div.dp-texto` y `div[id^="sumario"]`. La heurística actual cae al default conservador (`MENSAJE_PE`) en este caso. Un PE-origin que sea proyecto de ley directo (sin ser mensaje envoltorio) también caería en `MENSAJE_PE` por el default. Para precisar, extender el parser para leer también el `<h4>` y detectar el patrón `MENSAJE NRO: NNNN/YY Y PROYECTO DE LEY` (que es texto convencional de HCDN para anunciar mensaje + proyecto adjunto). No urgente: el default conservador no genera datos incorrectos para mensajes reales, solo es menos preciso para proyectos directos del PE. Cuando se implemente, sumar fixtures de muestra de "proyecto PE directo" para tener cobertura.

- **Trámite con cámara inferida desde texto libre.** El campo `camara` del `TramiteEvento` actualmente se infiere de la celda de la tabla con un `if "senado" in text → HSN, else → HCDN`. Si HCDN cambia el texto (ej. "Senado de la Nación" → "HSN") el parser sigue funcionando, pero si introduce una cámara nueva (improbable) no la detecta. Endurecer cuando aparezca el caso.

- **Adhesiones**: en el fixture `hcdn_1497-D-2024.html` aparecen "SOLICITUD DE SER ADHERENTE..." en la tabla de trámite. Actualmente se modelan como `TramiteEvento` igual que cualquier otro movimiento. Decidir en una feature futura si conviene tipificarlas como `Firmante` secundario (adherente) o mantener como evento de trámite. Implica cambio de modelo → ADR previo.

## Referencias

- Documentación de la fuente: [`../../../docs/data-sources.md`](../../../../docs/data-sources.md) §HCDN.
- Spec de la feature: [`../../../docs/specs/01-ingesta-hcdn.md`](../../../../docs/specs/01-ingesta-hcdn.md).
- ADR del modelo: [`../../../docs/adr/0002-modelo-expediente.md`](../../../../docs/adr/0002-modelo-expediente.md).
