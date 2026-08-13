import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// `.env` lives at the repository root (envDir below), and this config file runs
// in Node before Vite populates the client env, so the value has to be loaded
// explicitly -- reading process.env here would silently see nothing.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  return {
    plugins: [react()],
    envDir: "..",
    server: {
      port: 5173,
      proxy: {
        "/api": {
          // Defaults to the documented backend port. Override with
          // VITE_API_PROXY_TARGET in .env when the backend runs elsewhere --
          // for example when a crash leaves 8000 held by a stale socket.
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 4173,
    },
  };
});
