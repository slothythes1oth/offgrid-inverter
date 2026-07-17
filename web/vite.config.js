import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend so the phone hits one origin.
// Build output goes to web/dist, which the backend serves in production.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // expose on the LAN so an iPhone can reach the dev server
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
