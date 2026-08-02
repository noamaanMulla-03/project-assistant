// ── Knowledge Base API Client ────────────────────────────────────────────────
// Typed functions for uploading, listing, downloading, and deleting documents
// in the shared knowledge base.  Uses the configured axios instance for auth.

import apiClient from "./client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface KnowledgeDocument {
	id: string;
	filename: string;
	file_type: string;
	file_size: number; // bytes
	status: string; // "processing" | "indexed" | "error"
	visibility: string; // "public" (knowledge base) | "private" (project)
	uploaded_by: string | null;
	uploaded_by_name: string | null;
	created_at: string;
}

interface DocumentListResponse {
	documents: KnowledgeDocument[];
	total: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const ALLOWED_TYPES = [
	"application/pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"text/plain",
];

/** Map MIME type to a display label. */
export function mimeToLabel(mime: string): string {
	const map: Record<string, string> = {
		"application/pdf": "PDF",
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document":
			"DOCX",
		"text/plain": "TXT",
	};
	return map[mime] ?? mime;
}

/** Format bytes into a human-readable string. */
export function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Validate that a File has an allowed extension. */
export function isAllowedFile(file: File): boolean {
	return ALLOWED_TYPES.includes(file.type);
}

/** Human-readable list of allowed extensions. */
export const ALLOWED_EXTENSIONS_LABEL = ".pdf, .docx, .txt";

// ── API Functions ────────────────────────────────────────────────────────────

/** Upload a document to the knowledge base. Returns the created document metadata. */
export async function uploadDocument(file: File): Promise<KnowledgeDocument> {
	const form = new FormData();
	form.append("file", file);

	const { data } = await apiClient.post<KnowledgeDocument>(
		"/knowledge/upload",
		form,
		{
			headers: { "Content-Type": "multipart/form-data" },
			// Optional: track upload progress via onUploadProgress
		},
	);
	return data;
}

/** Fetch paginated list of knowledge-base documents, newest first. */
export async function getDocuments(
	skip = 0,
	limit = 50,
): Promise<DocumentListResponse> {
	const { data } = await apiClient.get<DocumentListResponse>(
		"/knowledge/documents",
		{ params: { skip, limit } },
	);
	return data;
}

/** Download a document by ID — triggers browser save dialog. */
export async function downloadDocument(
	id: string,
	filename: string,
): Promise<void> {
	const { data } = await apiClient.get(`/knowledge/documents/${id}`, {
		responseType: "blob",
	});

	// Create a temporary URL and trigger download
	const url = URL.createObjectURL(data);
	const link = document.createElement("a");
	link.href = url;
	link.download = filename;
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
	URL.revokeObjectURL(url);
}

/** Delete a document by ID. */
export async function deleteDocument(id: string): Promise<void> {
	await apiClient.delete(`/knowledge/documents/${id}`);
}

// ── Document Text ────────────────────────────────────────────────────────────

export interface DocumentText {
	filename: string;
	file_type: string; // "pdf" | "docx" | "txt" — drives frontend rendering
	content: string;
}

/** Fetch the full reconstructed text of a document for the review viewer. */
export async function fetchDocumentText(id: string): Promise<DocumentText> {
	const { data } = await apiClient.get<DocumentText>(
		`/knowledge/documents/${id}/text`,
	);
	return data;
}

/** Retry ingestion for a document that previously failed (status='error'). */
export async function reingestDocument(id: string): Promise<KnowledgeDocument> {
	const { data } = await apiClient.post<KnowledgeDocument>(
		`/knowledge/documents/${id}/reingest`,
	);
	return data;
}
