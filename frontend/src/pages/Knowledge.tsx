// ── Knowledge Base Page ──────────────────────────────────────────────────────
// Full-page view for the shared knowledge base.  Features:
//   - Drag-and-drop upload zone with file type validation
//   - Document grid with file-type-coded cards
//   - Download and delete actions
//   - Loading skeletons, empty state, error handling

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { GlowingEffectCard } from "../components/ui/glowing-effect";
import { cn } from "../components/utils";
import {
    ALLOWED_EXTENSIONS_LABEL,
    deleteDocument,
    downloadDocument,
    formatBytes,
    getDocuments,
    isAllowedFile,
    mimeToLabel,
    uploadDocument,
    type KnowledgeDocument,
} from "../api/knowledge";

// ── Inline SVG Icons ─────────────────────────────────────────────────────────

function UploadIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17,8 12,3 7,8" />
            <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
    );
}

function FileIcon({
    fileType,
    className,
}: {
    fileType: string;
    className?: string;
}) {
    return (
        <svg
            className={className}
            width="36"
            height="36"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
        </svg>
    );
}

function DownloadIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7,10 12,15 17,10" />
            <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
    );
}

function TrashIcon({ className }: { className?: string }) {
    return (
        <svg
            className={className}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <polyline points="3,6 5,6 21,6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
    );
}

function Spinner({ className }: { className?: string }) {
    return (
        <svg
            className={cn("animate-spin", className)}
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
        >
            <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="3"
                className="opacity-25"
            />
            <path
                d="M12 2a10 10 0 0 1 10 10"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
            />
        </svg>
    );
}

// ── File type colour map ─────────────────────────────────────────────────────

const FILE_COLORS: Record<string, string> = {
    pdf: "text-red-500",
    docx: "text-blue-500",
    txt: "text-gray-500 dark:text-gray-400",
};

const FILE_BG_COLORS: Record<string, string> = {
    pdf: "bg-red-50 dark:bg-red-950/30",
    docx: "bg-blue-50 dark:bg-blue-950/30",
    txt: "bg-gray-100 dark:bg-gray-800/30",
};

// ═══════════════════════════════════════════════════════════════════════════════
//  Knowledge Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function Knowledge() {
    const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // ── Fetch documents on mount ──────────────────────────────────────────
    const fetchDocs = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const { documents: docs } = await getDocuments();
            setDocuments(docs);
        } catch {
            setError("Failed to load documents. Please try again.");
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDocs();
    }, [fetchDocs]);

    // ── Upload handler ────────────────────────────────────────────────────
    const handleUpload = useCallback(
        async (file: File) => {
            if (!isAllowedFile(file)) {
                setError(
                    `"${file.name}" is not a supported file type. Please use ${ALLOWED_EXTENSIONS_LABEL}.`,
                );
                return;
            }

            setIsUploading(true);
            setError(null);
            try {
                const doc = await uploadDocument(file);
                setDocuments((prev) => [doc, ...prev]); // Prepend newest
            } catch (err: unknown) {
                const msg =
                    err instanceof Error ? err.message : "Upload failed.";
                setError(msg);
            } finally {
                setIsUploading(false);
            }
        },
        [],
    );

    // ── Download handler ──────────────────────────────────────────────────
    const handleDownload = useCallback(
        async (doc: KnowledgeDocument) => {
            try {
                await downloadDocument(doc.id, doc.filename);
            } catch {
                setError("Download failed. Please try again.");
            }
        },
        [],
    );

    // ── Delete handler ────────────────────────────────────────────────────
    const handleDelete = useCallback(
        async (doc: KnowledgeDocument) => {
            if (
                !window.confirm(
                    `Delete "${doc.filename}"? This cannot be undone.`,
                )
            )
                return;

            try {
                await deleteDocument(doc.id);
                setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
            } catch {
                setError("Delete failed. Please try again.");
            }
        },
        [],
    );

    // ── Drag-and-drop handlers ────────────────────────────────────────────
    const handleDragOver = (e: DragEvent) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = (e: DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
    };

    const handleDrop = (e: DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) handleUpload(files[0]);
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (files && files.length > 0) handleUpload(files[0]);
        // Reset input so the same file can be re-uploaded
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    // ── Skeleton cards for loading state ──────────────────────────────────
    const renderSkeletons = (count = 4) =>
        Array.from({ length: count }).map((_, i) => (
            <div
                key={i}
                className="animate-pulse rounded-2xl border border-surface-200 bg-white p-5 dark:border-surface-dark-700 dark:bg-surface-dark-900"
            >
                <div className="mb-3 h-8 w-8 rounded-lg bg-surface-200 dark:bg-surface-dark-800" />
                <div className="mb-2 h-4 w-3/4 rounded bg-surface-200 dark:bg-surface-dark-800" />
                <div className="h-3 w-1/2 rounded bg-surface-100 dark:bg-surface-dark-800" />
            </div>
        ));

    return (
        <div className="px-4 py-12">
            <div className="mx-auto max-w-5xl">
                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="mb-8">
                    <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">
                        Knowledge Base
                    </h1>
                    <p className="mt-1 text-sm text-surface-700 dark:text-surface-dark-300">
                        Upload and manage documents shared across all users.
                        Supported formats: {ALLOWED_EXTENSIONS_LABEL}
                    </p>
                </div>

                {/* ── Upload Zone ────────────────────────────────────────── */}
                <GlowingEffectCard className="mb-10">
                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                        className={cn(
                            "cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-colors",
                            isDragOver
                                ? "border-indigo-400 bg-indigo-50/50 dark:border-indigo-500 dark:bg-indigo-950/20"
                                : "border-surface-300 bg-white hover:border-surface-400 dark:border-surface-dark-700 dark:bg-surface-dark-900 dark:hover:border-surface-dark-600",
                        )}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf,.docx,.txt"
                            onChange={handleFileSelect}
                            className="hidden"
                        />

                        {isUploading ? (
                            <div className="flex flex-col items-center gap-3">
                                <Spinner className="text-indigo-500" />
                                <p className="text-sm text-surface-700 dark:text-surface-dark-300">
                                    Uploading...
                                </p>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center gap-3">
                                <div
                                    className={cn(
                                        "rounded-full p-3 transition-colors",
                                        isDragOver
                                            ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-950/50 dark:text-indigo-400"
                                            : "bg-surface-100 text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-300",
                                    )}
                                >
                                    <UploadIcon />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-surface-800 dark:text-surface-dark-100">
                                        {isDragOver
                                            ? "Drop your file here"
                                            : "Drag & drop a file here, or click to browse"}
                                    </p>
                                    <p className="mt-1 text-xs text-surface-500 dark:text-surface-dark-300">
                                        {ALLOWED_EXTENSIONS_LABEL} — up to 25 MB
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </GlowingEffectCard>

                {/* ── Error Banner ────────────────────────────────────────── */}
                {error && (
                    <div className="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
                        <span>{error}</span>
                        <button
                            onClick={() => setError(null)}
                            className="ml-auto shrink-0 rounded-lg p-1 hover:bg-red-100 dark:hover:bg-red-950/50"
                            aria-label="Dismiss error"
                        >
                            ✕
                        </button>
                    </div>
                )}

                {/* ── Document Grid ──────────────────────────────────────── */}
                {isLoading ? (
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {renderSkeletons(6)}
                    </div>
                ) : documents.length === 0 ? (
                    /* Empty state */
                    <div className="rounded-2xl border border-dashed border-surface-300 px-6 py-16 text-center dark:border-surface-dark-700">
                        <FileIcon
                            fileType=""
                            className="mx-auto mb-4 text-surface-400 dark:text-surface-dark-500"
                        />
                        <p className="text-sm font-medium text-surface-700 dark:text-surface-dark-300">
                            No documents yet
                        </p>
                        <p className="mt-1 text-xs text-surface-500 dark:text-surface-dark-400">
                            Upload your first document using the drop zone
                            above.
                        </p>
                    </div>
                ) : (
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {documents.map((doc) => {
                            const colorClass =
                                FILE_COLORS[doc.file_type] ??
                                "text-surface-500";
                            const bgClass =
                                FILE_BG_COLORS[doc.file_type] ?? "";

                            return (
                                <GlowingEffectCard
                                    key={doc.id}
                                    className="h-full"
                                >
                                    <div
                                        className={cn(
                                            "flex h-full flex-col rounded-2xl bg-white p-5 dark:bg-surface-dark-900",
                                        )}
                                    >
                                        {/* File type icon + label */}
                                        <div className="mb-3 flex items-center gap-3">
                                            <div
                                                className={cn(
                                                    "rounded-lg p-2",
                                                    bgClass,
                                                    colorClass,
                                                )}
                                            >
                                                <FileIcon
                                                    fileType={doc.file_type}
                                                />
                                            </div>
                                            <span
                                                className={cn(
                                                    "rounded-md px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
                                                    bgClass,
                                                    colorClass,
                                                )}
                                            >
                                                {mimeToLabel(doc.file_type) ||
                                                    doc.file_type}
                                            </span>
                                        </div>

                                        {/* Filename */}
                                        <p
                                            className="mb-1 line-clamp-2 text-sm font-medium text-surface-800 dark:text-surface-dark-100"
                                            title={doc.filename}
                                        >
                                            {doc.filename}
                                        </p>

                                        {/* Metadata */}
                                        <p className="mb-4 text-xs text-surface-500 dark:text-surface-dark-400">
                                            {formatBytes(doc.file_size)} ·{" "}
                                            {new Date(
                                                doc.created_at,
                                            ).toLocaleDateString()}
                                            {doc.uploaded_by_name && (
                                                <>
                                                    {" "}
                                                    · by{" "}
                                                    {doc.uploaded_by_name}
                                                </>
                                            )}
                                        </p>

                                        {/* Spacer pushes actions to bottom */}
                                        <div className="flex-1" />

                                        {/* Actions */}
                                        <div className="flex gap-2">
                                            <button
                                                onClick={() =>
                                                    handleDownload(doc)
                                                }
                                                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-surface-300 px-3 py-2 text-xs font-medium text-surface-700 transition-colors hover:border-surface-700 hover:bg-surface-100 dark:border-surface-dark-700 dark:text-surface-dark-300 dark:hover:border-surface-dark-200 dark:hover:bg-surface-dark-800"
                                            >
                                                <DownloadIcon />
                                                Download
                                            </button>
                                            <button
                                                onClick={() =>
                                                    handleDelete(doc)
                                                }
                                                className="flex items-center justify-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-900/30 dark:text-red-400 dark:hover:bg-red-950/30"
                                            >
                                                <TrashIcon />
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                </GlowingEffectCard>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
