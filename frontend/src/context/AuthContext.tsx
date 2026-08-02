// ── Auth Context ─────────────────────────────────────────────────────────────
// Provides authentication state and actions (login, register, logout) to the
// entire component tree.
//
// Flow:
//   1. On mount → attempt silent refresh via ``/auth/refresh`` cookie
//   2. Login → POST /auth/login → store access token in-memory → set user
//   3. Register → POST /auth/register → redirect to login
//   4. Logout → POST /auth/logout → clear token + user state
//   5. API interceptor handles 401 auto-refresh (see api/client.ts)

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from "react";
import apiClient, { setAccessToken } from "../api/client";

// ── Types ────────────────────────────────────────────────────────────────────

interface User {
    id: string;
    email: string;
    full_name: string;
    created_at: string;
}

interface AuthState {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (email: string, password: string) => Promise<void>;
    register: (email: string, password: string, fullName: string) => Promise<void>;
    logout: () => Promise<void>;
}

// ── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthState | undefined>(undefined);

// ── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true); // True until initial refresh attempt completes

    // ── Silent refresh on mount ────────────────────────────────────────────
    useEffect(() => {
        // Abort flag prevents stale async results from overwriting state when
        // React StrictMode double-mounts (dev) or when the component unmounts
        // before the refresh completes. Without this, two concurrent refresh
        // calls race: the first blacklists the cookie, the second fails with
        // 401, and if it resolves last it logs the user out.
        let cancelled = false;

        const restoreSession = async () => {
            try {
                const { data } = await apiClient.post("/auth/refresh");
                if (cancelled) return;
                setAccessToken(data.access_token);
                // Fetch user profile with the fresh access token
                const { data: userData } = await apiClient.get("/auth/me");
                if (cancelled) return;
                setUser(userData);
            } catch {
                if (cancelled) return;
                // No valid session — user stays logged out
                setAccessToken(null);
                setUser(null);
            } finally {
                if (!cancelled) setIsLoading(false);
            }
        };

        restoreSession();

        // On cleanup (unmount or StrictMode re-run), mark as cancelled so the
        // first effect's pending promises don't clobber the second effect's state.
        return () => {
            cancelled = true;
        };
    }, []);

    // ── Listen for forced logout from the API interceptor ──────────────────
    useEffect(() => {
        const handleForceLogout = () => {
            setAccessToken(null);
            setUser(null);
        };
        window.addEventListener("auth:logout", handleForceLogout);
        return () => window.removeEventListener("auth:logout", handleForceLogout);
    }, []);

    // ── Actions ────────────────────────────────────────────────────────────

    const login = useCallback(async (email: string, password: string) => {
        const { data } = await apiClient.post("/auth/login", { email, password });
        setAccessToken(data.access_token);
        const { data: userData } = await apiClient.get("/auth/me");
        setUser(userData);
    }, []);

    const register = useCallback(
        async (email: string, password: string, fullName: string) => {
            await apiClient.post("/auth/register", {
                email,
                password,
                full_name: fullName,
            });
            // Registration does NOT auto-login — user must log in separately
        },
        [],
    );

    const logout = useCallback(async () => {
        try {
            await apiClient.post("/auth/logout");
        } catch {
            // Even if the request fails, clear local state
        }
        setAccessToken(null);
        setUser(null);
    }, []);

    // ── Memoised context value ─────────────────────────────────────────────

    const value = useMemo<AuthState>(
        () => ({
            user,
            isAuthenticated: user !== null,
            isLoading,
            login,
            register,
            logout,
        }),
        [user, isLoading, login, register, logout],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/** Access auth state and actions.  Must be used within an ``AuthProvider``. */
export function useAuth(): AuthState {
    const ctx = useContext(AuthContext);
    if (ctx === undefined) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return ctx;
}
