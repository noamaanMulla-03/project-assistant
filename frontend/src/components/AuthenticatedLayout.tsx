// ── Authenticated Layout ─────────────────────────────────────────────────────
// Wraps all protected pages with the Sidebar.  The main content area margin-left
// is spring-animated in sync with the sidebar's expand / collapse toggle.
// Uses <Outlet /> from react-router-dom for nested child routes.

import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { motion, useMotionValue, useSpring } from "motion/react";
import Sidebar from "./Sidebar";

// ── Constants (must match Sidebar.tsx) ───────────────────────────────────────

const COLLAPSED_W = 64;
const EXPANDED_W = 256;
const STORAGE_KEY = "project-assistant-sidebar-collapsed";

export default function AuthenticatedLayout() {
    // ── Collapse state (persisted to localStorage) ────────────────────────
    const [collapsed, setCollapsed] = useState(() => {
        try {
            return localStorage.getItem(STORAGE_KEY) === "true";
        } catch {
            return false;
        }
    });

    const toggleCollapsed = useCallback(() => {
        setCollapsed((prev) => {
            const next = !prev;
            try {
                localStorage.setItem(STORAGE_KEY, String(next));
            } catch { /* noop */ }
            return next;
        });
    }, []);

    // ── Spring-animated margin-left for the main content ─────────────────
    const mlMotion = useMotionValue(collapsed ? COLLAPSED_W : EXPANDED_W);
    const springML = useSpring(mlMotion, {
        stiffness: 300,
        damping: 26,
    });

    useEffect(() => {
        mlMotion.set(collapsed ? COLLAPSED_W : EXPANDED_W);
    }, [collapsed, mlMotion]);

    return (
        <div className="flex min-h-screen bg-surface-50 dark:bg-surface-dark-950">
            {/* Sidebar: fixed position, sits on the left */}
            <Sidebar collapsed={collapsed} onToggle={toggleCollapsed} />

            {/* Main content area: margin-left animates in sync with sidebar */}
            <motion.main
                style={{ marginLeft: springML }}
                className="min-h-screen flex-1"
            >
                <Outlet />
            </motion.main>
        </div>
    );
}
