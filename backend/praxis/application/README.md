# `praxis.application` — Capa Application

Orquestación del dominio: casos de uso + puertos (interfaces).

## Qué vive acá

- **Casos de uso** (uno por archivo): `SeguirExpediente`, `AsignarExpedienteAAsesor`, `ConfigurarAlerta`, `BuscarExpedientes`, etc. Cada uno modela una acción del usuario o del sistema.
- **Puertos** (interfaces / abstract base classes): `ExpedienteRepository`, `NotificationSender`, `EventBus`, `FuenteExpedientes`, etc. Definen el contrato que la capa Infrastructure debe cumplir.
- **DTOs** y **comandos** específicos de los casos de uso (cuando no son entidades del dominio).

## Qué NO vive acá

- Implementaciones concretas de los puertos: van en `praxis.infrastructure`.
- Lógica de negocio pura: va en `praxis.domain`.
- Endpoints HTTP: van en `praxis.api`.

## Restricciones de dependencias

`praxis.application` **puede** importar de `praxis.domain`.
**No puede** importar de `praxis.infrastructure` ni de `praxis.api`. Las implementaciones se inyectan desde afuera (DI).

## Política de tipado

`mypy --strict` activado para todo este módulo. Los puertos son contratos: si el tipado se afloja, los adaptadores empiezan a divergir y se pierde el aislamiento.

## Política de testing

Testeable sin DB ni red, usando puertos mockeados o fakes in-memory. Cobertura objetivo: 80%+.
