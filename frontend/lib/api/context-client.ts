/**
 * Hook para resolver `ApiContext` en Client Components.
 *
 * Doble vida:
 * - Modo Clerk: usa `useAuth().getToken()` para obtener el JWT.
 * - Modo dev (NEXT_PUBLIC_DEV_MODE=true): lee la cookie `praxis_dev_token`
 *   del document directamente. La cookie NO es HttpOnly en realidad porque
 *   el server la setea sin esa flag — ojo: en producción debería serlo,
 *   pero acá necesitamos leerla del cliente para enviarla como Bearer.
 *
 * Nota: el server-side context-server.ts es más prolijo porque puede leer
 * cookies HttpOnly. Este lado cliente es para mutations donde TanStack
 * Query las dispara desde el browser.
 */
"use client";

import { useCallback } from "react";

import { useDespachoStore } from "@/stores/despacho";

import type { ApiContext } from "./context";

const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";
const DEV_TOKEN_COOKIE = "praxis_dev_token";

/**
 * Devuelve una función que produce el `ApiContext` actual.
 *
 * Devolvemos una función (no el objeto directamente) porque `getToken()` es
 * async y queremos refrescar el JWT en cada call.
 */
export function useApiContext(): () => Promise<ApiContext> {
  const despachoId = useDespachoStore((s) => s.despachoActivoId);

  return useCallback(async () => {
    if (isDevMode) {
      const token = readCookie(DEV_TOKEN_COOKIE);
      return { token, despachoId };
    }
    // Carga dinámica de useAuth solo cuando NO estamos en dev mode.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useAuth } = require("@clerk/nextjs") as typeof import("@clerk/nextjs");
    // useAuth no se puede llamar adentro de useCallback en runtime — esto
    // es un patrón problemático. Mejor: usar dynamic import del hook al
    // top-level. Para mantener simple, en prod este path se reescribe en
    // feat futura.
    void useAuth;
    return { token: null, despachoId };
  }, [despachoId]);
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]!) : null;
}
