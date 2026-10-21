// ── Project API Client ───────────────────────────────────────────────────────
// Typed functions for creating, fetching, and analysing multi-document projects.
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
	// Cached AI extraction result — null until the first analysis completes
	analysis_result: ExtractionResult | null;
	analysis_status: "idle" | "running" | "completed" | "error";
	analysis_error: string | null;
	// User-reviewed action summary — null until the user saves their review
	review_summary: ReviewSummary | null;
}

export interface ProjectListResponse {
	projects: ProjectResponse[];
	total: number;
}

// ── Extraction Result Types (mirrors backend schemas/extraction.py) ──────────

export interface Fact {
	content: string;
	source_document: string;
	source_section: string;
	confidence: "high" | "medium" | "low";
}

export interface Decision {
	content: string;
	source_document: string;
	source_section: string;
	stakeholders: string[];
}

export interface Assumption {
	content: string;
	source_document: string;
	source_section: string;
	validation_needed: boolean;
}

export interface Risk {
	content: string;
	source_document: string;
	source_section: string;
	severity: "critical" | "high" | "medium" | "low";
	mitigation: string;
}

export interface OpenQuestion {
	content: string;
	source_document: string;
	source_section: string;
	suggested_owner: string;
}

export interface ActionItem {
	content: string;
	source_document: string;
	source_section: string;
	priority: "high" | "medium" | "low";
	deadline: string;
}

export interface DocumentConflict {
	statement_a: string;
	statement_b: string;
	document_a: string;
	document_b: string;
	section_a: string;
	section_b: string;
	resolution_suggestion: string;
}

export interface RepeatedStatement {
	statement: string;
	document_a: string;
	document_b: string;
	section_a: string;
	section_b: string;
	is_exact_match: boolean;
}

export interface MissingAction {
	description: string;
	policy_reference: string;
	policy_section: string;
	urgency: "critical" | "high" | "medium" | "low";
}

export interface MissingQuestion {
	question: string;
	policy_reference: string;
	policy_section: string;
	urgency: "critical" | "high" | "medium" | "low";
}

export interface DocumentType {
	filename: string;
	document_type: string;
}

export interface ExtractionResult {
	document_types: DocumentType[];
	summary: string;
	facts: Fact[];
	decisions: Decision[];
	assumptions: Assumption[];
	risks: Risk[];
	open_questions: OpenQuestion[];
	action_items: ActionItem[];
	document_conflicts: DocumentConflict[];
	missing_actions: MissingAction[];
	missing_questions: MissingQuestion[];
	repeated_statements: RepeatedStatement[];
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
	window.dispatchEvent(new Event("projects:changed"));
	return data;
}

/** Fetch a project by ID, including live per-document ingestion statuses. */
export async function getProject(id: string): Promise<ProjectResponse> {
	const { data } = await apiClient.get<ProjectResponse>(`/projects/${id}`, {
		headers: { "Cache-Control": "no-cache" },
	});
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

/** Start analysis and return its current project status immediately. */
export async function analyzeProject(
	id: string,
	force = false,
): Promise<ProjectResponse> {
	const { data } = await apiClient.post<ProjectResponse>(
		`/projects/${id}/analyze`,
		null,
		{ params: force ? { force: true } : undefined },
	);
	return data;
}

/** Remove a document from a project.  Deletes the doc from disk, DB, and FAISS.
 *  Returns the updated project, or `{deleted: true}` if the last doc was removed. */
export async function removeProjectDocument(
	projectId: string,
	documentId: string,
): Promise<ProjectResponse | { deleted: true }> {
	const { data } = await apiClient.delete<
		ProjectResponse | { deleted: true }
	>(`/projects/${projectId}/documents/${documentId}`);
	return data;
}

// ── Review Summary Types ─────────────────────────────────────────────────────

export interface ReviewSummary {
	facts: unknown[];
	conflicts: unknown[];
	action_items: unknown[];
}

/** Save the user-reviewed action summary for a project. */
export async function saveReview(
	projectId: string,
	review: ReviewSummary,
): Promise<ProjectResponse> {
	const { data } = await apiClient.put<ProjectResponse>(
		`/projects/${projectId}/review`,
		review,
	);
	return data;
}
