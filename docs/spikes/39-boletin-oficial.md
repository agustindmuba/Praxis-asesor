# Spike 39.1.5 — Portal Boletín Oficial

**Branch:** `feat/39-resumen-bo`
**Fecha:** 2026-06-02
**Conclusión:** El plan original de scrapear HTML del portal **no es
viable** sin Playwright. Hay dos alternativas reales (PDFs S3 + SAIJ).
Esta enmienda al ADR 0006/0007 y a la spec 15 se acuerda en el commit
del spike.

## Objetivo

Validar **antes** de codear `BoletinOficialScraper` (feat-39.3) que el
portal:

1. Es accesible con UA respetuoso (1 req/s + identificación).
2. Permite filtrar por fecha y sección.
3. Tiene estructura HTML parseable (rubros, normas, sumarios, links).
4. No requiere autenticación.

## Resultado: 2 caminos viables, ninguno es el original

| Camino | Viable v1 | Costo |
|---|---|---|
| Scraping HTML del portal | ❌ NO (SPA React) | Requeriría Playwright |
| **PDF del día por sección (S3 público)** | ✅ SÍ | `pdfplumber` ya en stack |
| **SAIJ (`argentina.gob.ar/normativa`)** | 🟡 a explorar | Nuevo spike |
| Reverse-engineer API SOAP del SPA | ❌ NO (frágil) | Sesión + paginación oscura |

## Hallazgos

### robots.txt

```
User-agent: *
Disallow: /detalleAviso/segunda/*
Disallow: /seccion/segunda/*
Disallow: /seccion/segunda
```

**Impacto en spec 15**: la sección **Segunda (Avisos Oficiales) queda
fuera del MVP**. Robots la prohíbe explícitamente. La spec 15 indicaba
las 3 secciones (Legislación, Designaciones, Avisos Oficiales). Tras
este spike, **el MVP cubre solo Legislación (primera) y Designaciones
(cuarta)**.

(Curiosidad: el robots solo prohíbe la sección segunda. Las otras tres
están autorizadas. Esto sugiere que Avisos Oficiales tiene una
restricción legal o regulatoria propia que las normas y designaciones
no tienen.)

### El portal es SPA React

`https://www.boletinoficial.gob.ar/seccion/primera` y todas sus
variantes con fecha (`/2026-05-31`, `?fecha=…`) devuelven exactamente
**el mismo HTML** (~116 KB para "primera", verificado con MD5).

Razón: el HTML es un shell React que carga datos vía JavaScript.
Sin un navegador headless (Playwright), el HTML estático no tiene los
listados de normas.

```bash
# Las 3 fechas distintas devuelven el mismo MD5:
c45cc40a1ca6c84084c0ab2edadd0187 *legislacion__2026-05-25.html
c45cc40a1ca6c84084c0ab2edadd0187 *legislacion__2026-05-31.html
c45cc40a1ca6c84084c0ab2edadd0187 *legislacion__2026-06-01.html
```

Endpoint API real descubierto: `GET /seccion/actualizar/{n}` devuelve
JSON pero requiere sesión previa para incluir contenido. Sin cookie/JS
state previo:

```json
{"hay_mas_datos":false,"html":"","sig_pag":1,"ult_rubro":"","id_rubro":null}
```

Reverse-engineer este flujo es viable pero **frágil** (depende de un
estado de sesión interno que cambia silenciosamente).

### PDFs del día — el camino feliz

El portal sirve el BO completo del día como PDF público en S3:

| URL | Tamaño | Status |
|---|---|---|
| `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/primera.pdf` | 1.97 MB | ✅ 200 |
| `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/segunda.pdf` | 2.27 MB | ✅ 200 (pero robots) |
| `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/tercera.pdf` | 1.96 MB | ✅ 200 |
| `https://s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/cuarta.pdf` | 0.73 MB | ✅ 200 |

Características clave:

- **Sin auth** — S3 público.
- **`application/pdf`** — parseable con `pdfplumber` (ya en stack para
  `spike` HCDN PDF).
- **Refresca a las 00:01 ART** del día siguiente (a confirmar; el
  spike corrió a las 12:28 ART y bajó el PDF "del día").
- **El robots.txt del dominio `boletinoficial.gob.ar` NO aplica a
  `s3.arsat.com.ar`**. La sección segunda igual queda fuera v1 por
  respeto al espíritu de la restricción.

**Limitación crítica**: no encontramos un patrón de URL para PDFs
**históricos**. Probamos 7 layouts plausibles (`/2026/06/01/primera.pdf`,
`/historico/...`, `/seccion/primera/20260601.pdf`, etc) y todos
devolvieron 403. Por ahora el PDF S3 sirve **solo el día corriente**.

**Implicación para spec 15**: encaja perfectamente con el caso de uso
(briefing 7:30 AM con normas del día anterior). El job nocturno 05:00
ART baja `pdf-del-dia/primera.pdf` y `cuarta.pdf`, los parsea, persiste
normas. Re-procesar fechas anteriores sería un v2.

### SAIJ — la otra alternativa

`https://www.argentina.gob.ar/normativa` responde 200 con HTML de
240 KB. Es el sitio del Sistema Argentino de Información Jurídica.

**No exploré profundo**. Es la base oficial del Estado para normativa
nacional. Tiene búsqueda full-text, navegación por organismo y por
tipo de norma. Si en v2 necesitamos histórico estructurado, hay que
hacerle un spike propio.

Las rutas hijas que probé devolvieron 502/404, pero el endpoint base
sí responde — es cuestión de descubrir cuál es el path canónico.

## Recomendación para feat-39.3

**Cambiar el enfoque del scraper**:

- ~~`BoletinOficialScraper` (HTML scraping)~~ ← descartado.
- **`BoletinOficialPdfClient`** que baja `pdf-del-dia/primera.pdf` y
  `pdf-del-dia/cuarta.pdf` y los parsea con `pdfplumber`.

Trade-offs:

✅ **Pros**:
- Sin Playwright (mantenemos ADR 0007 limpio).
- Parser PDF estable y testeable con fixtures.
- Cubre exactamente el caso de uso del briefing diario.
- Sin sesión / cookies / state oscuro.

⚠️ **Contras**:
- Sin acceso a normas históricas pasadas hasta tener flujo PDF (o SAIJ).
- Sin `sumario` estructurado: el PDF tiene texto que hay que parsear
  para reconstruir el sumario que el sitio HTML servía limpito. Es
  trabajo extra de heurísticas (regex sobre la estructura del PDF).
- El PDF es ~2 MB, parsearlo toma 10-30 segundos vs unos pocos KB de
  HTML. Trivial para una corrida nocturna.

## Acciones pendientes (post-spike)

1. **Ajustar spec 15**:
   - Quitar sección "Avisos Oficiales" del alcance MVP.
   - Marcar Tercera (Convocatorias, Edictos Judiciales) como out-of-scope
     explícito (ya lo estaba).
   - Documentar el cambio de estrategia (HTML → PDF S3) en sección
     "Solución propuesta".

2. **Ajustar ADR 0007** (política scraping):
   - Agregar referencia al patrón de PDF público (S3 CDN sin sesión).
   - Documentar que `s3.arsat.com.ar` es un dominio distinto al portal
     y su `robots.txt` (si tiene) aplica por separado.

3. **Ajustar ADR 0006** (modelo de datos):
   - `NormaBO.seccion` queda con 2 valores reales v1: `legislacion`,
     `designaciones`. Mantener `avisos_oficiales` en el enum por si v2
     vía SAIJ lo habilita.
   - `NormaBO.url_oficial` apunta al PDF S3 (o al portal HTML del BO
     como referencia humana).
   - `NormaBOTexto.texto` ahora viene del PDF parseado, no del HTML.

4. **Refactor feat-39.3**: `BoletinOficialPdfClient` (no Scraper) +
   `parser_bo_pdf.py` con `pdfplumber`. Tests con PDFs fixturizados en
   `tests/fixtures/bo/`.

5. **(Opcional v2)** Spike SAIJ aparte para histórico.

## Artefactos del spike

```
backend/spikes/bo/
  _robots.txt                       # robots.txt al momento del spike
  _homepage.html                    # home del BO (referencia React shell)
  legislacion__2026-06-01.html      # SPA shell para primera (todas las
  legislacion__2026-05-31.html      # fechas devuelven el MISMO MD5 — el
  legislacion__2026-05-25.html      # contenido viene por JS)
  designaciones__2026-06-01.html    # idem para cuarta
  designaciones__2026-05-31.html
  designaciones__2026-05-25.html
  avisos_oficiales__*.html          # idem segunda; queda como referencia
                                     # aunque NO se use por robots.

backend/scripts/
  spike_bo.py                       # round 1 — exploró HTML
  spike_bo_round2.py                # round 2 — descubrió PDFs S3 + SAIJ
```

## Cómo reproducir

```bash
cd backend
PYTHONUTF8=1 .venv/Scripts/python -m scripts.spike_bo
PYTHONUTF8=1 .venv/Scripts/python -m scripts.spike_bo_round2
```

Cada round corre ~40 segundos respetando 1 req/s. UA identificable. Sin
LLM, costo cero.

## Conclusiones tras feat-39.3 (parser real)

Al escribir el `BoletinOficialPdfClient` real (no el spike) descubrimos
un **hallazgo adicional importante** sobre la "Cuarta Sección":

- El PDF de `cuarta.pdf` (que bajamos en el spike) NO contiene
  designaciones. Contiene **"Registro de Dominios de Internet"** — un
  listado de altas, bajas y transferencias de dominios `.ar`. Nada que
  ver con designaciones políticas.
- Las designaciones de funcionarios públicos se publican como
  **decretos dentro de la Primera Sección**. Ejemplo del PDF fixture:
  > MINISTERIO DE CAPITAL HUMANO. Decreto 412/2026.
  > DECTO-2026-412-APN-PTE - Desígnase Subsecretario Legal.

Implicación: **v1 sólo procesa la Primera Sección**. El enum
`SeccionBO.DESIGNACIONES` queda como categoría lógica reservada para
v2, cuando el clasificador LLM podrá distinguir designaciones (es
decreto + sumario empieza con "Desígnase…") de otras leyes/decretos
y la UI las filtrará como vista separada.

`SECCIONES_ACTIVAS_V1 = {SeccionBO.LEGISLACION}` se redujo en
consecuencia. El test `test_solo_legislacion_y_designaciones` se
renombró a `test_solo_legislacion`.

Los PDFs `cuarta.pdf` y los HTML de `designaciones__*.html` del spike
quedan en el repo como evidencia documental.
