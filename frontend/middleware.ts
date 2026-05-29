/**
 * Middleware — dos modos:
 *
 * 1. Clerk normal: cualquier ruta no pública pide sesión Clerk.
 * 2. Dev mode (NEXT_PUBLIC_DEV_MODE=true): NO usa Clerk en absoluto.
 *    Si no hay cookie `praxis_dev_token`, redirige a /dev-login.
 *    Si la hay, deja pasar.
 *
 * El switch evita que Clerk haga handshakes contra el dominio fake del
 * publishable key dummy.
 */
import { NextResponse } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const DEV_TOKEN_COOKIE = "praxis_dev_token";
const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

const isPublic = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/dev-login",
  "/api/health",
]);

// Helper de rutas públicas para el modo dev (no usa Clerk).
function isPublicPath(pathname: string): boolean {
  return (
    pathname.startsWith("/dev-login") ||
    pathname.startsWith("/sign-in") ||
    pathname.startsWith("/sign-up") ||
    pathname.startsWith("/api/health")
  );
}

// Middleware "dev": no usa Clerk.
// Si te falta la cookie, te manda a /dev-login. Sino te deja pasar.
async function devMiddleware(req: Request) {
  const url = new URL(req.url);
  if (isPublicPath(url.pathname)) {
    return NextResponse.next();
  }
  const hasToken = req.headers.get("cookie")?.includes(`${DEV_TOKEN_COOKIE}=`);
  if (!hasToken) {
    url.pathname = "/dev-login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

// Middleware "clerk": el de siempre.
const clerkBased = clerkMiddleware(async (auth, req) => {
  if (isPublic(req)) return;
  await auth.protect();
});

export default isDevMode ? devMiddleware : clerkBased;

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
