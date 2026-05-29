/**
 * Provider de TanStack Query, montado en el Root Layout.
 *
 * Defaults razonables para una app autenticada:
 * - `staleTime: 30s` para evitar refetch sobre cada navegación.
 * - `retry: 1` — los 401/403 NO se reintentan (manejan refresh + redirect).
 * - `refetchOnWindowFocus: true` solo en client, para que el dashboard se
 *   actualice cuando el usuario vuelve a la tab.
 */
"use client";

import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useState } from "react";

import { ApiError401, ApiError403 } from "@/lib/api/client";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: true,
            retry: (failureCount, error) => {
              if (error instanceof ApiError401 || error instanceof ApiError403) {
                return false;
              }
              return failureCount < 1;
            },
          },
          mutations: {
            retry: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
