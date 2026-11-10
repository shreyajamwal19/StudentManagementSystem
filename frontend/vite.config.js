import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server proxies API calls to the FastAPI backend (default http://127.0.0.1:8000), so no CORS setup is needed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": process.env.VITE_API || "http://127.0.0.1:8000", "/auth": process.env.VITE_API || "http://127.0.0.1:8000" } },
  test: { environment: "jsdom", globals: true },
});
