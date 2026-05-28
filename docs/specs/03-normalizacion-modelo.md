# 03 — Normalización del modelo común (cámara-agnóstico)

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 3
- **Depende de**: features 1 (HCDN) y 2 (HSN), ADR 0002 + Amendment 1, puerto `FuenteExpedientes`.

## Problema

Las features 1 y 2 entregan dos adaptadores (`HcdnScraper`, `HsnScraper`) que implementan el mismo puerto y producen el mismo tipo de dominio (`Expediente`). Pero el llamador todavía tiene que **saber a cuál adaptador pegarle** según la cámara del expediente. Eso filtra el detalle de infraestructura al código de aplicación.

Esta feature cierra el ciclo del bloque 1 entregando un **caso de uso unificador**: el llamador pide un expediente por su `NumeroExpediente` y el sistema rutea internamente al adaptador correcto.

## Solución propuesta

Caso de uso `BuscarExpediente` en `praxis.application.use_cases.buscar_expediente`. Recibe los dos `FuenteExpedientes` por inyección (uno HCDN, uno HSN). Su método `execute(numero, tipo)` despacha al puerto correcto según `numero.camara`.

```python
class BuscarExpediente:
    def __init__(self, hcdn: FuenteExpedientes, hsn: FuenteExpedientes) -> None: ...

    async def execute(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente: ...
```

## Caso de uso técnico

```
DADO un NumeroExpediente de cualquier cámara (HCDN o HSN)
     y un BuscarExpediente cableado con HcdnScraper + HsnScraper
CUANDO se invoca execute(numero, tipo)
ENTONCES devuelve el Expediente desde la fuente correcta
         o propaga ExpedienteNoEncontrado / FuenteNoDisponible.
```

## Criterios de aceptación

- [ ] Existe `praxis.application.use_cases.BuscarExpediente`.
- [ ] Recibe los dos puertos `FuenteExpedientes` por DI (uno HCDN, uno HSN).
- [ ] Despacha al puerto correcto según `numero.camara`.
- [ ] Propaga errores del adaptador sin reemplazarlos.
- [ ] Si la cámara es desconocida (futuro improbable), lanza `ValueError`.
- [ ] Tests unitarios con fakes que implementan `FuenteExpedientes` (no `MagicMock` — fakes explícitos por testabilidad).
- [ ] Lint + type-check + tests verdes.

## Fuera de alcance

- **Persistencia**: el use case devuelve el Expediente al llamador, no lo guarda. Persistencia entra con la feature de DB.
- **Cache**: cada `execute` hace fetch fresco. Cache en feature aparte.
- **Búsqueda por criterios distintos a `numero`** (por autor, por tema, por fecha): feature 9 del PRODUCT.md.
- **Validación de combinación cámara/tipo**: el adaptador HSN ya valida (lanza ValueError si tipo es MENSAJE_PE). El use case propaga.

## Notas técnicas

- Inyección de los dos puertos por constructor — el composition root (que aparecerá cuando armemos `praxis.api.main` para producción) los instancia y arma el `BuscarExpediente`.
- Type hint del constructor: parámetros con keyword `*` para forzar pasar por nombre (`hcdn=...`, `hsn=...`). Esto evita confusión sobre cuál puerto va dónde.
- Tests: usar **fakes** (clases que implementan el puerto a mano) en lugar de `MagicMock`. Hace los tests legibles y respeta el contrato del puerto.
