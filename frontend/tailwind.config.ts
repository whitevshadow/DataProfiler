import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"] ,
  theme: {
    extend: {
      colors: {
        canvas: "#0f172a",
        surface: "#111827",
        panel: "#0b1220",
        accent: "#22d3ee",
        edge: "#22c55e",
        pk: "#fbbf24",
        fk: "#60a5fa",
        danger: "#f87171",
        lcil: "#a855f7",
      },
      fontFamily: {
        display: ["Sora", "sans-serif"],
        body: ["Space Grotesk", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(34, 211, 238, 0.15)",
      },
    },
  },
  plugins: [],
} satisfies Config;
