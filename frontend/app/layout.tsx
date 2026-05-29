/**
 * Root layout — envuelve toda la app.
 *
 * - `<ClerkProvider>` para que `useAuth` / `auth()` funcionen.
 * - `<QueryProvider>` para TanStack Query.
 * - Fuente Inter, lang="es", meta básico.
 */
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Inter } from "next/font/google";

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

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: {
    default: "Praxis Asesor",
    template: "%s · Praxis Asesor",
  },
  description: "Sistema operativo del despacho parlamentario.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const body = (
    <html lang="es" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
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
    <ClerkProvider appearance={{ variables: { colorPrimary: "#1e293b" } }}>
      {body}
    </ClerkProvider>
  );
}
