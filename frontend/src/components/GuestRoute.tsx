// ── Guest Route ──────────────────────────────────────────────────────────────
// Wraps routes that should only be accessible to unauthenticated users
// (login, register).  Redirects to /dashboard if already signed in.

import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function GuestRoute() {
    const { isAuthenticated, isLoading } = useAuth();

    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center bg-surface-50 dark:bg-surface-dark-950">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary-400 dark:border-primary-300 border-t-primary-500" />
            </div>
        );
    }

    if (isAuthenticated) {
        return <Navigate to="/dashboard" replace />;
    }

    return <Outlet />;
}
