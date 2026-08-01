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

export interface ExtractionResult {
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

/** Run AI extraction on a project's documents.  Returns the full structured payload. */
export async function analyzeProject(id: string): Promise<ExtractionResult> {
	const { data } = await apiClient.post<ExtractionResult>(
		`/projects/${id}/analyze`,
	);
	return data;
}
