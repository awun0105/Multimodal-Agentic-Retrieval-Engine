import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.AIC_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "")
      },
      "/media": {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
});
