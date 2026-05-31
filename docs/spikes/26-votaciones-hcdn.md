# Spike 26.1 — Portal de votaciones HCDN

**Branch:** `feat/26-briefing-pre-sesion`
**Fecha:** 2026-05-31
**Conclusión:** el ADR 0005 se sostiene con ajustes menores.

## Objetivo del spike

Validar **antes** de invertir 3-5 días en el módulo, que el portal de
votaciones nominales de HCDN sigue accesible, parseable y trae los datos
que el briefing necesita (recomendación de voto basada en cómo votó el
bloque la última vez).

## Hallazgos

### Portal accesible

| | |
|---|---|
| URL base | `https://votaciones.hcdn.gob.ar/` |
| Status | 200 OK con `User-Agent: PraxisAsesor/0.1 (+contacto@dominio.com)` |
| Bot detection | No bloqueó el UA del scraper de Praxis |
| Rate limit | Sin headers explícitos. Mantenemos 1 req/s como `HcdnScraper` |
| Endpoint de búsqueda | `GET /votaciones/search?anoSearch=2025&txtSearch=` |
| Endpoint de detalle | `GET /votacion/{id}` (HTML) y `/pdf/acta/{id}` (PDF) |
| Avatares legisladores | `/assets/diputados/A{id}` (potencial llave para cruzar con catálogo futuro) |

### Listado (home y search)

- **Home (`/`)** trae las **500 votaciones más recientes**. Las más viejas datan de **2021-12-16**, las nuevas son del día.
- Filtro `anoSearch={año}` reduce al año específico. Confirmado: 2025 → 116 votaciones; años están entre 1993 y 2026 (35 opciones).
- Filtro `txtSearch={query}` busca por texto libre en el título.

Una fila del listado:

```
FECHA              | TÍTULO                                      | TIPO              | RESULTADO
20/05/2026 22:07   | O.D. 84 - RÉGIMEN DE ZONA FRÍA. ...         | Votación Nominal  | AFIRMATIVO
```

Links de la fila: `/pdf/acta/5937` (PDF oficial) + `/votacion/5937` (HTML detalle).

### Detalle de una votación

Ejemplo: `https://votaciones.hcdn.gob.ar/votacion/5937` (885 KB HTML).

Encabezado parseable:

| Campo | Valor de muestra |
|---|---|
| Título | `O.D. 84 - RÉGIMEN DE ZONA FRÍA. MODIFICACIÓN. DICT. DE MAY. CAPÍTULO VI.` |
| Fecha + hora | `20/05/2026 - 22:07` |
| Sesión | `Período 144 - Reunión 3 - Acta 20` |
| Presidida por | `MENEM, MARTIN` |
| Resultado | `AFIRMATIVO` |
| Totales | 137 afirmativos · 102 negativos · 1 abstención · 1 sin votar · 16 ausentes |

Tabla de votos individuales (258 filas):

```
DIPUTADO              | BLOQUE              | PROVINCIA  | ¿CÓMO VOTÓ?  | ¿QUÉ DIJO?
YEDLIN, PABLO RAUL    | Union Por La Patria | Tucumán    | NEGATIVO     | (opcional)
...
```

Voto puede ser: `AFIRMATIVO`, `NEGATIVO`, `ABSTENCION`, `SIN VOTAR`, `AUSENTE`.

Cada legislador tiene un asset link `/assets/diputados/A{id}`. Ese `{id}`
parece ser un identificador estable del legislador en el portal — útil
para el catálogo futuro de legisladores.

### Cruce a expediente

**El detalle NO contiene número de expediente** del proyecto votado.
Solo se identifica con `O.D. {N}`, ej `O.D. 84`.

El cruce a expediente requiere:

1. Parsear `O.D. 84` del título.
2. Consultar el OD 84 de la sesión correspondiente.
3. Listar los expedientes incluidos en ese OD.

Es decir, **la votación cruza con el OD, no directo con el expediente**.
Esto valida la decisión del ADR 0005 de `Votacion.expediente_id` como
`NULL` por default, con cruce best-effort.

Algunas votaciones son "MOCION SOLICITADA POR EL DIP. XYZ" sin referencia
a OD ni expediente. Para esas el cruce queda `NULL` permanente.

### Datos abiertos / export

El portal tiene botones "XLSX" y "CSV" pero son funciones JS
(`javascript:exportExcel()`, `javascript:exportCSV()`) que generan el
archivo en el browser desde el DOM ya cargado. **No hay endpoint API
JSON oficial**. Vamos por HTML scraping.

## Implicaciones para el ADR 0005

El modelo del ADR queda confirmado con dos ajustes:

1. **Agregar `Votacion.titulo_od`** (string opcional): para parsear el
   `O.D. 84` del título y eventualmente cruzarlo con la entidad
   `OrdenDelDia` del spec 14 (cruce diferido a feat/29).
2. **Agregar `Votacion.acta_pdf_url`** y `Votacion.acta_id_hcdn`: el portal
   identifica cada acta con un ID propio (`5937`). Persistirlo evita
   re-descargar y permite vincular al PDF oficial desde la UI.

Ningún cambio estructural — son campos extra a la tabla.

## Costo estimado del módulo

Confirmado: **3-5 días** según ADR 0005.

- Scraper (search + detalle + parser HTML) → 1.5 días.
- Modelos ORM + migración + repo → 1 día.
- Tests con fixtures → 1 día.
- Script seed para sembrar votaciones 2024-2026 → 0.5 días.

## Fixtures guardadas

```
backend/spikes/votaciones/
  home.html              (2.0 MB — listado de las 500 más recientes)
  votacion_5937.html     (885 KB — detalle con tabla de 257 votos)
  votacion_5931.html     (885 KB — segundo ejemplo)
```

Vamos a usarlas como fixtures de los tests de parseo en `feat/26.3`.

## Decisión

✅ **Avanzar con el módulo de votaciones nominales** según ADR 0005, con
los dos ajustes menores señalados arriba.

## Próximo paso sugerido

`feat/26.2` — implementar `VotacionesHcdnScraper` + parser HTML usando
las fixtures de este spike, sin tocar la DB todavía.
