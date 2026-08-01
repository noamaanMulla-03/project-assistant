// ── Theme Context ─────────────────────────────────────────────────────────────
// Manages light / dark mode via the `dark` class on <html>.
// Persists selection to localStorage so it survives page refreshes.

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from "react";

// ── Types ────────────────────────────────────────────────────────────────────

type Theme = "light" | "dark";

interface ThemeState {
    theme: Theme;
    toggle: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const STORAGE_KEY = "project-assistant-theme";

function getStoredTheme(): Theme {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === "dark" || stored === "light") return stored;
    } catch { /* localStorage unavailable (SSR / incognito) */ }
    // Default to system preference, fallback to light
    if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return "dark";
    }
    return "light";
}

function applyTheme(theme: Theme): void {
    const root = document.documentElement;
    if (theme === "dark") {
        root.classList.add("dark");
    } else {
        root.classList.remove("dark");
    }
}

// ── Context ──────────────────────────────────────────────────────────────────

const ThemeContext = createContext<ThemeState | undefined>(undefined);

// ── Provider ─────────────────────────────────────────────────────────────────

export function ThemeProvider({ children }: { children: ReactNode }) {
    const [theme, setTheme] = useState<Theme>(getStoredTheme);

    // Apply the class on mount and whenever theme changes
    useEffect(() => {
        applyTheme(theme);
    }, [theme]);

    const toggle = useCallback(() => {
        setTheme((prev) => {
            const next: Theme = prev === "light" ? "dark" : "light";
            try { localStorage.setItem(STORAGE_KEY, next); } catch { /* noop */ }
            return next;
        });
    }, []);

    const value = useMemo<ThemeState>(() => ({ theme, toggle }), [theme, toggle]);

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useTheme(): ThemeState {
    const ctx = useContext(ThemeContext);
    if (ctx === undefined) {
        throw new Error("useTheme must be used within a ThemeProvider");
    }
    return ctx;
}
