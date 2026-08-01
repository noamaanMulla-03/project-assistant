// ── Sidebar ───────────────────────────────────────────────────────────────────
// A glassmorphism floating sidebar with:
//   - Animated glowing border on the right edge
//   - Spring-animated expand / collapse toggle (persisted to localStorage)
//   - Nav items for Dashboard and Knowledge Base
//   - Bottom section with user avatar, theme toggle, and logout
//   - All icons are inline SVGs — no external icon library

import { useEffect, useRef, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { cn } from "../components/utils";

// ── Constants ────────────────────────────────────────────────────────────────

const COLLAPSED_W = 64;
const EXPANDED_W = 256;
const STORAGE_KEY = "project-assistant-sidebar-collapsed";

// ── Inline SVG Icons ─────────────────────────────────────────────────────────
// Each icon is a tiny function returning an SVG.  Provides tree-shakeable,
// dependency-free icons consistent with the rest of the codebase.

function DashboardIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
    );
}

function KnowledgeIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            <line x1="8" y1="7" x2="16" y2="7" />
            <line x1="8" y1="11" x2="14" y2="11" />
        </svg>
    );
}

function PlusCircleIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
        </svg>
    );
}

function SunIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
    );
}

function MoonIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
    );
}

function LogoutIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16,17 21,12 16,7" />
            <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
    );
}

function ChevronLeftIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <polyline points="15,18 9,12 15,6" />
        </svg>
    );
}

// ── Glowing Border ───────────────────────────────────────────────────────────
// A vertical animated bar on the right edge of the sidebar that pulses subtly.

function GlowingEdge() {
    return (
        <motion.div
            className="pointer-events-none absolute inset-y-0 right-0 w-px"
            animate={{ opacity: [0.2, 0.5, 0.2] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
            {/* Gradient beam that moves vertically */}
            <motion.div
                className="h-full w-full"
                style={{
                    background:
                        "linear-gradient(to bottom, transparent, rgba(99,102,241,0.6), rgba(139,92,246,0.6), transparent)",
                }}
                animate={{ y: ["-100%", "100%"] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            />
        </motion.div>
    );
}

// ── Nav Item ─────────────────────────────────────────────────────────────────

interface NavItemProps {
    to: string;
    label: string;
    icon: ReactNode;
    collapsed: boolean;
}

function NavItem({ to, label, icon, collapsed }: NavItemProps) {
    return (
        <NavLink
            to={to}
            className={({ isActive }) =>
                cn(
                    "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                    collapsed ? "justify-center px-0" : "",
                    isActive
                        ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300"
                        : "text-surface-600 hover:bg-surface-100 hover:text-surface-800 dark:text-surface-dark-300 dark:hover:bg-surface-dark-800 dark:hover:text-surface-dark-100",
                )
            }
            title={collapsed ? label : undefined}
        >
            <span className="shrink-0">{icon}</span>
            {/* Label: hidden when collapsed, animated opacity when expanded */}
            <motion.span
                className="truncate"
                animate={{
                    opacity: collapsed ? 0 : 1,
                    width: collapsed ? 0 : "auto",
                }}
                transition={{ duration: 0.2 }}
            >
                {label}
            </motion.span>
        </NavLink>
    );
}

// ── Props ────────────────────────────────────────────────────────────────────

interface SidebarProps {
    collapsed: boolean;
    onToggle: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Sidebar Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
    const { user, logout } = useAuth();
    const { theme, toggle: toggleTheme } = useTheme();
    const navigate = useNavigate();

    // ── Spring-animated width for smooth expand / collapse ────────────────
    const widthMotion = useMotionValue(collapsed ? COLLAPSED_W : EXPANDED_W);
    const springWidth = useSpring(widthMotion, {
        stiffness: 300,
        damping: 26,
    });

    // Keep the motion value in sync when collapsed state changes
    useEffect(() => {
        widthMotion.set(collapsed ? COLLAPSED_W : EXPANDED_W);
    }, [collapsed, widthMotion]);

    // ── Hover lift effect on the entire sidebar ───────────────────────────
    const containerRef = useRef<HTMLDivElement>(null);
    const mouseY = useMotionValue(0.5);
    const shadowOpacity = useTransform(mouseY, [0, 1], [0.08, 0.14]);

    // ── Logout handler ────────────────────────────────────────────────────
    const handleLogout = async () => {
        await logout();
        navigate("/login", { replace: true });
    };

    // ── User initials for avatar ──────────────────────────────────────────
    const initials = user?.full_name
        ?.split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2) ?? "?";

    // ── Format created_at for tooltip ─────────────────────────────────────
    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString()
        : "";

    return (
        <motion.aside
            ref={containerRef}
            style={{ width: springWidth }}
            onMouseMove={(e) => {
                if (!containerRef.current) return;
                const rect = containerRef.current.getBoundingClientRect();
                mouseY.set((e.clientY - rect.top) / rect.height);
            }}
            className={cn(
                "fixed inset-y-0 left-0 z-40 flex flex-col",
                // Glassmorphism backdrop
                "backdrop-blur-2xl",
                "border-r border-surface-200/50 dark:border-surface-dark-700/50",
                // Background with gradient
                "bg-white/70 dark:bg-surface-dark-900/70",
                // Shadow that shifts with mouse position for depth
                "shadow-2xl",
            )}
            initial={false}
            animate={{
                boxShadow: `0 0 40px rgba(99, 102, 241, ${collapsed ? 0.06 : 0.12})`,
            }}
            transition={{ duration: 0.4, ease: "easeInOut" }}
        >
            {/* Animated glowing edge on the right */}
            <GlowingEdge />

            {/* ════ Top Section: Toggle + Logo ════ */}
            <div
                className={cn(
                    "flex h-16 items-center border-b border-surface-200/50 dark:border-surface-dark-700/50 px-3",
                    collapsed ? "justify-center" : "justify-between",
                )}
            >
                {/* App name / logo — hidden when collapsed */}
                {!collapsed && (
                    <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.1 }}
                        className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-lg font-semibold text-transparent"
                    >
                        Assistant
                    </motion.span>
                )}

                {/* Collapse toggle button */}
                <button
                    onClick={onToggle}
                    className={cn(
                        "rounded-lg p-1.5 text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-700 dark:text-surface-dark-300 dark:hover:bg-surface-dark-800 dark:hover:text-surface-dark-100",
                    )}
                    aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                    <motion.span
                        animate={{ rotate: collapsed ? 180 : 0 }}
                        transition={{ duration: 0.35, ease: "easeInOut" }}
                        style={{ display: "block" }}
                    >
                        <ChevronLeftIcon />
                    </motion.span>
                </button>
            </div>

            {/* ════ Middle Section: Navigation ════ */}
            <nav
                className={cn(
                    "flex-1 space-y-1 overflow-y-auto py-4",
                    collapsed ? "px-2" : "px-3",
                )}
            >
                <NavItem
                    to="/dashboard"
                    label="Dashboard"
                    icon={<DashboardIcon />}
                    collapsed={collapsed}
                />
                <NavItem
                    to="/project/new"
                    label="New Project"
                    icon={<PlusCircleIcon />}
                    collapsed={collapsed}
                />
                <NavItem
                    to="/knowledge"
                    label="Knowledge Base"
                    icon={<KnowledgeIcon />}
                    collapsed={collapsed}
                />
            </nav>

            {/* ════ Bottom Section: User + Actions ════ */}
            <div
                className={cn(
                    "border-t border-surface-200/50 dark:border-surface-dark-700/50 p-3",
                    collapsed ? "px-2" : "",
                )}
            >
                {/* User avatar + name */}
                <div
                    className={cn(
                        "flex items-center gap-3",
                        collapsed ? "justify-center" : "",
                    )}
                    title={collapsed ? `${user?.full_name ?? ""} — member since ${memberSince}` : undefined}
                >
                    {/* Avatar circle */}
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 text-xs font-semibold text-white shadow-sm">
                        {initials}
                    </div>

                    {!collapsed && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="min-w-0 flex-1"
                        >
                            <p className="truncate text-sm font-medium text-surface-800 dark:text-surface-dark-100">
                                {user?.full_name}
                            </p>
                            <p className="truncate text-xs text-surface-500 dark:text-surface-dark-300">
                                {user?.email}
                            </p>
                        </motion.div>
                    )}
                </div>

                {/* Action buttons */}
                <div
                    className={cn(
                        "mt-3 flex w-full",
                        collapsed
                            ? "flex-col items-center"
                            : "flex-row",
                    )}
                >
                    {/* Theme toggle */}
                    <button
                        onClick={toggleTheme}
                        className={cn(
                            "rounded-lg text-surface-500 transition-colors hover:bg-surface-100 hover:text-surface-700 dark:text-surface-dark-300 dark:hover:bg-surface-dark-800 dark:hover:text-surface-dark-100",
                            collapsed
                                ? "p-2"
                                : "flex flex-1 items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs",
                        )}
                        title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
                        aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
                    >
                        {theme === "light" ? <MoonIcon /> : <SunIcon />}
                        {!collapsed && (
                            <span>{theme === "light" ? "Dark" : "Light"}</span>
                        )}
                    </button>

                    {/* Logout */}
                    <button
                        onClick={handleLogout}
                        className={cn(
                            "rounded-lg text-surface-500 transition-colors hover:bg-red-50 hover:text-red-600 dark:text-surface-dark-300 dark:hover:bg-red-950/30 dark:hover:text-red-400",
                            collapsed
                                ? "p-2"
                                : "flex flex-1 items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs",
                        )}
                        title="Sign out"
                        aria-label="Sign out"
                    >
                        <LogoutIcon />
                        {!collapsed && <span>Sign out</span>}
                    </button>
                </div>
            </div>
        </motion.aside>
    );
}
