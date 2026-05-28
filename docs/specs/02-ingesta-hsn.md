# 02 — Ingesta de expedientes HSN

- **Estado**: en desarrollo
- **Bloque del MVP**: 1 (Fundamentos de datos)
- **Feature en PRODUCT.md**: §"Features en orden de implementación" item 2
- **Depende de**: ADR 0001 (stack), ADR 0002 (modelo Expediente) + Amendment 1, feature 1 (puerto `FuenteExpedientes` ya existente), spike `feat/scraping-spike` (validado).

## Problema

Análogo a feature 1, pero para el portal del Senado (`www.senado.gob.ar`). El despacho necesita poder pedir un expediente de HSN dado su número (`NNN/YY`) + origen + tipo, y obtener un `Expediente` con todos los campos del dominio.

A diferencia de HCDN, HSN **no expone un event-log de trámite**: solo timestamps por etapa. El adaptador debe **derivar `TramiteEvento` sintéticos** desde esos timestamps, marcando `fuente="derived:hsn-stages"` para trazabilidad (ver ADR 0002 §"TramiteEvento" + Amendment 1).

## Solución propuesta

Adaptador HSN que implementa el mismo puerto `praxis.application.ports.FuenteExpedientes`. Bajo el capó:

1. Construye URL canónica: `GET /parlamentario/comisiones/verExp/<NUM>.<YY>/<ORIGEN>/<TIPO>`.
2. Parsea la HTML resultante usando los `summary=` de las 5 tablas (no text-search por labels — ver gotcha en `data-sources.md` §HSN).
3. Deriva eventos de trámite desde fechas de Mesa/DAE/Comisiones/Giros, en orden cronológico ascendente.
4. Mapea códigos de URL a enums del dominio (`S`→SENADOR, `CD`→REVISION_DIPUTADOS, `PE`→EJECUTIVO; `PL`→PROYECTO_LEY, `PR`→PROYECTO_RESOLUCION, `PD`→PROYECTO_DECLARACION, `PC`→PROYECTO_COMUNICACION).

## Caso de uso técnico

```
DADO un NumeroExpediente HSN (numero=239, anio=2024, origen=SENADOR, camara=HSN)
     y tipo conocido (PROYECTO_LEY, p.ej.)
CUANDO el sistema pide ese expediente vía FuenteExpedientes (instancia HsnScraper)
ENTONCES devuelve un Expediente con todos los campos del dominio,
         incluyendo trámite como event-log derivado de los stages,
         o lanza ExpedienteNoEncontrado si el portal devuelve 404.
```

**Limitación de signature actual**: `FuenteExpedientes.buscar_por_numero(numero)` toma solo el `NumeroExpediente`, pero HSN necesita también el `TipoExpediente` para construir la URL (la `/TIPO` final). Tres opciones evaluadas:

A. Agregar parámetro opcional `tipo: TipoExpediente | None = None` al puerto. Si la cámara es HSN, el llamador debe pasarlo. (No rompe HCDN.)

B. El scraper HSN intenta los 4 tipos en orden hasta encontrar 200. Más HTTP calls; inelegante.

C. Cambiar la signature del puerto a recibir un struct `BusquedaExpediente` con todos los campos necesarios. Más expresivo, más invasivo.

**Decisión**: opción A para esta feature (mínimo cambio al puerto). Si en el futuro aparece otro adaptador con necesidad similar, considerar C en un ADR aparte.

## Criterios de aceptación

- [ ] Existe `praxis.infrastructure.scrapers.hsn.HsnScraper` implementando el puerto.
- [ ] El parser extrae correctamente, para los 3 expedientes validados en el spike:
  - Cabecera completa (origen, tipo full text, extracto).
  - Autores (lista — vacía cuando el origen es CD, comportamiento documentado).
  - Fechas: Mesa de Entradas, Dado Cuenta, Dir. Comisiones, dictamen.
  - Número DAE (sin contaminación con "Tipo: NORMAL" u otros).
  - Giros con fechas in/out y comisión limpia (sin "ORDEN DE GIRO: N").
  - URL del PDF original.
- [ ] El derivador de trámite produce eventos en orden cronológico ascendente, con `fuente="derived:hsn-stages"`, sin duplicar info.
- [ ] El puerto `FuenteExpedientes` admite un parámetro opcional `tipo`; HSN lo exige y HCDN lo ignora.
- [ ] Tests de contrato (con HTML fixturizado) + tests unit del derivador + tests de scraper con `MockTransport`. Cero red en CI.
- [ ] Lint + type-check + tests verdes.
- [ ] README del adaptador en `praxis/infrastructure/scrapers/hsn/`.

## Fuera de alcance

- **Listing / enumeración** de expedientes nuevos. Solo "traeme este número exacto, de tal tipo y origen". Enumeración via Asuntos Entrados (PDFs) en feature aparte.
- **Tab `etapaDiputado`**: cuando el expediente pasa por ambas cámaras, HSN expone una sub-tab con info del trámite en HCDN. Por ahora ignoramos; cuando llegue feature de cross-referencing entre cámaras se incorpora.
- **Tab `textoDefinitivo`** vs `textoOriginal`: por ahora solo tomamos el original (URL del PDF). El texto definitivo es relevante post-sanción; feature posterior.
- **PDF parsing** del texto del expediente. Solo guardamos URL.
- **Mapeo a `Legislador` / `Comision`**: strings libres por ahora.

## Notas técnicas

Toda la info de la fuente vive en [`../data-sources.md`](../data-sources.md) §HSN. Resumen:

- **URL**: `GET /parlamentario/comisiones/verExp/<NUM>.<YY>/<ORIGEN>/<TIPO>`.
- **Parsing**: 5 tablas identificadas por `summary=`:
  - `summary="Número de Expediente NNN/YY"` → cabecera (Nº/Origen/Tipo/Extracto).
  - `summary="Listado de Autores"` → autores.
  - `summary="Fechas en Mesa de Entradas"` → Mesa + Dado Cuenta + DAE.
  - `summary="Fechas en Dirección Comisiones"` → Dir. Gral. Comisiones + dictamen.
  - `summary="Giros del Expediente a Comisiones"` → comisión + fecha in/out.
- **PDF**: dentro de `<div id="textoOriginal">`, link a `/parlamentario/parlamentaria/<docId>/downloadPdf`.
- **Encoding**: UTF-8 declarado por el server.
- **Rate limit**: 1 req/seg.
- **UA**: `PraxisAsesor/0.x (+contacto@dominio.com)`.

### Derivación de TramiteEvento desde stages

El derivador genera eventos sintéticos a partir de los timestamps disponibles. Mapeo:

| Fecha del expediente | Evento generado | Cámara | Detalle |
|---|---|---|---|
| `fecha_mesa_entradas` | "INGRESO A MESA DE ENTRADAS" | HSN | — |
| `fecha_dado_cuenta` | "DADO CUENTA EN SESION" | HSN | DAE si está disponible |
| `fecha_dir_comisiones` | "INGRESO A DIRECCION GENERAL DE COMISIONES" | HSN | — |
| `giro.fecha_ingreso` (uno por giro) | "GIRO A COMISION" | HSN | nombre de la comisión |
| `giro.fecha_egreso` (uno por giro, si existe) | "EGRESO DE COMISION" | HSN | nombre de la comisión |
| `fecha_dictamen_mesa` (si no es "SIN FECHA") | "INGRESO DEL DICTAMEN A LA MESA" | HSN | — |

Todos con `fuente="derived:hsn-stages"`. Orden cronológico ascendente.

## Plan de tests

- **Unit (parser)**: parseo correcto de las 5 tablas con fixtures sintéticos chicos.
- **Unit (derivador)**: cada combinación de fechas presentes → eventos esperados, en orden correcto, con campos correctos.
- **Contract (parser end-to-end)**: contra los 3 fixtures HTML reales del spike (`239/24/S/PL`, `1/24/CD/PL`, `1497/20/S/PC`).
- **Scraper**: con `MockTransport` — UA correcto, URL canónica construida bien, errores (404, 5xx, timeouts).

## Riesgos

- **Tipo desconocido a priori**: para buscar por número en HSN, el llamador debe saber qué tipo es (`PL`/`PR`/`PD`/`PC`). Para un sistema interno con el dato en DB, no es problema; para una búsqueda libre, sí. Mitigación: cuando enumeremos por Asuntos Entrados, el tipo viene en los metadatos del PDF.
- **CD-origen sin autores**: documentado y aceptado. El campo `firmantes` queda vacío. Mitigación: cuando llegue cross-referencing, completar desde HCDN.
- **Trámite derivado vs. real**: los eventos sintéticos pueden no capturar movimientos intermedios que el portal no expone. Mitigación: marcar `fuente="derived:hsn-stages"` para que el frontend (a futuro) pueda distinguir y mostrar disclaimers.
