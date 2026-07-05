"use client";

/**
 * Registra el service worker de la PWA en el navegador.
 *
 * Sólo corre en cliente y sólo cuando `navigator.serviceWorker` existe
 * (Chrome / Edge / Safari 11.1+ / Firefox). Falla silencioso en
 * cualquier otro caso — la app sigue andando como web normal.
 *
 * El SW vive en `/sw.js` (public/) y hace lo mínimo para que Chrome
 * dispare el prompt "Añadir a pantalla de inicio". Ver `public/sw.js`.
 */
import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    // En dev el turbopack refresca el bundle constantemente; el SW
    // cachearía HMR mangled y rompería HMR. Sólo registramos en prod.
    if (process.env.NODE_ENV !== "production") return;

    const controller = new AbortController();
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => {
        // Registro falló (extensión bloqueando, storage lleno, etc).
        // No hay nada útil que hacer — la app funciona sin SW.
      });
    return () => controller.abort();
  }, []);

  return null;
}
