// ── Register Page ────────────────────────────────────────────────────────────
// Registration form with full name, email, password, and confirm password.

import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { BackgroundBeams } from "../components/ui/background-beams";
import { GlowingEffectCard } from "../components/ui/glowing-effect";
import { extractErrorMessage } from "../components/utils";
import { useAuth } from "../context/AuthContext";

export default function Register() {
    const { register } = useAuth();
    const navigate = useNavigate();

    const [fullName, setFullName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError(null);

        // Client-side password match check
        if (password !== confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setIsSubmitting(true);

        try {
            await register(email, password, fullName);
            setSuccess(true);
        } catch (err: unknown) {
            setError(extractErrorMessage(err, "Registration failed. Please try again."));
        } finally {
            setIsSubmitting(false);
        }
    };

    // Success state — show confirmation with a link to login
    if (success) {
        return (
            <BackgroundBeams>
                <div className="flex min-h-screen items-center justify-center px-4 py-12">
                    {/* Theme toggle — fixed top-right */}
                    <div className="fixed right-4 top-4 z-50">
                        <ThemeToggle />
                    </div>
                    <GlowingEffectCard className="w-full max-w-md">
                        <div className="rounded-2xl bg-zinc-900/95 p-8 text-center backdrop-blur-sm">
                            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-green-500/20">
                                <svg
                                    className="h-7 w-7 text-green-400"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2}
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M5 13l4 4L19 7"
                                    />
                                </svg>
                            </div>
                            <h1 className="text-xl font-semibold text-surface-800 dark:text-surface-dark-100">
                                Registration successful!
                            </h1>
                            <p className="mt-2 text-sm text-surface-700 dark:text-surface-dark-300">
                                Your account has been created.  You can now sign in.
                            </p>
                            <button
                                onClick={() => navigate("/login")}
                                className="mt-6 w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-500"
                            >
                                Go to Sign in
                            </button>
                        </div>
                    </GlowingEffectCard>
                </div>
            </BackgroundBeams>
        );
    }

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
                                Create your account
                            </h1>
                            <p className="mt-2 text-sm text-surface-700 dark:text-surface-dark-300">
                                Get started with Project Assistant
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

                            {/* Full name */}
                            <div>
                                <label
                                    htmlFor="fullName"
                                    className="mb-1.5 block text-sm font-medium text-surface-800 dark:text-surface-dark-100"
                                >
                                    Full name
                                </label>
                                <input
                                    id="fullName"
                                    type="text"
                                    required
                                    autoComplete="name"
                                    value={fullName}
                                    onChange={(e) => setFullName(e.target.value)}
                                    placeholder="Jane Smith"
                                    className="w-full rounded-lg border border-surface-300 bg-surface-50 dark:border-surface-dark-700 dark:bg-surface-dark-800 px-4 py-2.5 text-sm text-surface-800 dark:text-surface-dark-100 placeholder-surface-700 dark:placeholder-surface-dark-300 transition-colors focus:border-primary-400 focus:bg-white dark:focus:bg-surface-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-200"
                                />
                            </div>

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
                                    autoComplete="new-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Min. 8 characters"
                                    className="w-full rounded-lg border border-surface-300 bg-surface-50 dark:border-surface-dark-700 dark:bg-surface-dark-800 px-4 py-2.5 text-sm text-surface-800 dark:text-surface-dark-100 placeholder-surface-700 dark:placeholder-surface-dark-300 transition-colors focus:border-primary-400 focus:bg-white dark:focus:bg-surface-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-200"
                                />
                            </div>

                            {/* Confirm password */}
                            <div>
                                <label
                                    htmlFor="confirmPassword"
                                    className="mb-1.5 block text-sm font-medium text-surface-800 dark:text-surface-dark-100"
                                >
                                    Confirm password
                                </label>
                                <input
                                    id="confirmPassword"
                                    type="password"
                                    required
                                    autoComplete="new-password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder="Re-enter your password"
                                    className="w-full rounded-lg border border-surface-300 bg-surface-50 dark:border-surface-dark-700 dark:bg-surface-dark-800 px-4 py-2.5 text-sm text-surface-800 dark:text-surface-dark-100 placeholder-surface-700 dark:placeholder-surface-dark-300 transition-colors focus:border-primary-400 focus:bg-white dark:focus:bg-surface-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-200"
                                />
                            </div>

                            {/* Submit */}
                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                {isSubmitting ? "Creating account..." : "Create account"}
                            </button>
                        </form>

                        {/* Footer */}
                        <p className="mt-6 text-center text-sm text-surface-800 dark:text-surface-dark-1000">
                            Already have an account?{" "}
                            <Link
                                to="/login"
                                className="font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300 transition-colors"
                            >
                                Sign in
                            </Link>
                        </p>
                    </div>
                </GlowingEffectCard>
            </div>
        </BackgroundBeams>
    );
}
