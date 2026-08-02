// ── Project Stage Navbar ─────────────────────────────────────────────────────
// Horizontal step-indicator navigation shared by Draft, Analysis, and Review pages.
// Each stage is only clickable after its prerequisite is met:
//   - Draft:    always accessible
//   - Analysis: only after analysis_result exists
//   - Review:   only after analysis_result exists
//
// Uses consistent styling from the codebase (surface colours, indigo accent).

import { NavLink } from "react-router-dom";
import { cn } from "./utils";

// ── Stage Configuration ──────────────────────────────────────────────────────

interface Stage {
	key: string;
	label: string;
	path: (id: string) => string;
	// Whether this stage requires a completed analysis to be accessible
	requiresAnalysis: boolean;
}

const STAGES: Stage[] = [
	{ key: "draft", label: "Project Draft", path: (id) => `/project/${id}`, requiresAnalysis: false },
	{ key: "analysis", label: "Analysis", path: (id) => `/project/${id}/results`, requiresAnalysis: true },
	{ key: "review", label: "Review", path: (id) => `/project/${id}/review`, requiresAnalysis: true },
];

// ── Step Connector Line ──────────────────────────────────────────────────────

function Connector({ enabled }: { enabled: boolean }) {
	return (
		<div
			className={cn(
				"mx-1 h-px flex-1 transition-colors",
				enabled
					? "bg-indigo-300 dark:bg-indigo-700"
					: "bg-surface-200 dark:bg-surface-dark-700",
			)}
		/>
	);
}

// ── Step Number Circle ──────────────────────────────────────────────────────

function StepCircle({ num, active, enabled }: { num: number; active: boolean; enabled: boolean }) {
	return (
		<span
			className={cn(
				"flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
				active
					? "bg-indigo-600 text-white dark:bg-indigo-500"
					: enabled
						? "bg-indigo-100 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-300"
						: "bg-surface-100 text-surface-400 dark:bg-surface-dark-800 dark:text-surface-dark-500",
			)}
		>
			{num}
		</span>
	);
}

// ── Props ────────────────────────────────────────────────────────────────────

interface ProjectNavbarProps {
	projectId: string;
	// Whether a cached analysis result exists on this project
	hasAnalysis: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Project Navbar Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function ProjectNavbar({ projectId, hasAnalysis }: ProjectNavbarProps) {
	return (
		<nav className="flex items-center gap-1 border-b border-surface-200 bg-surface-50/80 px-6 py-2.5 backdrop-blur-sm dark:border-surface-dark-700 dark:bg-surface-dark-900/80">
			{STAGES.map((stage, i) => {
				// Determine if this stage is reachable
				const enabled = !stage.requiresAnalysis || hasAnalysis;

				return (
					<div key={stage.key} className="contents">
						{/* Connector line between stages */}
						{i > 0 && <Connector enabled={enabled} />}

						{/* Stage link or disabled label */}
						{enabled ? (
							<NavLink
								to={stage.path(projectId)}
								end
								className={({ isActive }) =>
									cn(
										"flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
										isActive
											? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
											: "text-surface-600 hover:bg-surface-100 hover:text-surface-800 dark:text-surface-dark-300 dark:hover:bg-surface-dark-800 dark:hover:text-surface-dark-100",
									)
								}
							>
								{({ isActive }) => (
									<>
										<StepCircle num={i + 1} active={isActive} enabled />
										{stage.label}
									</>
								)}
							</NavLink>
						) : (
							<span className="flex cursor-not-allowed items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium text-surface-400 dark:text-surface-dark-500">
								<StepCircle num={i + 1} active={false} enabled={false} />
								{stage.label}
							</span>
						)}
					</div>
				);
			})}
		</nav>
	);
}
