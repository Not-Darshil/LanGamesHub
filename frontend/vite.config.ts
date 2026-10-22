import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, Vite serves the UI and proxies API/WebSocket traffic to the
// FastAPI backend. In production, FastAPI serves the built files from dist/.
const backend = process.env.LGH_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Everything is bundled locally; no CDN or remote assets at runtime.
    assetsInlineLimit: 0,
  },
});
