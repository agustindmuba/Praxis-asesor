/**
 * Store del despacho activo del usuario.
 *
 * El UUID del despacho activo se persiste en cookie HttpOnly (escrita por
 * Server Action) para que SSR/RSC tenga acceso desde el primer render.
 * En cliente, este store es la fuente de verdad reactiva.
 *
 * El sync entre cookie y store sucede en el provider de la app (`(app)/layout.tsx`):
 * - El server lee la cookie y pasa el valor como prop.
 * - El provider hace `setDespachoActivoId(propValue)` al montar.
 */
"use client";

import { create } from "zustand";

interface DespachoStore {
  /** UUID del despacho actualmente activo. Null hasta que se hidrata. */
  despachoActivoId: string | null;
  setDespachoActivoId: (id: string | null) => void;
}

export const useDespachoStore = create<DespachoStore>((set) => ({
  despachoActivoId: null,
  setDespachoActivoId: (id) => set({ despachoActivoId: id }),
}));
