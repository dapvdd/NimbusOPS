import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy target is configurable so the backend can run on any local port
// (default 8000). Example: API_PROXY_TARGET=http://127.0.0.1:8020 npm run dev
const proxyTarget = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
