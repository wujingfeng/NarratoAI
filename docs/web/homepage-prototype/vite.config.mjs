import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    port: 5100,
    strictPort: true,
    allowedHosts: ["terminal.local", "w.nps.byai.top"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
    proxy: {
    "/api": {
      target: "http://127.0.0.1:8001",
      changeOrigin: true,
    },
},
  },
  plugins: [react()],
});
