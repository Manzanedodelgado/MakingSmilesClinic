import type { Config } from "tailwindcss";

/**
 * Design system MakingSmiles — paleta heredada del estándar SmilePro, pero
 * declarada aquí como fuente única. Los tokens van como variables semánticas;
 * los componentes Clinical* y config-styles consumen estas clases.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#1500A0", // azul corporativo
          navy: "#013B82",
          cyan: "#1CA0D1",
          teal: "#2DD9C3",
          tealDark: "#20BEAB",
        },
        line: "#e5e7eb",
        surface: "#f8fbfd",
        muted: "#7f8c8d",
        // Semánticos de la paleta vetada (sin rojo/naranja/verde):
        // ok = turquesa · warn = violeta · err = magenta · info = azul (espejo de globals.css)
        ok: { DEFAULT: "#20BEAB", strong: "#0F8C7D", soft: "#E6F7F4", line: "#9FE6DB" },
        warn: { DEFAULT: "#7C3AED", strong: "#6D28D9", soft: "#EDE8FD", line: "#C4B5FD" },
        err: { DEFAULT: "#C026D3", strong: "#A21CAF", soft: "#FBEAFD", line: "#E9A8F5" },
        info: { DEFAULT: "#21A2E5", strong: "#073D8D", soft: "#E7F6FD", line: "#BFE4F7" },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
