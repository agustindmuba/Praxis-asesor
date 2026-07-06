"use client";

/**
 * PwaRegister DESACTIVADO en feat-65 hot-fix.
 *
 * El service worker interceptaba fetches de Next.js RSC y causaba loop
 * infinito entre /sign-in y /dashboard. Hasta debuggear bien el SW,
 * este componente sólo se encarga de DESREGISTRAR cualquier SW previo
 * que haya quedado en navegadores de usuarios.
 *
 * Cuando volvamos a habilitar PWA, hay que hacer que el SW ignore
 * completamente rutas con `?_rsc=` y `/api/` y `/_next/data/`.
 */
import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;

    // Desregistrar cualquier SW que haya quedado registrado antes.
    void navigator.serviceWorker.getRegistrations().then((regs) => {
      regs.forEach((r) => void r.unregister());
    });
  }, []);

  return null;
}
