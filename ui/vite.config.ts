import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

/**
 * Vite configuration for the Cadence UI.
 *
 * - `VITE_BASE` sets the public base path (e.g. "/cadence/" for GitHub Pages); defaults to "/".
 * - In dev, `/api/*` is proxied to the FastAPI server on 127.0.0.1:8000 (CONTRACT.md §10).
 * - `--mode static` loads `.env.static`, which sets `VITE_STATIC=1` (reads public/data/*.json).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const base = process.env.VITE_BASE ?? env.VITE_BASE ?? "/";
  // Emit into dist/<base> so a host can serve the app at that sub-path with a plain filesystem lookup.
  const outDir = base === "/" ? "dist" : `dist${base.replace(/\/$/, "")}`;
  return {
  base,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          motion: ["framer-motion"],
          charts: ["recharts"],
        },
      },
    },
  },
  };
});
