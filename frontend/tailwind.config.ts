import type { Config } from "tailwindcss";

// ── Tailwind CSS Configuration ───────────────────────────────────────────────
// Custom theme extending the default palette with design tokens used by
// Aceternity UI components and the application's own design system.

export default {
	content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
	darkMode: "class", // Toggle via <html class="dark">
	theme: {
		extend: {
			// ── Typography — Inter (Anthropic / Claude brand typeface) ──────
			fontFamily: {
				sans: ['"Inter"', "system-ui", "-apple-system", "sans-serif"],
			},
			// ── Animation keyframes for Aceternity UI effects ──────────────────
			animation: {
				"glowing-effect":
					"glowing-effect 2s ease-in-out infinite alternate",
				"background-beams": "background-beams 8s linear infinite",
			},
			keyframes: {
				"glowing-effect": {
					"0%": { backgroundPosition: "0% 50%" },
					"50%": { backgroundPosition: "100% 50%" },
					"100%": { backgroundPosition: "0% 50%" },
				},
				"background-beams": {
					"0%": { transform: "translateY(0)" },
					"100%": { transform: "translateY(-100%)" },
				},
			},
			// ── Colours — blended light/dark palette ───────────────────────────
			colors: {
				// Soft indigo primary (lighter than the original blue)
				primary: {
					50: "#eef2ff",
					100: "#e0e7ff",
					200: "#c7d2fe",
					300: "#a5b4fc",
					400: "#818cf8",
					500: "#6366f1",
					600: "#4f46e5",
					700: "#4338ca",
					800: "#3730a3",
					900: "#312e81",
					950: "#1e1b4b",
				},
				// Warm neutral palette for blended light/dark surfaces
				surface: {
					50: "#fafaf9", // Page background
					100: "#f5f5f4", // Card surface
					200: "#e7e5e4", // Subtle borders / dividers
					300: "#d6d3d1", // Input borders
					700: "#44403c", // Muted text
					800: "#292524", // Headings, dark accent text
					900: "#1c1917", // Dark UI elements
					950: "#0c0a09", // Deepest dark (sparingly)
				},
				// Inverse warm palette for dark mode
				"surface-dark": {
					50: "#fafaf9", // Lightest accent on dark (rare)
					100: "#e7e5e4", // Headings on dark bg
					200: "#d6d3d1", // Secondary text
					300: "#a8a29e", // Muted text
					700: "#44403c", // Input borders
					800: "#292524", // Input / card bg
					900: "#1c1917", // Elevated card bg
					950: "#0c0a09", // Page background
				},
			},
		},
	},
	plugins: [],
} satisfies Config;
