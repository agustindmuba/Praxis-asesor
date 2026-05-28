# Fuentes de datos — Praxis Asesor

Documentación de cada fuente externa que el sistema consume: contrato, estructura, rate limits, errores conocidos. Los hallazgos del spike inicial del ciclo 1 viven acá; cuando se materialicen los adaptadores en `backend/praxis/infrastructure/scrapers/`, cada uno tendrá su propio README local con detalles operativos.

## Reglas generales de ingesta

- Respetar `robots.txt` de cada sitio.
- Rate limit conservador: máx **1 req/segundo por dominio**, con backoff exponencial en errores.
- User-Agent identificable: `PraxisAsesor/0.x (+contacto@dominio.com)`.
- Cachear agresivamente; nada de re-scrapear lo que no cambió.
- Validado en spike: ambos portales aceptan ese UA sin fricción (HCDN `robots.txt` bloquea explícitamente `Scrapy` y `HeadlessChrome`; ningún User-Agent custom como el nuestro está en la blocklist).

---

## HCDN — Honorable Cámara de Diputados de la Nación

- **Portal**: [`www.diputados.gob.ar`](https://www.diputados.gob.ar/)
- **Status**: server-side rendered HTML, UTF-8, sin API pública. Sí scrapeable.
- **`robots.txt`** ([fuente](https://www.diputados.gob.ar/robots.txt)):
  - `User-agent: *` con `allow: /` (acceso general permitido).
  - Bloquea por nombre: `Bytespider`, `MJ12bot`, `AhrefsBot`, `Scrapy`, `HeadlessChrome`, `SeznamBot`.
  - Disallows: `/.content*/`, `/sandbox/`, `/pec/`, `/PEC/`, `/*frames.jsp*`.
  - Acción: usar UA `PraxisAsesor/...` (no Scrapy, no HeadlessChrome) y mantenernos lejos de los disallows.
- **Términos**: "La información contenida en este sitio es de dominio público y puede ser utilizada libremente. Se solicita citar la fuente". No hay política formal de scraping.

### Detalle de expediente

**No hay URL canónica `GET` directa.** Las URLs históricas tipo `/proyectos/proyecto.jsp?exp=NNNN-D-YYYY` están deprecadas (devuelven 404). Las versiones `/diputados/<slug>/proyecto.html?exp=...` funcionan pero requieren conocer el slug del diputado, que no es derivable trivialmente.

**Vía que funciona**: POST al buscador.

```
POST https://www.diputados.gob.ar/proyectos/resultado.html

Form data:
  zezion=true
  strNumExp=<NNNN>        # número de expediente, p.ej. "1497"
  strNumExpOrig=<X>       # origen: D | S | PE | OV | P | CD
  strNumExpAnio=<YYYY>    # año
  strMostrarFirmantes=on
  strMostrarComisiones=on
  strMostrarTramites=on
  strMostrarDictamenes=on
  strCantPagina=20
  (resto vacío)
```

La response es HTML con la ficha completa del expediente directamente embebida (no es una lista de resultados con un link al detalle: es el detalle).

### Campos extraídos

| Campo | Selector / fuente |
|---|---|
| **Extracto** (sumario corto) | `div.dp-texto` |
| **Sumario** (completo, modal) | `div[id^="sumario"]` — hidden div alimenta un modal JS, pero el contenido vive en el HTML |
| **Firmantes** | tabla con headers `FIRMANTE / DISTRITO / BLOQUE` |
| **Giros a Comisiones** | tabla con header `COMISIÓN` |
| **Trámite** | tabla con headers `CÁMARA / MOVIMIENTO / FECHA / RESULTADO` |
| **PDF del texto** | `<a href>` apuntando a `https://www4.hcdn.gob.ar/dependencias/dsecretaria/Periodo<YYYY>/PDF<YYYY>/TP<YYYY>/<NNNN-X-YYYY>.pdf` |

### Gotchas

- **PDFs en subdominio diferente**: `www4.hcdn.gob.ar`, no `www.diputados.gob.ar`. Hay que respetar rate limit por dominio en ambos.
- **Trámite puede estar vacío** para expedientes recién ingresados. No es un error de parseo.
- **`zezion=true`** es un valor literal del form hidden, no parece variable de sesión real (revisar en el futuro si se vuelve un problema).
- **Encoding**: el server declara `charset=UTF-8` correctamente; `httpx` lo detecta sin override.

### Pendiente (no cubierto por el spike)

- **Listado / paginación**: cómo descubrir expedientes nuevos sin conocer su número. Candidatos:
  - Boletines diarios "Trámite Parlamentario" (PDFs, ver `https://www.hcdn.gob.ar/secparl/dsecretaria/s_t_parlamentario/tramites-parlamentarios.html`).
  - Boletines de Asuntos Entrados (similar).
  - Búsqueda por rango de fechas vía el mismo endpoint POST (`strFechaInicio`, `strFechaFin`).
- **Dictámenes**: el spike no probó expedientes con dictamen. El form acepta `strMostrarDictamenes=on` y la ficha debería incluirlos; falta validar estructura.
- **Adhesiones**: en el caso de 1497-D-2024 aparecieron "SOLICITUD DE SER ADHERENTE" en el trámite. Decidir si las modelamos como firmantes secundarios o como tipo especial de evento.
- **Trámite Parlamentario** completo: parsear el PDF/HTML de Trámite Parlamentario daily para enumeración masiva.

### Snippet de prueba

```bash
uv run spike/hcdn/explore.py
# Salida: HTML cacheado en spike/_cache/hcdn_*.html
#         JSON parseado en spike/_cache/hcdn_resultados.json
```

Spike validado contra: `1497-D-2024`, `0001-D-2024`, `0001-PE-2024`.

---

## HSN — Honorable Senado de la Nación

- **Portal**: [`www.senado.gob.ar`](https://www.senado.gob.ar/)
- **Status**: server-side rendered HTML, UTF-8, sin API pública pero **con endpoints abiertos JSON/Excel** (ver más abajo). Sí scrapeable.
- **`robots.txt`** ([fuente](https://www.senado.gob.ar/robots.txt)):
  - Solo bloquea archivers de Internet Archive (`ia_archiver`, `archive.org_bot`).
  - Resto: permitido.
- **Términos**: no hay política explícita visible.

### Detalle de expediente

URL canónica **directa** (a diferencia de HCDN):

```
GET https://www.senado.gob.ar/parlamentario/comisiones/verExp/<NUM>.<YY>/<ORIGEN>/<TIPO>
```

Componentes:
- `NUM`: número de expediente (1 a 4 dígitos, **sin ceros a la izquierda**).
- `YY`: año a 2 dígitos (`24` = 2024).
- `ORIGEN`: `S` (Senado) | `CD` (Cámara de Diputados — revisión) | `PE` (Poder Ejecutivo).
- `TIPO`: `PL` (Ley) | `PR` (Resolución) | `PD` (Declaración) | `PC` (Comunicación).

Ejemplos:
- `https://www.senado.gob.ar/parlamentario/comisiones/verExp/239.24/S/PL`
- `https://www.senado.gob.ar/parlamentario/comisiones/verExp/1.24/CD/PL`

### Estructura del HTML

La ficha está organizada en 5 tablas identificables sin ambigüedad por su atributo `summary=`, más un `<div id="textoOriginal">` con el link al PDF. **No usar text search por labels**: el menú lateral repite los mismos términos y rompe el parser.

| Tabla / contenedor | `summary=` o id | Contiene |
|---|---|---|
| Cabecera | `summary="Número de Expediente <NUM>/<YY>"` | Nº, Origen, Tipo, Extracto |
| Autores | `summary="Listado de Autores"` | Senadores firmantes |
| Mesa de Entradas | `summary="Fechas en Mesa de Entradas"` | Fecha ingreso, Dado Cuenta, Nº DAE |
| Dir. Comisiones | `summary="Fechas en Dirección Comisiones"` | Fecha ingreso a comisiones, fecha de dictamen |
| Giros | `summary="Giros del Expediente a Comisiones"` | Comisión, fecha ingreso, fecha egreso |
| PDF | `<div id="textoOriginal">` | Link a `/parlamentario/parlamentaria/<docId>/downloadPdf` |

### Campos extraídos

| Campo | Selector |
|---|---|
| Número (`NUM/YY`) | de la URL o de la primera celda de la cabecera |
| Origen full text | celda 2 de la cabecera (ej. "Senado De La Nación", "Cámara De Diputados") |
| Tipo full text | celda 3 de la cabecera (ej. "Proyecto De Ley") |
| Extracto | celda 4 de la cabecera |
| Autores | tabla `summary="Listado de Autores"`, una entrada por celda |
| Fecha Mesa de Entradas | tabla `summary="Fechas en Mesa de Entradas"`, col 1 |
| Fecha Dado Cuenta | misma tabla, col 2 |
| Nº DAE | misma tabla, col 3 (primer token; la celda mezcla "12/2024 Tipo: NORMAL") |
| Fecha Dir. Comisiones | tabla `summary="Fechas en Dirección Comisiones"`, col 1 |
| Fecha Dictamen Mesa | misma tabla, col 2 ("SIN FECHA" si no hay) |
| Giros | tabla `summary="Giros del Expediente a Comisiones"`, una fila por giro |
| PDF | `div#textoOriginal a[href*="downloadPdf"]` |

### Gotchas

- **Expedientes `CD`-origen no tienen autores en HSN**: vienen "en revisión" desde HCDN; los firmantes originales viven en el sistema de Diputados. Si una integración cruza ambas cámaras, hay que resolver autores yendo a HCDN cuando origen=CD.
- **Columna comisión mezclada**: el texto del giro viene como `"DE SALUD ORDEN DE GIRO: 1"` — separar comisión del orden con regex `(.+?)\s+ORDEN DE GIRO:\s*\d+`.
- **DAE mezclado**: la celda DAE incluye `Tipo: NORMAL` u otra etiqueta; tomar solo el primer token (`12/2024`).
- **Tabs**: el HTML tiene 5 tabs (`#Autores`, `#etapaDiputado`, `#tramiteLegislativo`, `#textoDefinitivo`, `#textoOriginal`). Todas server-side rendered y visibles en el HTML; el JS solo controla cuál está activa.
- **Sin event-log de trámite tipo HCDN**: HSN modela el trámite como timestamps por etapa (Mesa → DAE → Dir. Comisiones → Giros). Para normalizar al modelo común `tramite` (event-log), hay que **derivar eventos** de los timestamps.
- **Encoding**: UTF-8 declarado y respetado por httpx. Consola Windows (cp1252) puede romper al imprimir; usar `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

### Datasets abiertos JSON/Excel (`/micrositios/DatosAbiertos/`)

Endpoints estructurados disponibles. Útiles para **catálogos** (legisladores, comisiones), no tanto para expedientes (no hay dataset "expedientes" como tal; hay "asuntos entrados" pero son URLs a PDFs de sesión).

| Dataset | JSON | Excel |
|---|---|---|
| Senadores vigentes | `/ExportarListadoSenadores/json` | `/ExportarListadoSenadores/Excel` |
| Senadores histórico | `/ExportarListadoSenadoresHistorico/json` | `/ExportarListadoSenadoresHistorico/Excel` |
| Comisiones | `/ExportarListadoComisiones/json/todas` | `/ExportarListadoComisiones/Excel` |
| Asuntos Entrados | `/ExportarListadoAsuntosEntrados/json` | `/ExportarListadoAsuntosEntrados/Excel` |
| Versiones Taquigráficas | `/ExportarListadoVersionesTac/json` | `/ExportarListadoVersionesTac/Excel` |
| Normativa Vigente | `/ExportarNormativaVigente/json` | `/ExportarNormativaVigente/Excel` |
| Decretos Presidenciales | `/ExportarDecretosPresidenciales/json` | `/ExportarDecretosPresidenciales/Excel` |
| Resoluciones Conjuntas | `/ExportarResolucionesConjuntas/json` | `/ExportarResolucionesConjuntas/Excel` |

Todos con prefijo `https://www.senado.gob.ar/micrositios/DatosAbiertos/Exportar...`.

**Asuntos Entrados**: estructura `{"table": {"rows": [{"URL": "...", "FECHA REUNION": "YYYY-MM-DD"}, ...]}}`. Una entrada por sesión, ~580+ registros 1999–2026. Cada `URL` apunta al PDF de "Asuntos Entrados" de esa sesión.

### Pendiente (no cubierto por el spike)

- **Listado / búsqueda**: el formulario en `/parlamentario/parlamentaria/` permite búsqueda; no probamos enviarlo todavía.
- **Tab `#etapaDiputado`** para expedientes con doble paso por las cámaras.
- **Texto definitivo** vs texto original: hay dos tabs separados; cómo decidir cuál es "el vigente".
- **Comisiones específicas**: `/parlamentario/comisiones/proyectos/<id>` lista los proyectos asignados a una comisión — útil para enumeración por comisión.
- **PDFs de Asuntos Entrados** como fuente de enumeración: parsear estos PDFs daría el catálogo completo de expedientes nuevos por sesión.

### Snippet de prueba

```bash
uv run spike/hsn/explore.py
# Salida: HTML cacheado en spike/_cache/hsn_*.html
#         JSON parseado en spike/_cache/hsn_resultados.json
```

Spike validado contra: `239/24/S/PL`, `1/24/CD/PL`, `1497/20/S/PC`.

---

## InfoLeg, SAIJ

Sin relevamiento aún. Se agregan cuando aparezca la primera feature que los necesite (probablemente enriquecimiento de fichas, post-MVP base).

---

## Tabla comparativa HCDN vs HSN

| Aspecto | HCDN | HSN |
|---|---|---|
| URL canónica directa | ❌ (POST search) | ✅ (`/verExp/NUM.YY/ORIGEN/TIPO`) |
| Rendering | Server-side | Server-side |
| Encoding | UTF-8 | UTF-8 |
| Bloqueo de robots.txt | Scrapy, HeadlessChrome (no nos afecta) | Solo archivers |
| Firmantes en la ficha | Sí (con distrito + bloque) | Sí, salvo CD-origen |
| Trámite | Event log (Cámara/Movimiento/Fecha/Resultado) | Stages con timestamps |
| PDF del texto | `www4.hcdn.gob.ar` (otro subdominio) | Mismo dominio (`/parlamentario/parlamentaria/<docId>/downloadPdf`) |
| Datasets abiertos | ❌ | ✅ (catálogos, no expedientes directos) |

**Decisión de modelado** para `praxis.domain.Expediente`: el modelo común debe tener un campo `tramite: list[TramiteEvento]` que se rellena directo desde HCDN; para HSN, el adaptador deriva eventos sintéticos a partir de los timestamps de cada etapa (Mesa, DAE, Dir. Comisiones, Giro N) preservando el orden cronológico. ADR pendiente cuando arranquemos la implementación.
