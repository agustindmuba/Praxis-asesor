/**
 * Hidrata el store Zustand desde el valor que vino del server.
 *
 * Necesario porque Zustand vive en cliente y arranca con `null`. Si no
 * sincronizamos, el primer render del cliente envía requests sin
 * `X-Despacho-Id` y rompe.
 */
"use client";

import { useEffect } from "react";

import { useDespachoStore } from "@/stores/despacho";

interface Props {
  despachoActivoId: string;
  children: React.ReactNode;
}

export function DespachoBootstrap({ despachoActivoId, children }: Props) {
  const setDespachoActivoId = useDespachoStore((s) => s.setDespachoActivoId);

  useEffect(() => {
    setDespachoActivoId(despachoActivoId);
  }, [despachoActivoId, setDespachoActivoId]);

  return <>{children}</>;
}
