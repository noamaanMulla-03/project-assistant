import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// https://vite.dev/config/
export default defineConfig({
	plugins: [react()],
	resolve: {
		alias: {
			"@": resolve(__dirname, "src"),
		},
	},
	// Proxy API calls to the FastAPI backend during development
	server: {
		host: true, // Listen on all interfaces (needed for Docker)
		port: 5173,
		// Proxy auth & API routes to the FastAPI backend (Docker service name)
		proxy: {
			"/auth": {
				target: "http://backend:8000",
				changeOrigin: true,
			},
			"/knowledge": {
				target: "http://backend:8000",
				changeOrigin: true,
			},
			"/projects": {
				target: "http://backend:8000",
				changeOrigin: true,
			},
			"/health": {
				target: "http://backend:8000",
				changeOrigin: true,
			},
		},
	},
});
