# Fuentes de datos — Praxis Asesor

Documentación de cada fuente externa que el sistema consume: contrato, estructura, rate limits, errores conocidos.

## Reglas generales de ingesta

- Respetar `robots.txt` de cada sitio.
- Rate limit conservador: máx **1 req/segundo por dominio**, con backoff exponencial en errores.
- User-Agent identificable: `PraxisAsesor/0.x (+contacto@dominio.com)`.
- Cachear agresivamente; nada de re-scrapear lo que no cambió.
- Cada adaptador en `backend/praxis/infrastructure/` tiene su propio README explicando contrato.

## Fuentes previstas

### HCDN — Honorable Cámara de Diputados de la Nación

- Portal: [`www.diputados.gob.ar`](https://www.diputados.gob.ar/).
- Sistema de Información Parlamentaria (SIP).
- Estado: sin API pública oficial. Requiere scraping.
- **Pendiente**: relevar endpoints concretos en el ciclo 1.

### HSN — Honorable Senado de la Nación

- Portal: [`www.senado.gob.ar`](https://www.senado.gob.ar/).
- Sistema "Parlamentario".
- Estado: sin API pública oficial. Requiere scraping.
- **Pendiente**: relevar endpoints concretos en el ciclo 1.

### InfoLeg

- Portal: [`www.infoleg.gob.ar`](https://www.infoleg.gob.ar/).
- Ministerio de Justicia. Normativa nacional consolidada.
- Estado: solo lectura para enriquecer fichas (etapa posterior al MVP base).

### SAIJ

- Portal: [`www.saij.gob.ar`](https://www.saij.gob.ar/).
- Base jurídica.
- Estado: relevamiento aún no hecho.

## Estado del documento

Stub inicial. Se completa por adaptador a medida que se implementen.
