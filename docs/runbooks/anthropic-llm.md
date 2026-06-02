# Runbook — Anthropic LLM provider

Cómo enchufar el `AnthropicLlmProvider` (Claude Sonnet 4.5) en el
backend de Praxis Asesor, con un cap de gasto duro en la consola de
Anthropic.

Ver `praxis/infrastructure/llm/anthropic_provider.py` y
`praxis/api/deps.py::get_llm_provider`.

## 1. Crear la API key

1. Loguearse en https://console.anthropic.com.
2. Settings → **API Keys** → "Create Key".
3. Nombre sugerido: `praxis-asesor-dev` (o `prod` cuando corresponda).
4. Copiar el valor que empieza con `sk-ant-...`. **No se vuelve a mostrar.**

## 2. Setear el cap mensual (paso obligatorio)

1. Settings → **Limits** → "Spend limit".
2. Setear el cap en USD del mes corriente. **Recomendado para arrancar: 5 USD/mes.**
3. Si se llega al cap, Anthropic devuelve `429` y la API se corta sola
   hasta el ciclo siguiente. El backend lo va a ver como una excepción
   genérica desde el SDK; el caller (use case del briefing) propaga el
   error.
4. Anthropic además permite alertas por email al 50% / 80% / 100% del
   cap — conviene activarlas.

## 3. Configurar el backend

Agregar a `backend/.env` (no versionado):

```
ANTHROPIC_API_KEY=sk-ant-...
# opcional, default ya apunta a Sonnet 4.5:
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

Reiniciar el backend. Al primer request de IA, `get_llm_provider`
detecta la key y arma `AnthropicLlmProvider` en vez del fake.

## 4. Verificar que está activo

```bash
# Smoke: regenerar un briefing existente con regenerar=true
curl -X POST http://127.0.0.1:8000/api/v1/briefings \
  -H "Authorization: Bearer dev:user_agustin" \
  -H "X-Despacho-Id: <despacho-uuid>" \
  -H "Content-Type: application/json" \
  -d '{"orden_del_dia_id": "<od-uuid>", "regenerar": true}' | jq .modelo_llm
```

Debe responder `"claude-sonnet-4-5-..."` (no `"fake-keywords"`).

## 5. Volver al modo gratis

Comentar / borrar `ANTHROPIC_API_KEY` del `.env` y reiniciar. El
provider vuelve a ser el `FakeLlmProvider` sin tocar más nada.

## Costos esperados

Con Sonnet 4.5 + prompt caching activo (system prompt cacheado a
`cache_control: ephemeral`):

| Llamada | Input | Output | Costo/call |
|---|---|---|---|
| Clasificación temática (con cache hit) | ~600 tok | ~20 tok | $0.0008 |
| Argumentos por proyecto | ~1.500 tok | ~250 tok | $0.008 |
| Contraargumentos por proyecto | ~1.500 tok | ~200 tok | $0.008 |

Briefing típico (40 expedientes en OD, 5 del despacho):

- 20 clasificaciones nuevas: ~$0.04
- 5 × argumentos: ~$0.04
- 5 × contraargumentos: ~$0.04
- **Total: ~$0.12 USD por briefing**

Con cap de 5 USD/mes alcanza para ~40 briefings completos. Suficiente
para validar antes de escalar.

## Troubleshooting

| Síntoma | Causa probable |
|---|---|
| Briefing vuelve a tener bullets genéricos | Falta `ANTHROPIC_API_KEY` en `.env` o el backend no se reinició |
| Endpoint tira `anthropic.AuthenticationError` | Key inválida o revocada en la consola |
| Endpoint tira `anthropic.PermissionDeniedError` | Cap del mes alcanzado o cuenta sin saldo |
| Bullets cortados a mitad | `max_tokens` bajo — subir en `anthropic_provider.py` |
| Bullets mal parseados | El modelo devolvió numeración, asteriscos extras, etc. Ajustar `_parsear_bullets()` o pedir formato más estricto en el prompt |

## Cuándo bajar a Haiku

Si el cap de Sonnet se queda corto, una opción intermedia es usar
Haiku solo para clasificación (~$0.0003/call) y dejar Sonnet para
argumentos. Requiere refactor para tener dos providers en paralelo;
no está implementado todavía.
