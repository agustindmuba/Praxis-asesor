/**
 * Root layout — envuelve toda la app.
 *
 * - `<ClerkProvider>` para que `useAuth` / `auth()` funcionen.
 * - `<QueryProvider>` para TanStack Query.
 * - Tipografías Praxis: Inter (cuerpo) + Space Grotesk (títulos).
 */
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Inter, Space_Grotesk } from "next/font/google";

import { QueryProvider } from "@/components/providers/query-provider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

/**
 * Modo dev: si la variable NEXT_PUBLIC_DEV_MODE está en "true", no
 * montamos ClerkProvider. Esto evita que Clerk haga handshakes contra
 * el dominio fake del publishable key dummy.
 */
const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

/**
 * Tipografías Praxis (feat/33 — manual de marca):
 * - Inter como cuerpo (sustituto web de Aaux Next).
 * - Space Grotesk para títulos (sustituto web de PP Radio Grotesk Black).
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: {
    default: "Praxis Asesor",
    template: "%s · Praxis Asesor",
  },
  description:
    "Decisiones estratégicas basadas en datos. Sistema operativo del despacho parlamentario.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const body = (
    <html lang="es" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${spaceGrotesk.variable} font-sans antialiased`}
      >
        <QueryProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </QueryProvider>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );

  // En modo dev, salteamos ClerkProvider para no disparar handshakes
  // contra el dominio fake del publishable key.
  if (isDevMode) {
    return body;
  }

  return (
    <ClerkProvider appearance={{ variables: { colorPrimary: "#2A3D75" } }}>
      {body}
    </ClerkProvider>
  );
}
