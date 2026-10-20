import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "./",
  cacheDir: ".vite-cache",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      // The isolation probe is a second trusted page with its own strict CSP; it is only
      // ever loaded by `--riu-isolation-probe` and shares no module graph with the app shell.
      input: {
        index: path.resolve(__dirname, "index.html"),
        "riu-probe": path.resolve(__dirname, "riu-probe.html"),
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/.runtime/**", "**/.cache/**", "**/release/**", "**/dist-electron/**"],
    },
  },
});
