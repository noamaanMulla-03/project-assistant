// ── Glowing Effect Card ──────────────────────────────────────────────────────
// A container with an animated glowing border that follows the cursor.
// Inspired by Cursor's enterprise page and recreated for Aceternity UI.
//
// Usage:
//   <GlowingEffectCard>
//     <div>Your content here</div>
//   </GlowingEffectCard>

"use client";

import { type CSSProperties, type ReactNode, useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { cn } from "../utils";

// ── Props ────────────────────────────────────────────────────────────────────

interface GlowingEffectCardProps {
    children: ReactNode;
    className?: string;
    /** Width of the glowing border in pixels (default: 1) */
    borderWidth?: number;
    /** Colour variant: "default" (multicolor) or "white" */
    variant?: "default" | "white";
}

// ── Component ────────────────────────────────────────────────────────────────

export function GlowingEffectCard({
    children,
    className,
    borderWidth = 1,
    variant = "default",
}: GlowingEffectCardProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    // Track mouse position relative to the card
    const mouseX = useMotionValue(0);
    const mouseY = useMotionValue(0);

    // Smooth the mouse position for a nicer feel
    const springX = useSpring(mouseX, { stiffness: 150, damping: 20 });
    const springY = useSpring(mouseY, { stiffness: 150, damping: 20 });

    // Map cursor position to rotation (subtle 3D tilt)
    const rotateX = useTransform(springY, [0, 1], [3, -3]);
    const rotateY = useTransform(springX, [0, 1], [-3, 3]);

    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        mouseX.set((e.clientX - rect.left) / rect.width);
        mouseY.set((e.clientY - rect.top) / rect.height);
    };

    const handleMouseLeave = () => {
        mouseX.set(0.5);
        mouseY.set(0.5);
    };

    // Gradient colours based on variant — updated for blended theme
    const glowGradient =
        variant === "white"
            ? "conic-gradient(from 0deg at 50% 50%, rgba(99,102,241,0.6), transparent 60%, rgba(99,102,241,0.6))"
            : "conic-gradient(from 0deg at 50% 50%, #6366f1, #a78bfa, #f472b6, #6366f1)";

    return (
        <motion.div
            ref={containerRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={
                {
                    "--glow-gradient": glowGradient,
                    "--border-width": `${borderWidth}px`,
                    perspective: "800px",
                    rotateX,
                    rotateY,
                } as CSSProperties
            }
            className={cn("relative rounded-2xl", className)}
        >
            {/* Glowing border layer */}
            <div
                className="pointer-events-none absolute inset-0 rounded-2xl"
                style={{
                    background: "var(--glow-gradient)",
                    padding: "var(--border-width)",
                    WebkitMask:
                        "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
                    WebkitMaskComposite: "xor",
                    maskComposite: "exclude",
                }}
            />

            {/* Content container — light surface with shadow for blended theme */}
            <div className="relative rounded-2xl bg-white p-[var(--border-width)] shadow-2xl shadow-surface-950/5 dark:bg-surface-dark-900 dark:shadow-black/30">
                {children}
            </div>
        </motion.div>
    );
}
