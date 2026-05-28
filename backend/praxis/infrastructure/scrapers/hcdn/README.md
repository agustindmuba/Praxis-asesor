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

## Referencias

- Documentación de la fuente: [`../../../docs/data-sources.md`](../../../../docs/data-sources.md) §HCDN.
- Spec de la feature: [`../../../docs/specs/01-ingesta-hcdn.md`](../../../../docs/specs/01-ingesta-hcdn.md).
- ADR del modelo: [`../../../docs/adr/0002-modelo-expediente.md`](../../../../docs/adr/0002-modelo-expediente.md).
