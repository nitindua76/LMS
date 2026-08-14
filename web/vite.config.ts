import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Comma-separated list of extra hostnames the Vite dev server will accept
// requests for, on top of "lms.local" — needed when teammates on the LAN
// browse via this machine's hostname/IP instead of lms.local (which only
// resolves on this machine via its own hosts-file entry). Without this,
// Vite returns "Blocked request. This host is not allowed" for any other
// Host header, independent of and prior to the API's own CORS_ORIGINS check.
const extraAllowedHosts = (process.env.VITE_ALLOWED_HOSTS || "")
  .split(",")
  .map((h) => h.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: ["lms.local", ...extraAllowedHosts],
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
