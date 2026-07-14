import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
const localProxySecret = process.env.MINGJIAN_LOCAL_PROXY_SECRET?.trim();

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": "/src" },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        headers: localProxySecret
          ? { "X-MingJian-Local-Proxy": localProxySecret }
          : undefined,
      },
    },
  },
});
