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
  // Modo dev: la página de login fake no debe pasar por Clerk.
  "/dev-login",
]);

/**
 * Si hay una cookie de dev (`praxis_dev_token`), saltamos Clerk
 * completamente. Eso permite que la página `(app)/layout.tsx` use el token
 * fake del backend sin que Clerk redirija.
 */
const isDevSession = (req: Request) =>
  process.env.NODE_ENV !== "production" &&
  req.headers.get("cookie")?.includes("praxis_dev_token=");

export default clerkMiddleware(async (auth, req) => {
  if (isPublic(req)) return;
  if (isDevSession(req as unknown as Request)) return;
  await auth.protect();
});

export const config = {
  matcher: [
    // Excluye archivos con extensión (imágenes, fuentes) y _next.
    "/((?!_next|.*\\..*).*)",
    // Pero incluye rutas /api/ con auth.
    "/(api|trpc)(.*)",
  ],
};
