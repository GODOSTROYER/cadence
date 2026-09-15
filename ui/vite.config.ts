import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type PluginOption } from "vite";

/**
 * Dev-only stand-in for the Vercel function's admin endpoints, used by `vite --mode static`.
 *
 * There is no admin session in local dev: `/api/admin/me` answers 404, which the UI reads as
 * "admin features unavailable, show everything". The admin datasets are served straight from
 * `../results/ui/<name>.json` (the export script's output) so the internal pages have data to show.
 * Nothing here is part of a build.
 */
function devAdminData(base: string): PluginOption {
  const dir = fileURLToPath(new URL("../results/ui/", import.meta.url));
  const allowed = new Set(["eval_summary", "failure_modes", "golden_merged", "decisions", "health"]);
  const prefix = `${base.replace(/\/$/, "")}/api/admin/`;
  return {
    name: "cadence-dev-admin-data",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        if (!url.startsWith(prefix)) return next();
        const rest = url.slice(prefix.length).split("?")[0] ?? "";
        res.setHeader("Content-Type", "application/json");
        if (rest === "me" || rest === "login" || rest === "logout") {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: "No admin session in local dev." }));
          return;
        }
        const name = rest.startsWith("data/") ? rest.slice(5) : "";
        const file = `${dir}${name}.json`;
        if (!allowed.has(name) || !existsSync(file)) {
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: `No dev dataset ${name || rest}. Run scripts/07_export_ui_data.py.` }));
          return;
        }
        res.end(readFileSync(file));
      });
    },
  };
}

/**
 * Vite configuration for the Cadence UI.
 *
 * - `VITE_BASE` sets the public base path (e.g. "/hiver-assignment/"); defaults to "/".
 * - In dev, `/api/*` is proxied to the FastAPI server on 127.0.0.1:8000 (CONTRACT.md §10).
 * - `--mode static` loads `.env.static`, which sets `VITE_STATIC=1` (reads public/data/*.json) and
 *   enables the dev admin-data stand-in above.
 * - `--mode vercel` loads `.env.vercel`: static data, live agent behind the function, sub-path base.
 */
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const base = process.env.VITE_BASE ?? env.VITE_BASE ?? "/";
  // Emit into dist/<base> so a host can serve the app at that sub-path with a plain filesystem lookup.
  const outDir = base === "/" ? "dist" : `dist${base.replace(/\/$/, "")}`;
  const plugins: PluginOption[] = [react(), tailwindcss()];
  if (command === "serve" && mode === "static") plugins.push(devAdminData(base));
  return {
    base,
    plugins,
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
