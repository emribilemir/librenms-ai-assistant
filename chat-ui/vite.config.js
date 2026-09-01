import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/ai-api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ai-api/, ""),
      },
    },
  },
});
