/**
 * Resolver de `ApiContext` en server (RSC + Server Actions).
 *
 * NO importar desde Client Components — tira un error en build.
 *
 * Dos modos:
 * - Clerk normal: lee token con `auth()` + cookie del despacho.
 * - Dev mode (`NEXT_PUBLIC_DEV_MODE=true`): lee solo cookies, no toca Clerk.
 *   Esto evita errores en runtime cuando el middleware Clerk no está activo.
 */
import "server-only";

import { cookies } from "next/headers";

import type { ApiContext } from "./context";

/** Nombre de la cookie que guarda el despacho activo. */
export const DESPACHO_COOKIE = "praxis_despacho_id";

/**
 * Cookie de modo dev: si está seteada, su valor se usa como Bearer token
 * en lugar de pedírselo a Clerk. Solo en `NEXT_PUBLIC_DEV_MODE=true`.
 */
export const DEV_TOKEN_COOKIE = "praxis_dev_token";

const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

/**
 * Lee token + despacho_id desde cookies + (si no es dev) Clerk.
 *
 * Si el usuario no está autenticado, devuelve `{ token: null, despachoId: ... }`
 * — el caller decide qué hacer (típicamente redirect a /sign-in o /dev-login).
 */
export async function getApiContextServer(): Promise<ApiContext> {
  const cookieStore = await cookies();
  const despachoId = cookieStore.get(DESPACHO_COOKIE)?.value ?? null;

  // Modo dev: SOLO mira la cookie, nunca Clerk.
  if (isDevMode) {
    const devToken = cookieStore.get(DEV_TOKEN_COOKIE)?.value ?? null;
    return { token: devToken, despachoId };
  }

  // Modo Clerk: dynamic import para no traer @clerk/nextjs/server en bundles
  // que no lo necesiten.
  const { auth } = await import("@clerk/nextjs/server");
  const { getToken } = await auth();
  const token = (await getToken()) ?? null;
  return { token, despachoId };
}
