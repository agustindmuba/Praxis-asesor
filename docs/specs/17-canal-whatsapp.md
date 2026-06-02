# Spec 17 — Canal WhatsApp (infraestructura compartida)

**Estado:** borrador · **Owner:** Agustín · **Branch sugerida:** `feat/41-canal-whatsapp`

## Por qué una spec aparte

WhatsApp aparece en dos features muy distintas (briefing diario en spec
15+16, alertas de menciones en spec 16) y va a aparecer en más a futuro
(alertas de votación nominal, recordatorios pre-sesión, etc.). El modelo
de destinatarios, plantillas, ventana de 24hs, anti-flood y registro de
envíos para auditoría son los mismos para todos los consumidores.

Concentrarlo acá:

- Evita duplicar modelos y código entre features.
- Permite que el ADR 0008 sea autónomo y referenciable.
- Habilita un futuro 3er o 4to consumidor sin tocar las specs anteriores.

## Problema

Praxis necesita un canal **proactivo** de notificación al despacho. Email
es lento y se pierde en bandejas de entrada; SMS es caro y tiene mala UX
en Argentina; push browser nativo asume que el legislador deja la pestaña
abierta. **WhatsApp es donde la política argentina vive.** Es el canal
real de coordinación entre asesores, legisladores y bloque.

Pero WhatsApp como canal proactivo no es trivial:

- Meta exige **plantillas pre-aprobadas** para mensajes iniciados fuera
  de la ventana de 24hs ("conversación con el usuario abierta").
- Las plantillas tardan 24-48hs en ser aprobadas. Es prerequisito de
  onboarding.
- Hay categorías (`utility`, `marketing`, `authentication`) con costo y
  reglas distintas.
- Cada destinatario tiene que dar **opt-in explícito** (regla Meta).
- Hay que respetar **opt-out** inmediato si el usuario manda STOP.
- Anti-flood obligatorio para no quemar el número de Praxis.

## Usuario y caso de uso

**Usuario interno (Praxis):** los servicios de spec 15 y 16 que producen
mensajes para destinatarios.

**Usuario final (despacho):**

- **Onboarding**: define quién recibe qué.
- **Día a día**: recibe briefings + alertas en su WhatsApp personal o de
  trabajo. Puede pausar / opt-out cuando quiera.

```
CU-1 (onboarding):
  Asesor admin del despacho entra a /configuracion/whatsapp,
  agrega 1-N destinatarios (nombre + teléfono E.164 + rol),
  selecciona qué recibe cada uno (briefing diario, alertas menciones).
  Envío de confirmación opt-in al teléfono.
  Tras confirmar respondiendo "SI", el destinatario queda activo.

CU-2 (envío proactivo programado):
  EnviarBriefingDiario.execute(despacho_id) compone payload de
  plantilla `praxis_briefing_diario_v1`, dispara MessagingProvider,
  persiste EnvioWhatsApp.

CU-3 (alerta inmediata):
  EnviarAlertaMencion.execute(mencion_id) decide individual vs
  agrupada (anti-flood), usa plantilla correspondiente.

CU-4 (opt-out):
  Destinatario responde STOP. Webhook de Meta llega a /webhooks/meta,
  Praxis marca `opt_out_en` y no vuelve a mandar.
```

## Decisiones tomadas (del prompt de Agustín)

| Tema | Decisión |
|---|---|
| Stack | Meta Cloud API directo (no BSPs como Twilio o 360Dialog) |
| Plantillas | Pre-aprobadas por Meta — prerequisito de onboarding |
| Configuración por despacho | Múltiples destinatarios; selección granular de qué recibe cada uno |
| Anti-flood | Obligatorio, decidido en spec 16 (N=3 + agrupamiento) |
| Persistencia de envíos | Auditoría completa: cada envío + estado de entrega vía webhook Meta |

## Decisiones de dominio NUEVAS (resueltas)

- **D11** → **3 plantillas v1** como se documentan abajo
  (`praxis_briefing_diario_v1`, `praxis_mencion_individual_v1`,
  `praxis_mencion_agrupada_v1`). Categoría `utility`, idioma `es_AR`,
  todas con botón URL a la app.
- **D12** → **Solo rol `admin_despacho`** puede ABM destinatarios.
  Otros roles del despacho ven la lista pero no editan. Cambios
  quedan auditados con `usuario_id` que disparó la operación.
- **D13** → **Sin fallback en v1.** Opt-out de WhatsApp = no recibe
  notificaciones. Sigue viendo todo en la app. Email queda
  explícitamente para v2 si aparece el caso en producción.
- **D14** → **Cap mensual: 1.500 mensajes / despacho.** Cubre escenario
  típico (~990) con margen 50% para días pico. Alerta interna cuando
  un despacho llega al 80% del cap. Estimado ~USD 15/mes/despacho a
  precio Meta utility AR vigente.
- **D15** → **Un único número Meta para Praxis.** Verificación de
  marca única, una sola cuenta WhatsApp Business Account. Todos los
  despachos reciben mensajes desde ese número. Multi-número por
  despacho queda v2 si lo pide el cliente.

## Solución propuesta

Adaptador `WhatsAppCloudApiProvider` que implementa el puerto
`MessagingProvider`. Bajo el capó:

1. Persistir mensaje en `EnvioWhatsApp` con estado `pendiente`.
2. POST a Meta Cloud API `/messages` con plantilla + parámetros.
3. Actualizar estado a `enviado` con `message_id_meta` que responde la
   API.
4. Webhook `POST /webhooks/meta/messages-status` actualiza estado a
   `entregado` / `leido` / `fallo` según los callbacks de Meta.
5. Webhook `POST /webhooks/meta/inbound` captura respuestas del
   destinatario (STOP, opt-in "SI", etc.) y actualiza `Destinatario`.

Configuración del número:

- En `.env`: `META_WHATSAPP_PHONE_NUMBER_ID`, `META_WHATSAPP_TOKEN`,
  `META_BUSINESS_ACCOUNT_ID`, `META_VERIFY_TOKEN` (para validar
  webhooks).
- Modelo recomendado v1: **un número único Praxis** (más barato +
  simpler para verificación de marca con Meta). Multi-número por
  despacho queda v2. Confirmar en D15.

## Modelo de dominio nuevo

```python
@dataclass(frozen=True, slots=True)
class Destinatario:
    """Persona que recibe mensajes de Praxis vía WhatsApp."""
    id: UUID | None
    despacho_id: UUID
    usuario_id: UUID | None     # opt: link al Usuario interno si existe
    nombre: str
    rol_interno: str            # "legislador", "jefe_asesores", "asesor_temático", "comunicacion"
    telefono_e164: str          # "+5491133445566"
    recibe_briefing_diario: bool
    recibe_alertas_menciones: bool
    recibe_alertas_otras: bool  # placeholder para v2 (ej: votaciones)
    opt_in_en: datetime | None
    opt_out_en: datetime | None
    activo: bool                # derivado: opt_in_en AND NOT opt_out_en

@dataclass(frozen=True, slots=True)
class PlantillaWhatsApp:
    """Plantilla pre-aprobada por Meta. Catálogo interno."""
    name: str                   # "praxis_briefing_diario_v1"
    idioma: str                 # "es_AR"
    categoria: Literal["utility", "marketing", "authentication"]
    body_params: list[str]      # nombres declarativos: ["fecha", "cuerpo_briefing"]
    estado_meta: Literal["pendiente_aprobacion", "aprobada", "rechazada", "pausada"]
    aprobada_en: datetime | None
    contenido_referencia: str   # texto de la plantilla para revisión interna

@dataclass(frozen=True, slots=True)
class EnvioWhatsApp:
    """Registro de un envío específico. Auditable."""
    id: UUID | None
    destinatario_id: UUID
    despacho_id: UUID           # desnormalizado para queries por despacho
    plantilla_name: str
    tipo: Literal[
        "briefing_diario",
        "mencion_individual",
        "mencion_agrupada",
        "otros",
    ]
    payload_params: dict[str, str]    # los valores enviados a Meta
    correlativo_id: UUID | None       # ej: briefing_id o mencion_id origen
    enviado_en: datetime | None
    estado: Literal[
        "pendiente",
        "enviado",
        "entregado",
        "leido",
        "fallo",
        "rechazado_opt_out",
    ]
    message_id_meta: str | None
    error: str | None

@dataclass(frozen=True, slots=True)
class PerfilInteresDespacho:
    """Perfil declarativo del despacho para evaluar accionabilidad."""
    despacho_id: UUID
    areas_tematicas: list[str]      # subset de las 12
    comisiones_legislador: list[str]  # nombres como aparecen en HCDN/HSN
    distritos_observados: list[str]   # ["Buenos Aires", "CABA"]
    aliases_legislador: list[str]     # ["Pablo Juliano", "Juliano", "@PJuliano"]
    actualizado_en: datetime
```

`PerfilInteresDespacho` vive en esta spec porque es compartido entre 15
y 16 y se configura desde la misma pantalla de onboarding. Puede
moverse a una micro-spec separada si Agustín lo prefiere — decisión D1
indirectamente lo afecta.

## Plantillas WhatsApp para v1

Aprobadas en D11 (3 plantillas) + ADR 0008 (4ª plantilla `praxis_optin_v1`
agregada al definir el flujo de onboarding). **Total v1: 4 plantillas.**
Cada una se manda a Meta para aprobación al arranque del onboarding del
primer despacho real (24-48hs).

### `praxis_briefing_diario_v1`

- Categoría: **utility** (es un resumen periódico que el usuario ha
  pedido recibir).
- Idioma: `es_AR`.
- Body params: `{{1}} = fecha`, `{{2}} = cuerpo_briefing` (texto
  preformateado con BO + Noticias, máximo ~900 chars).
- Botón URL: "Abrir Praxis Asesor" → `https://app.praxis…/dashboard`.
- Contenido de referencia:

  ```
  📋 Briefing Praxis · {{1}}
  
  {{2}}
  ```

### `praxis_mencion_individual_v1`

- Categoría: **utility**.
- Idioma: `es_AR`.
- Body params: `{{1}} = fuente`, `{{2}} = hora`, `{{3}} = tono`,
  `{{4}} = alcance`, `{{5}} = titulo_articulo`.
- Botón URL dinámico: "Ver nota" → URL del artículo. Botón secundario:
  "Histórico de menciones" → `/menciones`.
- Contenido de referencia:

  ```
  🔔 Mención detectada
  Fuente: {{1}} · {{2}}
  Tono: {{3}} · Alcance: {{4}}
  
  "{{5}}"
  ```

### `praxis_mencion_agrupada_v1`

- Categoría: **utility**.
- Idioma: `es_AR`.
- Body params: `{{1}} = cantidad`, `{{2}} = distribucion_tono`,
  `{{3}} = top_fuentes`.
- Botón URL: "Ver detalle en la app" →
  `/menciones?desde=…&hasta=…`.
- Contenido de referencia:

  ```
  🔔 {{1}} menciones en la última hora
  {{2}}
  Top: {{3}}
  ```

### `praxis_optin_v1`

Plantilla del primer contacto al destinatario. Sirve para que el
destinatario confirme opt-in respondiendo "SI". Sin esta confirmación,
los envíos del briefing diario y de las alertas quedan en pendiente.

- Categoría: **utility**.
- Idioma: `es_AR`.
- Body params: `{{1}} = nombre_destinatario`, `{{2}} = nombre_despacho`.
- Sin botón URL (queremos respuesta de texto).
- Contenido de referencia:

  ```
  Hola {{1}},
  
  El despacho {{2}} te dio de alta en Praxis Asesor para recibir
  el briefing diario y alertas en este teléfono.
  
  Respondé SI para confirmar.
  Respondé STOP en cualquier momento para darte de baja.
  ```

## Puertos y casos de uso

```python
class MessagingProvider(ABC):
    """Adaptador para enviar mensajes a un destinatario."""
    async def enviar_plantilla(
        self,
        *,
        destinatario: Destinatario,
        plantilla: PlantillaWhatsApp,
        params: dict[str, str],
        correlativo_id: UUID | None,
        tipo: str,
    ) -> EnvioWhatsApp: ...

class DestinatarioRepository(ABC):
    async def crear(self, d: Destinatario) -> Destinatario: ...
    async def buscar_por_despacho(self, despacho_id: UUID) -> list[Destinatario]: ...
    async def marcar_opt_in(self, id: UUID) -> None: ...
    async def marcar_opt_out(self, telefono_e164: str) -> None: ...

class PlantillaWhatsAppRepository(ABC):
    async def por_name(self, name: str) -> PlantillaWhatsApp | None: ...
    async def listar_aprobadas(self) -> list[PlantillaWhatsApp]: ...

class EnvioWhatsAppRepository(ABC):
    async def crear(self, e: EnvioWhatsApp) -> EnvioWhatsApp: ...
    async def actualizar_estado(
        self, *, message_id_meta: str, nuevo_estado: str, error: str | None
    ) -> None: ...
    async def listar_por_despacho(
        self, *, despacho_id: UUID, desde: datetime, hasta: datetime
    ) -> list[EnvioWhatsApp]: ...

class RegistrarDestinatario:
    async def execute(self, *, despacho_id: UUID, datos: dict) -> Destinatario: ...
    # envía mensaje de confirmación opt-in

class ProcesarWebhookMeta:
    async def execute(self, *, payload: dict) -> None: ...
    # actualiza estados de envío + opt-out
```

## Endpoints API

```
POST   /api/v1/destinatarios
       body: { nombre, telefono_e164, rol_interno, recibe_briefing_diario, recibe_alertas_menciones }
       → registra + dispara opt-in
GET    /api/v1/destinatarios
DELETE /api/v1/destinatarios/{id}

GET    /api/v1/perfil-interes
PUT    /api/v1/perfil-interes
       body: { areas_tematicas[], comisiones_legislador[], distritos_observados[], aliases_legislador[] }

POST   /webhooks/meta/messages-status      (público, validado con verify_token)
POST   /webhooks/meta/inbound              (público, validado con verify_token)

GET    /api/v1/envios?desde=&hasta=        (auditoría interna del despacho)
```

## UI

Nueva ruta `/configuracion`:

- Pestaña **Perfil de interés**: edita áreas temáticas, comisiones,
  distritos, alias del legislador.
- Pestaña **Destinatarios WhatsApp**: tabla CRUD de destinatarios,
  estado opt-in/opt-out, qué recibe cada uno.
- Pestaña **Historial de envíos**: tabla auditable (último N envíos,
  estado, plantilla).

## Anti-flood y agrupamiento

La lógica concreta vive en spec 16 (sec. "Anti-flood y agrupamiento").
La spec 17 solo provee la infraestructura: `MessagingProvider`,
`EnvioWhatsApp`, persistencia. El buffer Redis lo gestiona el caso de
uso `EnviarAlertaMencion` definido en spec 16.

Si Agustín quiere formalizar el algoritmo como decisión arquitectónica
(en lugar de "vive en una spec de feature"), abrimos **ADR 0009 —
Anti-flood y agrupamiento de alertas**.

## Criterios de aceptación

- [ ] Modelo de dominio + repos + migración Alembic listos.
- [ ] `WhatsAppCloudApiProvider` implementa `MessagingProvider`,
      tests con HTTP mockeado (`respx`).
- [ ] Webhook de Meta validado con `META_VERIFY_TOKEN` y firma
      `X-Hub-Signature-256` (HMAC).
- [ ] Las 3 plantillas v1 documentadas con su contenido de referencia,
      el script para registrarlas en Meta y el procedimiento de
      onboarding (24-48hs).
- [ ] Opt-in: envío de mensaje de confirmación + handler de respuesta
      "SI"/"NO" actualiza `Destinatario`.
- [ ] Opt-out: cualquier mensaje del destinatario con texto STOP marca
      `opt_out_en` y bloquea futuros envíos a ese teléfono.
- [ ] Estado del envío se actualiza vía webhook (pendiente → enviado →
      entregado → leído / fallo).
- [ ] Vista `/configuracion` permite el ABM completo.
- [ ] Smoke real: un envío de prueba al teléfono de Agustín, opt-in OK,
      briefing diario llega, opt-out OK.
- [ ] Lint, type-check y tests verdes.

## Fuera de alcance (v1)

- **Multi-número por despacho** (cada despacho con su número Meta) —
  decisión D15.
- **Conversación bidireccional inteligente** ("¿qué proyectos
  tratamos esta semana?" → bot responde). Solo opt-in / opt-out se
  procesan, el resto se descarta y se registra como noise.
- **Mensajes multimedia** (imagen, PDF del briefing por WhatsApp). Solo
  texto + botón URL.
- **Email como canal alternativo**. Posiblemente v2 (D13).
- **Push browser nativo** (Service Worker).
- **Integración con Telegram, Signal o iMessage**.
- **Mensajes de marketing** (categoría `marketing` de Meta). Solo
  `utility` para v1.

## Riesgos

- **Plantillas no aprobadas a tiempo** → bloquea onboarding. Mitigación:
  someter las 3 plantillas a Meta apenas se apruebe esta spec, antes de
  empezar a codear el resto.
- **Cuenta de WhatsApp Business suspendida** por alto rate de
  bloqueos / opt-outs masivos → mitigación: opt-in explícito antes de
  enviar nada, manejo limpio de STOP, cap de mensajes por destinatario.
- **Costo descontrolado** → cap mensual por despacho + alerta interna
  cuando ronda el 80% del cap.
- **Webhook caído / mensajes perdidos** → idempotencia por
  `message_id_meta`, retries con backoff, dashboard `/configuracion`
  muestra estado y permite reenvío manual.
- **Latencia de Meta API** (a veces hay backpressure) → cola Celery
  con prioridad, alertas de SLA si la mediana sube de 5s.
- **Confusión de despacho** (mandar al destinatario equivocado por bug
  en tenancy) → tests específicos de tenant isolation en todos los
  endpoints + caso de uso; `despacho_id` desnormalizado en
  `EnvioWhatsApp` para auditar en queries.

## Plan de tests

- **Unit (dominio)**: Destinatario invariantes, telefono_e164
  validado.
- **Unit (provider)**: `WhatsAppCloudApiProvider` con `respx`
  mockeando Meta; verificar payload, headers, retries.
- **Unit (webhook)**: validación de firma HMAC, parseo de estados,
  parseo de STOP/SI.
- **Integration (no en CI)**: envío real al teléfono de prueba
  (manual, `@pytest.mark.network`).
- **Tenant isolation**: tests garantizan que un envío de despacho A no
  toca destinatario de despacho B aunque tengan teléfonos iguales
  (raro pero posible).
- **Eval de plantillas**: visualización en la sandbox de Meta con
  payloads reales para verificar layout antes de aprobar.

## Dependencias

- ADR 0008 (integración WhatsApp Cloud API).
- ADR 0009 sugerido (anti-flood y agrupamiento) — opcional.
- Variables de entorno Meta (`META_*`) configuradas en `backend/.env`
  con cap de gasto en consola Meta.
- Spec 15 + Spec 16 son los consumidores principales.
