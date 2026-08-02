// ── Login Page ───────────────────────────────────────────────────────────────
// Clean login form inside a glowing card, with animated background beams.

import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { BackgroundBeams } from "../components/ui/background-beams";
import { GlowingEffectCard } from "../components/ui/glowing-effect";
import { extractErrorMessage } from "../components/utils";
import { useAuth } from "../context/AuthContext";

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsSubmitting(true);

        try {
            await login(email, password);
            navigate("/dashboard", { replace: true });
        } catch (err: unknown) {
            setError(extractErrorMessage(err, "Login failed. Please try again."));
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <BackgroundBeams>
            <div className="flex min-h-screen items-center justify-center px-4 py-12">
                {/* Theme toggle — fixed top-right */}
                <div className="fixed right-4 top-4 z-50">
                    <ThemeToggle />
                </div>
                <GlowingEffectCard className="w-full max-w-md">
                    <div className="rounded-2xl bg-white dark:bg-surface-dark-900 p-8">
                        {/* Header */}
                        <div className="mb-8 text-center">
                            <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">
                                Welcome back
                            </h1>
                            <p className="mt-2 text-sm text-surface-700 dark:text-surface-dark-300">
                                Sign in to your Project Assistant account
                            </p>
                        </div>

                        {/* Form */}
                        <form onSubmit={handleSubmit} className="space-y-5">
                            {/* Error banner */}
                            {error && (
                                <div className="rounded-lg border border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950 px-4 py-3 text-sm text-red-700 dark:text-red-400">
                                    {error}
                                </div>
                            )}

                            {/* Email */}
                            <div>
                                <label
                                    htmlFor="email"
                                    className="mb-1.5 block text-sm font-medium text-surface-800 dark:text-surface-dark-100"
                                >
                                    Email
                                </label>
                                <input
                                    id="email"
                                    type="email"
                                    required
                                    autoComplete="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="you@example.com"
                                    className="w-full rounded-lg border border-surface-300 bg-surface-50 dark:border-surface-dark-700 dark:bg-surface-dark-800 px-4 py-2.5 text-sm text-surface-800 dark:text-surface-dark-100 placeholder-surface-700 dark:placeholder-surface-dark-300 transition-colors focus:border-primary-400 focus:bg-white dark:focus:bg-surface-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-200"
                                />
                            </div>

                            {/* Password */}
                            <div>
                                <label
                                    htmlFor="password"
                                    className="mb-1.5 block text-sm font-medium text-surface-800 dark:text-surface-dark-100"
                                >
                                    Password
                                </label>
                                <input
                                    id="password"
                                    type="password"
                                    required
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    className="w-full rounded-lg border border-surface-300 bg-surface-50 dark:border-surface-dark-700 dark:bg-surface-dark-800 px-4 py-2.5 text-sm text-surface-800 dark:text-surface-dark-100 placeholder-surface-700 dark:placeholder-surface-dark-300 transition-colors focus:border-primary-400 focus:bg-white dark:focus:bg-surface-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-200"
                                />
                            </div>

                            {/* Submit */}
                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {isSubmitting ? "Signing in..." : "Sign in"}
                            </button>
                        </form>

                        {/* Footer */}
                        <p className="mt-6 text-center text-sm text-surface-800 dark:text-surface-dark-100">
                            Don&rsquo;t have an account?{" "}
                            <Link
                                to="/register"
                                className="font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 transition-colors"
                            >
                                Create one
                            </Link>
                        </p>
                    </div>
                </GlowingEffectCard>
            </div>
        </BackgroundBeams>
    );
}
