# Runbook — Levantar el frontend en dev

**Cuándo seguirlo:** primera vez que clonás el repo, o cuando hayas
borrado `frontend/node_modules`.

## Prerequisitos

- Node ≥ 22.
- pnpm ≥ 9 (`corepack enable && corepack prepare pnpm@latest --activate`).
- Backend funcionando (ver [runbook backend](smoke-test-postgres.md)).
- Cuenta en [Clerk](https://dashboard.clerk.com) con una **Application** creada.

## Pasos

### 1. Instalar dependencias

```powershell
cd C:\Users\agust\Desktop\praxis-asesor\frontend
pnpm install
```

La primera vez tarda 1–2 min. Genera `node_modules/` y `pnpm-lock.yaml`.

### 2. Configurar Clerk

En el [Clerk dashboard](https://dashboard.clerk.com):

1. Crear una **Application** (free tier alcanza para dev).
2. En **API Keys**, copiar:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` → empieza con `pk_test_`.
   - `CLERK_SECRET_KEY` → empieza con `sk_test_`.
3. En **Sessions**, opcionalmente activar "Customize session token" y agregar
   `email` como claim (mejora la UX si después queremos email en el JWT).
4. (Opcional, para webhooks) En **Webhooks** → "Add Endpoint":
   - URL: `https://[ngrok-o-vercel]/api/v1/webhooks/clerk`
   - Eventos: `user.created`, `user.updated`, `user.deleted`.
   - Copiar el **Signing secret** (`whsec_...`) → va en `backend/.env`
     como `CLERK_WEBHOOK_SECRET`.

### 3. Configurar variables de entorno

```powershell
cd frontend
Copy-Item .env.example .env.local
notepad .env.local
```

Completar con las keys de Clerk del paso 2:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_real_value
CLERK_SECRET_KEY=sk_test_real_value
```

(El resto de variables `NEXT_PUBLIC_CLERK_*_URL` ya tienen defaults razonables.)

### 4. Configurar el backend para que Clerk funcione

En `backend/.env`, agregar (las URLs salen del dashboard de Clerk, en
"Frontend API"):

```env
CLERK_ISSUER=https://your-app.clerk.accounts.dev
CLERK_JWKS_URL=https://your-app.clerk.accounts.dev/.well-known/jwks.json
CORS_ORIGINS=http://localhost:3000
```

Reiniciar el backend si estaba corriendo:

```powershell
# Ctrl+C en la terminal del backend, después:
cd C:\Users\agust\Desktop\praxis-asesor\backend
uv run python -m praxis.api.main
```

### 5. Seedeá un usuario con tu Clerk user_id

Para que el backend te reconozca, tenés que tener un `Usuario` en la DB
con tu `clerk_user_id` en `auth_provider_id`.

```powershell
# Loguearte una vez en Clerk para crear el user, después copiar el user_id
# desde el dashboard (Users → tu user → ID).

cd C:\Users\agust\Desktop\praxis-asesor\backend
uv run python -m scripts.seed_inicial `
  --email "agustin@example.com" `
  --nombre "Agustin DM" `
  --clerk-id "user_xxxxxxxxxxxxxxxxx" `
  --despacho-nombre "Praxis Demo"
```

Anotá el `Despacho ID` que imprime — lo vamos a necesitar para la cookie.

### 6. Arrancar el frontend

```powershell
cd C:\Users\agust\Desktop\praxis-asesor\frontend
pnpm dev
```

Sale el dev server en http://localhost:3000.

### 7. Setear la cookie del despacho (primera vez)

Como el frontend todavía no tiene un selector de despacho UI, hay que setear
la cookie a mano la primera vez:

1. Abrir http://localhost:3000 → Clerk te manda a `/sign-in`.
2. Loguearte con la misma cuenta del paso 5.
3. Cuando aterriza en `/dashboard`, va a mostrar
   **"Despacho no seleccionado"** (esperado).
4. En la DevTools del browser (F12 → Application → Cookies →
   localhost:3000), crear manualmente:
   - **Name:** `praxis_despacho_id`
   - **Value:** `<el UUID del despacho del seed>`
   - **HttpOnly:** ✓
   - **SameSite:** Lax
5. Recargar la página. Ahora deberías ver el dashboard real con
   "Mis seguimientos".

> 🚧 **Mejora futura:** el siguiente PR de frontend agrega un selector
> de despacho en la topbar que llama a la Server Action y elimina este
> paso manual.

## Troubleshooting

### "Missing publishable key"

Falta `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` en `.env.local`. Verificá el archivo.

### El dashboard tira 401

El usuario seedeado no matchea con el Clerk user_id de la sesión actual.
Re-verificá que el `--clerk-id` del seed coincide con el `user_id` que ves
en Clerk → Users → (tu cuenta).

### CORS error en consola del browser

El backend no tiene `localhost:3000` en `CORS_ORIGINS`. Editar `backend/.env`,
poner `CORS_ORIGINS=http://localhost:3000`, reiniciar el backend.

### "Despacho no seleccionado" persiste después de setear la cookie

Cookie mal puesta. Verificar en DevTools que aparece en
`Application → Cookies → http://localhost:3000` con name **exactamente**
`praxis_despacho_id`.

### Tipos rotos después de tocar el backend

Regenerar:

```powershell
# Backend tiene que estar corriendo en :8000.
cd frontend
pnpm gen:api-types
```
