import type { NextConfig } from "next";

const config: NextConfig = {
  // React 19 strict mode.
  reactStrictMode: true,

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
