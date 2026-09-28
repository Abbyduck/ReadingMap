import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src")
    }
  },
  server: {
    port: 53180,
    proxy: {
      "/api": "http://127.0.0.1:8010",
      "/django-admin": "http://127.0.0.1:8010",
      "/static": "http://127.0.0.1:8010",
      "/media": "http://127.0.0.1:8010",
      "/booklist-assets": "http://127.0.0.1:8010"
    }
  }
});
