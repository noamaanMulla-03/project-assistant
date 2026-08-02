// ── Utility Helpers ──────────────────────────────────────────────────────────
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind CSS classes, resolving conflicts. */
export function cn(...inputs: ClassValue[]): string {
	return twMerge(clsx(inputs));
}

// ── Error message extraction ─────────────────────────────────────────────────
// FastAPI returns validation errors (422) as:
//   { detail: [{ type, loc, msg, input, ctx }] }
// Other errors return:
//   { detail: "string message" }
// Axios network errors have no response at all.

interface FastAPIValidationError {
	msg: string;
}

/**
 * Extract a human-readable error message from an Axios error or similar shape.
 * Handles FastAPI's array-format validation errors and plain string details.
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
	const data = (err as { response?: { data?: unknown } })?.response?.data;
	if (!data) return fallback;

	const detail = (data as { detail?: unknown })?.detail;
	if (detail === undefined || detail === null) return fallback;

	// FastAPI 422: detail is an array of { msg, loc, type, ... }
	if (Array.isArray(detail)) {
		return (detail as FastAPIValidationError[])
			.map((e) => e.msg)
			.filter(Boolean)
			.join("; ");
	}

	// Plain string detail (most other FastAPI errors)
	if (typeof detail === "string") return detail;

	return fallback;
}
