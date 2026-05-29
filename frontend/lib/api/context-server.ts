/**
 * Resolver de `ApiContext` en server (RSC + Server Actions).
 *
 * NO importar desde Client Components — tira un error en build.
 */
import "server-only";

import { auth } from "@clerk/nextjs/server";
import { cookies } from "next/headers";

import type { ApiContext } from "./context";

/** Nombre de la cookie que guarda el despacho activo. */
export const DESPACHO_COOKIE = "praxis_despacho_id";

/**
 * Cookie de modo dev: si está seteada, su valor se usa como Bearer token
 * en lugar de pedírselo a Clerk. SOLO en `NODE_ENV !== "production"`.
 * Se popula desde la página /dev-login.
 */
export const DEV_TOKEN_COOKIE = "praxis_dev_token";

/**
 * Lee token + despacho_id desde Clerk + cookies del request actual.
 *
 * Prioridad del token:
 *   1. Cookie `praxis_dev_token` si NODE_ENV !== "production".
 *   2. Token JWT de Clerk vía `auth()`.
 *
 * Si el usuario no está autenticado, devuelve `{ token: null, despachoId: ... }`
 * — el caller decide qué hacer (típicamente redirect a /sign-in).
 */
export async function getApiContextServer(): Promise<ApiContext> {
  const cookieStore = await cookies();
  const despachoId = cookieStore.get(DESPACHO_COOKIE)?.value ?? null;

  // Modo dev: si hay cookie, usamos ese token directo.
  if (process.env.NODE_ENV !== "production") {
    const devToken = cookieStore.get(DEV_TOKEN_COOKIE)?.value;
    if (devToken) {
      return { token: devToken, despachoId };
    }
  }

  // Modo Clerk normal.
  const { getToken } = await auth();
  const token = (await getToken()) ?? null;
  return { token, despachoId };
}
