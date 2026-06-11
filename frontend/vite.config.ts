import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base is read from VITE_API_BASE at build time (see .env.example).
// In dev, requests to /api are proxied to the local FastAPI server on :8080.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
