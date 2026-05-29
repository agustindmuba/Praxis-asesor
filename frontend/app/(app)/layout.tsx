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
import { ApiError401, ApiError403 } from "@/lib/api/client";
import { getApiContextServer } from "@/lib/api/context-server";
import { getMe } from "@/lib/api/endpoints";

import { setDespachoActivoAction } from "@/app/actions/despacho";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const ctx = await getApiContextServer();
  if (!ctx.token) {
    redirect("/sign-in");
  }

  // Si no hay cookie de despacho, intentamos resolver el primero del usuario.
  // El backend devuelve 400 si falta `X-Despacho-Id`. Probamos sin cookie
  // primero solo si hace falta un fallback. Para el bootstrap inicial, asumimos
  // que el sysadmin ya seteó la membresía del usuario y el frontend escribió
  // la cookie via Server Action al menos una vez.
  if (!ctx.despachoId) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md text-center">
          <h2 className="text-xl font-semibold">Despacho no seleccionado</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            No tenés un despacho activo asignado. Pedile a tu admin que te asigne
            a un despacho, o si ya lo hizo, recargá esta página después de unos segundos.
          </p>
        </div>
      </div>
    );
  }

  let me;
  try {
    me = await getMe(ctx);
  } catch (err) {
    if (err instanceof ApiError401) {
      redirect("/sign-in");
    }
    if (err instanceof ApiError403) {
      // El despacho cookie no corresponde al usuario actual; limpiamos y redirect.
      await setDespachoActivoAction("");
      redirect("/dashboard");
    }
    throw err;
  }

  return (
    <DespachoBootstrap despachoActivoId={me.despacho.id}>
      <AppShell me={me}>{children}</AppShell>
    </DespachoBootstrap>
  );
}
