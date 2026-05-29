/**
 * Server Actions para gestionar la cookie del despacho activo.
 *
 * La cookie se llama `DESPACHO_COOKIE` (en `lib/api/context-server`). HttpOnly,
 * SameSite=Lax, accesible por SSR/RSC para evitar flash de contenido equivocado.
 */
"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { DESPACHO_COOKIE, DEV_TOKEN_COOKIE } from "@/lib/api/context-server";

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

/**
 * Modo dev: setea ambas cookies (token fake + despacho) y redirige
 * al dashboard. Solo funciona si NODE_ENV !== "production".
 */
export async function devLoginAction(formData: FormData) {
  if (process.env.NODE_ENV === "production") {
    throw new Error("devLoginAction está deshabilitado en producción");
  }
  const clerkId = String(formData.get("clerkId") ?? "").trim();
  const despachoId = String(formData.get("despachoId") ?? "").trim();
  if (!clerkId || !despachoId) {
    throw new Error("Faltan clerkId o despachoId");
  }

  const cookieStore = await cookies();
  // En modo dev NO marcamos HttpOnly porque el JS del cliente necesita
  // leer la cookie para enviarla como Bearer en mutations. Inseguro en
  // general; aceptable como atajo solo-dev.
  cookieStore.set(DEV_TOKEN_COOKIE, `dev:${clerkId}`, {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24, // 1 día.
  });
  cookieStore.set(DESPACHO_COOKIE, despachoId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  redirect("/dashboard");
}

/** Modo dev: limpia las cookies y redirige a /dev-login. */
export async function devLogoutAction() {
  const cookieStore = await cookies();
  cookieStore.delete(DEV_TOKEN_COOKIE);
  cookieStore.delete(DESPACHO_COOKIE);
  redirect("/dev-login");
}
