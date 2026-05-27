# `praxis.infrastructure` — Capa Infrastructure

Implementaciones concretas de los puertos definidos en `praxis.application`.

## Qué vive acá

- **Repositorios SQLAlchemy**: `SqlAlchemyExpedienteRepository`, etc.
- **Scrapers**: `HcdnScraper`, `HsnScraper`, etc. — implementan `FuenteExpedientes`.
- **Notificadores**: `SmtpNotificationSender`, `SesNotificationSender`.
- **Cola**: configuración y workers de Celery.
- **Auth provider**: adaptador Clerk.
- **Storage**: adaptador S3/R2.
- **EventBus**: implementación basada en tabla `domain_events` + worker.
- **DB engine y sessionmaker**: setup de SQLAlchemy 2.0 async.

## Qué NO vive acá

- Lógica de negocio.
- Endpoints HTTP (van en `praxis.api`).

## Restricciones de dependencias

`praxis.infrastructure` **puede** importar de `praxis.domain` y `praxis.application`.
**No puede** importar de `praxis.api`.

Cada subcarpeta (`db/`, `scrapers/`, `notifications/`, `queue/`, ...) que integra una fuente externa **debe** tener su propio `README.md` explicando: contrato, endpoints o tablas usadas, rate limits, errores conocidos, configuración requerida.

## Política de tipado

Modo permisivo de mypy (no strict). Los adaptadores hablan con servicios externos cuyos tipos no siempre están disponibles.

## Política de testing

Tests de integración con servicios reales (DB local, sandbox de email). Los **tests de contrato** para scrapers son obligatorios: snapshot de HTML/JSON real → output esperado.
