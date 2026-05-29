/**
 * Middleware Clerk. Cualquier ruta que NO matchee `isPublic` exige sesión.
 *
 * El matcher excluye archivos estáticos y `_next/`. Si la sesión falta o
 * expiró, Clerk redirige automáticamente a `/sign-in` con `?redirect_url=...`.
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublic = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  // Healthcheck para que probes externos no pidan auth.
  "/api/health",
]);

export default clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Excluye archivos con extensión (imágenes, fuentes) y _next.
    "/((?!_next|.*\\..*).*)",
    // Pero incluye rutas /api/ con auth.
    "/(api|trpc)(.*)",
  ],
};
