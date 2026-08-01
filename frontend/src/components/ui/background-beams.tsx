// ── Background Beams ─────────────────────────────────────────────────────────
// Animated SVG beams that create a subtle, premium background effect.
// Rendered behind the main content on auth pages.

"use client";

import { type ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "../utils";

// ── Props ────────────────────────────────────────────────────────────────────

interface BackgroundBeamsProps {
    children: ReactNode;
    className?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

export function BackgroundBeams({ children, className }: BackgroundBeamsProps) {
    return (
        <div className={cn("relative min-h-screen overflow-hidden bg-surface-50 dark:bg-surface-dark-950", className)}>
            {/* Animated beam orbs — warm muted tones on light background */}
            <div className="pointer-events-none absolute inset-0">
                {/* Top-left orb — soft warm amber (light) / muted indigo (dark) */}
                <motion.div
                    animate={{
                        x: [0, 30, 0],
                        y: [0, -30, 0],
                        scale: [1, 1.1, 1],
                    }}
                    transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute -left-20 top-20 h-[400px] w-[400px] rounded-full bg-amber-200/40 blur-[100px] dark:bg-indigo-900/30"
                />
                {/* Bottom-right orb — soft indigo (light) / muted violet (dark) */}
                <motion.div
                    animate={{
                        x: [0, -30, 0],
                        y: [0, 30, 0],
                        scale: [1, 1.15, 1],
                    }}
                    transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute -bottom-20 -right-20 h-[500px] w-[500px] rounded-full bg-indigo-300/30 blur-[120px] dark:bg-violet-900/25"
                />
                {/* Center accent — soft rose (light) / muted pink (dark) */}
                <motion.div
                    animate={{
                        scale: [1, 1.2, 1],
                        opacity: [0.2, 0.4, 0.2],
                    }}
                    transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-200/30 blur-[100px] dark:bg-pink-900/20"
                />
            </div>

            {/* Content */}
            <div className="relative z-10">{children}</div>
        </div>
    );
}
