import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build is written into the Python package and committed, so deployment needs Python only.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../doc_engine/static", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8100", changeOrigin: true } } },
});
