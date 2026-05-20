import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname),
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main:  resolve(__dirname, "index.html"),
        fkrte: resolve(__dirname, "fkrte.html"),
        dbml:  resolve(__dirname, "dbml.html"),
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:5500",
      "/ws": {
        target: "ws://127.0.0.1:5500",
        ws: true,
      },
    },
  },
});
