// ── Project API Client ───────────────────────────────────────────────────────
// Typed functions for creating and fetching multi-document projects.
// Uses the configured axios instance for auth (same as api/knowledge.ts).

import apiClient from "./client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ProjectDocumentRef {
	id: string;
	filename: string;
	file_type: string;
	file_size: number; // bytes
	status: string; // "processing" | "indexed" | "error"
}

export interface ProjectResponse {
	id: string;
	status: string; // aggregate: "indexing" | "ready" | "error"
	documents: ProjectDocumentRef[];
	created_at: string;
	created_by_name: string | null;
}

export interface ProjectListResponse {
	projects: ProjectResponse[];
	total: number;
}

// ── API Functions ────────────────────────────────────────────────────────────

const FIELD_NAMES = ["file1", "file2", "file3"] as const;

/** Create a new project with 1-3 files.  Returns the project with document metadata. */
export async function createProject(files: File[]): Promise<ProjectResponse> {
	const form = new FormData();
	for (let i = 0; i < Math.min(files.length, 3); i++) {
		form.append(FIELD_NAMES[i], files[i]);
	}

	const { data } = await apiClient.post<ProjectResponse>("/projects", form, {
		headers: { "Content-Type": "multipart/form-data" },
	});
	return data;
}

/** Fetch a project by ID, including live per-document ingestion statuses. */
export async function getProject(id: string): Promise<ProjectResponse> {
	const { data } = await apiClient.get<ProjectResponse>(`/projects/${id}`);
	return data;
}

/** Fetch paginated list of the current user's projects, newest first. */
export async function listProjects(
	skip = 0,
	limit = 50,
): Promise<ProjectListResponse> {
	const { data } = await apiClient.get<ProjectListResponse>("/projects", {
		params: { skip, limit },
	});
	return data;
}
