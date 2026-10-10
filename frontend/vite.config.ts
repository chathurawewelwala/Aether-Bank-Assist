import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4200,
    host: true,
    proxy: {
      // Only used if VITE_API_BASE=/api/v1. Default frontend talks to
      // http://localhost:8000 directly so SSE is not buffered.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
        timeout: 0,
        proxyTimeout: 0,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            const ct = proxyRes.headers["content-type"] || "";
            if (String(ct).includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
});
