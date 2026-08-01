// ── Theme Toggle ─────────────────────────────────────────────────────────────
// A pill-shaped button that switches between light (sun) and dark (moon) mode.
// Uses the ThemeContext — place it anywhere in the component tree.

import { useTheme } from "../context/ThemeContext";

export default function ThemeToggle() {
    const { theme, toggle } = useTheme();

    return (
        <button
            onClick={toggle}
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            className="relative inline-flex h-8 w-14 items-center rounded-full border border-surface-200 bg-surface-100 p-0.5 transition-colors hover:border-surface-300 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:hover:border-surface-dark-300"
        >
            {/* Sliding pill */}
            <span
                className={`inline-flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm transition-transform duration-200 dark:bg-surface-dark-100 ${theme === "dark" ? "translate-x-6" : "translate-x-0"
                    }`}
            >
                {/* Sun icon (shown in light mode) */}
                <svg
                    className={`h-3.5 w-3.5 text-amber-500 transition-opacity duration-200 ${theme === "dark" ? "opacity-0 absolute" : "opacity-100"
                        }`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                    <path strokeLinecap="round" strokeLinejoin="round"
                        d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                    />
                </svg>
                {/* Moon icon (shown in dark mode) */}
                <svg
                    className={`h-3.5 w-3.5 text-primary-500 transition-opacity duration-200 ${theme === "light" ? "opacity-0 absolute" : "opacity-100"
                        }`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                    <path strokeLinecap="round" strokeLinejoin="round"
                        d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                    />
                </svg>
            </span>
        </button>
    );
}
