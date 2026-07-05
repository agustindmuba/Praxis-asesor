import type { NextConfig } from "next";

const config: NextConfig = {
  // React 19 strict mode.
  reactStrictMode: true,

  // Output standalone: el Dockerfile de prod (feat-65) copia solo el
  // .next/standalone al runtime en vez de node_modules completo.
  output: "standalone",

  // Warnings de ESLint no deben bloquear el build de producción (feat-65).
  // Los seguimos viendo en dev y en CI (backend-ci.yml chequea aparte).
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Errores de TypeScript tampoco bloquean prod build. El CI ya corre
  // `tsc --noEmit` como paso separado antes del deploy.
  typescript: {
    ignoreBuildErrors: true,
  },

  // Imágenes: dominios externos que vamos a permitir (Clerk avatares, etc).
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "img.clerk.com" },
      { protocol: "https", hostname: "images.clerk.dev" },
    ],
  },

  // Env vars que están disponibles en cliente. NEXT_PUBLIC_* lo son por default,
  // pero documentamos las que esperamos.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },

  // Aumentamos el tamaño máximo de body para que llegue lo razonable a Server Actions.
  experimental: {
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
};

export default config;
