// Tailwind 4 usa un plugin de PostCSS dedicado (@tailwindcss/postcss).
// No hay más tailwind.config.ts: la config va en CSS via @theme.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
