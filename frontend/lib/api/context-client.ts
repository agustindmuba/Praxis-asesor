/**
 * Hook para resolver `ApiContext` en Client Components.
 *
 * Lee el token de Clerk (`useAuth().getToken`) y el despacho activo del
 * store de Zustand (`useDespachoStore`).
 */
"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

import { useDespachoStore } from "@/stores/despacho";

import type { ApiContext } from "./context";

/**
 * Devuelve una función que produce el `ApiContext` actual.
 *
 * Devolvemos una función (no el objeto directamente) porque `getToken()` es
 * async y queremos refrescar el JWT en cada call.
 */
export function useApiContext(): () => Promise<ApiContext> {
  const { getToken } = useAuth();
  const despachoId = useDespachoStore((s) => s.despachoActivoId);

  return useCallback(async () => {
    const token = (await getToken()) ?? null;
    return { token, despachoId };
  }, [getToken, despachoId]);
}
