// ── Dashboard Page ───────────────────────────────────────────────────────────
// Simple protected page that confirms the auth flow works end-to-end.
// Displays the current user's profile.  Theme toggle and logout are in the
// sidebar, not here.

import { useAuth } from "../context/AuthContext";
import { GlowingEffectCard } from "../components/ui/glowing-effect";

export default function Dashboard() {
    const { user } = useAuth();

    if (!user) return null; // Shouldn't happen (protected route), but satisfy TypeScript

    return (
        <div className="px-4 py-12">
            <div className="mx-auto max-w-2xl">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">
                        Dashboard
                    </h1>
                    <p className="mt-1 text-sm text-surface-700 dark:text-surface-dark-300">
                        Welcome back, {user.full_name}
                    </p>
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
            </div>
        </div>
    );
}
