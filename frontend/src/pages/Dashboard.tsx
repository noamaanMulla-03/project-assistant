// ── Dashboard Page ───────────────────────────────────────────────────────────
// Simple protected page that confirms the auth flow works end-to-end.
// Displays the current user's profile and a logout button.

import { useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../context/AuthContext";
import { GlowingEffectCard } from "../components/ui/glowing-effect";

export default function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate("/login", { replace: true });
    };

    if (!user) return null; // Shouldn't happen (protected route), but satisfy TypeScript

    return (
        <div className="min-h-screen bg-surface-50 dark:bg-surface-dark-950 px-4 py-12">
            <div className="mx-auto max-w-2xl">
                {/* Header */}
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">Dashboard</h1>
                        <p className="mt-1 text-sm text-surface-700 dark:text-surface-dark-300">
                            Welcome back, {user.full_name}
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <ThemeToggle />
                        <button
                        onClick={handleLogout}
                        className="rounded-lg border border-surface-300 px-4 py-2 text-sm font-medium text-surface-700 dark:border-surface-dark-700 dark:text-surface-dark-300 transition-colors hover:border-surface-700 hover:bg-surface-100 dark:hover:border-surface-dark-200 dark:hover:bg-surface-dark-800"
                    >
                        Sign out
                    </button>
                    </div>
                </div>

                {/* User profile card */}
                <GlowingEffectCard>
                    <div className="rounded-2xl bg-white dark:bg-surface-dark-900 dark:shadow-black/20 p-6">
                        <h2 className="mb-4 text-lg font-medium text-surface-800 dark:text-surface-dark-100">
                            Your profile
                        </h2>
                        <dl className="space-y-3">
                            <div className="flex justify-between">
                                <dt className="text-sm text-surface-700 dark:text-surface-dark-300">User ID</dt>
                                <dd className="text-sm font-mono text-surface-800 dark:text-surface-dark-200">{user.id}</dd>
                            </div>
                            <div className="flex justify-between">
                                <dt className="text-sm text-surface-700 dark:text-surface-dark-300">Email</dt>
                                <dd className="text-sm text-surface-800 dark:text-surface-dark-100">{user.email}</dd>
                            </div>
                            <div className="flex justify-between">
                                <dt className="text-sm text-surface-700 dark:text-surface-dark-300">Full name</dt>
                                <dd className="text-sm text-surface-800 dark:text-surface-dark-100">{user.full_name}</dd>
                            </div>
                            <div className="flex justify-between">
                                <dt className="text-sm text-surface-700 dark:text-surface-dark-300">Member since</dt>
                                <dd className="text-sm text-surface-800 dark:text-surface-dark-100">
                                    {new Date(user.created_at).toLocaleDateString()}
                                </dd>
                            </div>
                        </dl>
                    </div>
                </GlowingEffectCard>

                {/* Placeholder for future project features */}
                <div className="mt-8 rounded-2xl border border-dashed border-surface-300 dark:border-surface-dark-700 px-6 py-12 text-center">
                    <p className="text-sm text-surface-700 dark:text-surface-dark-300">
                        Document-to-Action features will appear here.
                    </p>
                </div>
            </div>
        </div>
    );
}
