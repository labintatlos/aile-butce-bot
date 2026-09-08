import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Home Assistant Ingress sayfayi bir yol onekinin altinda sunar
  // (/api/hassio_ingress/<token>/). Mutlak yollar orada 404 verir, bu yuzden
  // tum varliklar goreli adreslenir.
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8099" },
  },
});
