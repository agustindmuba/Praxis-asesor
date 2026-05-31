# Spec 13 — Resumen ejecutivo del expediente con IA

**Estado:** propuesta · **Owner:** Agustín · **Branch:** `feat/24-resumen-ia`

## Objetivo

Que un asesor pueda **decidir si vale la pena leer 40 páginas de un proyecto**
con un click. El botón "Resumir con IA" genera 3 bullets:

1. **Qué propone** — en castellano simple, sin jurispeak.
2. **Quién lo impulsa** — primer firmante + bloque.
3. **Probabilidad de avance** — basado en estado actual + caducidad.

Cada uno tarda ~8-10 segundos contra Sonnet 4.5 real. Se cachea en DB:
una sola corrida por expediente, el resto son lecturas gratis.

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Modelo | Claude Sonnet 4.5 (cuando se enchufe) |
| Trigger | Botón explícito en la ficha (no auto) |
| Cache | En DB. Una corrida por expediente |
| Modo dev | `FakeLlmProvider` que arma resúmenes a partir de los datos ya en DB. No gasta API |
| Regenerar | Por ahora no — si el expediente cambió, se borra el resumen viejo manualmente |

## Modelo de datos

```
resumen_ejecutivo
  id UUID PK
  expediente_id UUID FK → expediente.id (UNIQUE)
  contenido_md TEXT      -- markdown con los 3 bullets
  modelo VARCHAR(50)     -- "fake" | "claude-sonnet-4-5-20251022" | etc.
  prompt_version VARCHAR(20) -- "v1" — para invalidar caches en futuras mejoras
  generado_en TIMESTAMPTZ DEFAULT now()
```

Una sola fila por expediente. Si querés regenerar, se borra y se vuelve a llamar.

## Puerto y caso de uso

```python
class LlmProvider(ABC):
    @abstractmethod
    async def generar_resumen_ejecutivo(
        self,
        expediente: Expediente,
    ) -> str:
        """Devuelve el contenido markdown del resumen.

        El caller decide cuándo invocar (tras chequear cache).
        El provider es responsable del prompt + parsing de la respuesta.
        """


class GenerarResumenEjecutivo:
    """Caso de uso. Devuelve un ResumenEjecutivo, cacheado en DB."""
    async def execute(self, expediente_id: UUID) -> ResumenEjecutivo:
        # 1. Buscar el expediente
        # 2. Si ya hay resumen en DB, devolverlo
        # 3. Si no, llamar LlmProvider, persistir, devolver
```

## Implementaciones de `LlmProvider`

### `FakeLlmProvider` (default en dev)

Arma los 3 bullets a partir de los datos ya en DB:

- "Qué propone": deriva del título + sumario. Pequeño formateo.
- "Quién lo impulsa": primer firmante por orden + bloque (si está).
- "Probabilidad de avance": mapeo del estado actual:
  - `INGRESADO` → "baja — todavía no fue a comisión"
  - `EN_COMISION` → "moderada — depende de prioridades de la comisión"
  - `CON_DICTAMEN` → "alta — listo para tratamiento en recinto"
  - `MEDIA_SANCION_*` → "muy alta — solo le falta la otra cámara"
  - `CADUCO`/`SANCIONADO`/`ARCHIVADO` → "ninguna — el expediente terminó su trámite"
  - Plus: si `fecha_caducidad` está a < 60 días, agrega "atención: vence pronto".

Devuelve markdown. No hace network calls. Costo: 0.

### `AnthropicLlmProvider` (cuando el user diga "enchufá")

- Lee `texto_url` del expediente → descarga PDF → extrae con `pdfplumber`.
- Construye un prompt con: título, sumario, texto truncado a ~30k tokens.
- Llama Sonnet 4.5 vía Anthropic SDK.
- Parsea la respuesta (debe seguir el formato de 3 bullets).
- Cachea en `resumen_ejecutivo.modelo = "claude-sonnet-4-5-..."`.

**Cuando se quiera activar**: agregar `ANTHROPIC_API_KEY` al `.env`. El
`get_llm_provider` dep elige automáticamente: si hay key, Anthropic; sino, Fake.

## Endpoint

`POST /api/v1/expedientes/{id}/resumir`

- Auth: `current_context` (multi-tenant, igual que el resto).
- Sin body.
- Response 200:
  ```json
  {
    "id": "uuid",
    "expediente_id": "uuid",
    "contenido_md": "**Qué propone:** ...",
    "modelo": "fake",
    "prompt_version": "v1",
    "generado_en": "2026-05-29T18:00:00Z"
  }
  ```
- Response 404 si el expediente no existe.
- Idempotente: si ya hay resumen, devuelve el cacheado.

## UI (ficha del expediente)

- Tab nuevo "Resumen IA" o **una caja arriba del header con un botón**.
- Estados:
  - Sin resumen aún → botón **"Resumir con IA"** + disclaimer chico.
  - Cargando → spinner "Pensando..." 10 segundos.
  - Con resumen → render del markdown + chip que dice qué modelo lo generó (`fake` o `Sonnet 4.5`).
- Disclaimer al pie: "Generado por IA. Revisá antes de citar."

## Out of scope

- Re-generar a pedido (regenerate button).
- Streaming de la respuesta (mostrar token por token).
- Múltiples resúmenes por expediente (uno por versión del texto).
- Resúmenes de la ficha en otros idiomas.
- Costo tracking por usuario.

Todo eso entra cuando duela.

## Plan de ejecución

1. Domain + puerto + caso de uso.
2. Tabla `resumen_ejecutivo` + migration + repo SQLAlchemy.
3. `FakeLlmProvider` + `_LLM_PROVIDER` dep en `api/deps.py`.
4. Endpoint POST + DTO + tests.
5. Frontend: botón + sección con markdown render.
6. Probar e2e en /expedientes/[id] real.
