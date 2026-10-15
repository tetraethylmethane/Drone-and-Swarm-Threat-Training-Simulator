import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env.DRIKR_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@contracts": fileURLToPath(new URL("../../packages/contracts/schemas", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: ["..", "../../packages/contracts"] },
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // Keep the large 3D and charting libraries in their own lazily loaded chunks.
        manualChunks(id: string) {
          const path = id.replaceAll("\\", "/");
          if (path.includes("/node_modules/three/") || path.includes("/node_modules/@react-three/"))
            return "three";
          if (path.includes("/node_modules/echarts/") || path.includes("/node_modules/zrender/"))
            return "echarts";
          return undefined;
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
