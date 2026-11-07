import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В разработке API проксируется на локальный backend, как это делает nginx в Docker.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/admin/v1": "http://localhost:8000" } },
});
