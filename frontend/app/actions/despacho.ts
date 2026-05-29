/**
 * Server Actions para gestionar la cookie del despacho activo.
 *
 * La cookie se llama `DESPACHO_COOKIE` (en `lib/api/context-server`). HttpOnly,
 * SameSite=Lax, accesible por SSR/RSC para evitar flash de contenido equivocado.
 */
"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";

import { DESPACHO_COOKIE } from "@/lib/api/context-server";

export async function setDespachoActivoAction(despachoId: string) {
  const cookieStore = await cookies();
  cookieStore.set(DESPACHO_COOKIE, despachoId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 días.
    secure: process.env.NODE_ENV === "production",
  });
  // Invalida cualquier cache de RSC que dependa del despacho.
  revalidatePath("/", "layout");
}

export async function clearDespachoCookieAction() {
  const cookieStore = await cookies();
  cookieStore.delete(DESPACHO_COOKIE);
  revalidatePath("/", "layout");
}
