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
 * Lee token + despacho_id desde Clerk + cookies del request actual.
 *
 * Si el usuario no está autenticado, devuelve `{ token: null, despachoId: ... }`
 * — el caller decide qué hacer (típicamente redirect a /sign-in).
 */
export async function getApiContextServer(): Promise<ApiContext> {
  const { getToken } = await auth();
  const cookieStore = await cookies();
  const token = (await getToken()) ?? null;
  const despachoId = cookieStore.get(DESPACHO_COOKIE)?.value ?? null;
  return { token, despachoId };
}
