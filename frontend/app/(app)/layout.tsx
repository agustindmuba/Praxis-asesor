/**
 * Layout de la app autenticada — sidebar + topbar + content area.
 *
 * Server Component que:
 * 1. Resuelve el `ApiContext` (token + cookie del despacho).
 * 2. Si no hay despacho en cookie, llama a `/me` para obtener el activo
 *    y setea la cookie via Server Action.
 * 3. Pasa `me` y `despachoActivoId` al provider del store cliente.
 */
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { DespachoBootstrap } from "@/components/providers/despacho-bootstrap";
import { ApiError, ApiError401, ApiError403 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getMe } from "@/lib/api/endpoints";

// Helper: en dev redirigimos a /dev-login para re-seleccionar despacho.
// En prod a /sign-in. La limpieza efectiva de cookies se hace ahí
// (que sí son Server Actions / Route Handlers válidos), no acá.
function redirectToLogin(): never {
  redirect(
    process.env.NODE_ENV === "production" ? "/sign-in" : "/dev-login",
  );
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const ctx = await getApiContextServer();
  if (!ctx.token) {
    redirectToLogin();
  }

  // Si no hay cookie de despacho, mandamos al login para que lo seleccione.
  // En Next 15 no se puede setear cookies durante el render del layout
  // (solo en Server Actions o Route Handlers).
  if (!ctx.despachoId) {
    redirectToLogin();
  }

  let me;
  try {
    me = await getMe(ctx);
  } catch (err) {
    if (err instanceof ApiError401) {
      redirectToLogin();
    }
    if (err instanceof ApiError403) {
      // El despacho cookie no corresponde al usuario actual. No podemos
      // limpiar la cookie acá (Next 15); el login va a sobrescribirla.
      redirectToLogin();
    }
    // 400 del backend cuando el despacho_id no existe → también mandamos al login.
    if (err instanceof ApiError && err.status === 400) {
      redirectToLogin();
    }
    throw err;
  }

  return (
    <DespachoBootstrap despachoActivoId={me.despacho.id}>
      <AppShell me={me}>{children}</AppShell>
    </DespachoBootstrap>
  );
}
