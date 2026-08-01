// ── Protected Route ──────────────────────────────────────────────────────────
// Wraps routes that require authentication.  Redirects to /login if the user
// is not signed in.  Shows a loading spinner while the session is being
// restored (avoids a flash of the login page on hard refresh).

import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute() {
    const { isAuthenticated, isLoading } = useAuth();

    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center bg-surface-50 dark:bg-surface-dark-950">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary-400 dark:border-primary-300 border-t-primary-500" />
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return <Outlet />;
}
