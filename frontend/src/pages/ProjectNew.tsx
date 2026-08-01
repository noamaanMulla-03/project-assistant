// ── Project New Page ─────────────────────────────────────────────────────────
// 3-slot document upload page for creating a new AI analysis project.
// Flow: select 1-3 files → "Upload Documents" → auto-poll ingestion status →
// "Start Analysis" button activates when all documents are indexed.
//
// Reuses helpers from api/knowledge.ts (formatBytes, mimeToLabel, isAllowedFile,
// ALLOWED_EXTENSIONS_LABEL) to keep UI formatting consistent.

import { useCallback, useEffect, useRef, useState } from "react";
import { GlowingEffectCard } from "../components/ui/glowing-effect";
import { cn } from "../components/utils";
import { createProject, getProject, type ProjectDocumentRef, type ProjectResponse } from "../api/project";
import {
    ALLOWED_EXTENSIONS_LABEL,
    formatBytes,
    isAllowedFile,
    mimeToLabel,
} from "../api/knowledge";

// ── Constants ────────────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3000;
const SLOT_COUNT = 3;

// ── File type colour map (matches Knowledge.tsx) ─────────────────────────────

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

// ── Inline SVG Icons (consistent pattern with Knowledge.tsx) ──────────────────

function FileIcon({ className }: { className?: string }) {
    return (
        <svg className={className} width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
        </svg>
    );
}

function Spinner({ className }: { className?: string }) {
    return (
        <svg className={cn("animate-spin", className)} width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
    );
}

function CheckCircleIcon({ className }: { className?: string }) {
    return (
        <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22,4 12,14.01 9,11.01" />
        </svg>
    );
}

function AlertTriangleIcon({ className }: { className?: string }) {
    return (
        <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
    );
}

function ArrowRightIcon({ className }: { className?: string }) {
    return (
        <svg className={className} width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12,5 19,12 12,19" />
        </svg>
    );
}

function XIcon({ className }: { className?: string }) {
    return (
        <svg className={className} width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
    );
}

// ── Status Pill Component ────────────────────────────────────────────────────

function StatusPill({ status }: { status: string }) {
    const config: Record<string, { bg: string; text: string; icon: React.ReactNode; label: string }> = {
        processing: {
            bg: "bg-amber-50 dark:bg-amber-950/30",
            text: "text-amber-700 dark:text-amber-400",
            icon: <Spinner />,
            label: "Indexing...",
        },
        indexed: {
            bg: "bg-emerald-50 dark:bg-emerald-950/30",
            text: "text-emerald-700 dark:text-emerald-400",
            icon: <CheckCircleIcon />,
            label: "Ready",
        },
        error: {
            bg: "bg-red-50 dark:bg-red-950/30",
            text: "text-red-700 dark:text-red-400",
            icon: <AlertTriangleIcon />,
            label: "Error",
        },
    };
    const c = config[status] ?? config.indexed;
    return (
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", c.bg, c.text)}>
            {c.icon}
            {c.label}
        </span>
    );
}

// ── Upload Slot Component ────────────────────────────────────────────────────

interface SlotProps {
    index: number;
    file: File | null;
    docRef: ProjectDocumentRef | null;
    onSelect: (file: File) => void;
    onRemove: () => void;
    disabled: boolean;
}

function UploadSlot({ index, file, docRef, onSelect, onRemove, disabled }: SlotProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const slotNum = index + 1;

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const f = e.target.files?.[0];
        if (f) onSelect(f);
        if (inputRef.current) inputRef.current.value = "";
    };

    // ── Empty slot ────────────────────────────────────────────────────────
    if (!file && !docRef) {
        return (
            <GlowingEffectCard className="h-full">
                <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    disabled={disabled}
                    className={cn(
                        "flex h-full min-h-[180px] w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-6 transition-colors",
                        disabled
                            ? "cursor-not-allowed border-surface-200 bg-surface-50 opacity-50 dark:border-surface-dark-800 dark:bg-surface-dark-950"
                            : "cursor-pointer border-surface-300 bg-white hover:border-indigo-400 hover:bg-indigo-50/30 dark:border-surface-dark-700 dark:bg-surface-dark-900 dark:hover:border-indigo-500 dark:hover:bg-indigo-950/20",
                    )}
                >
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".pdf,.docx,.txt"
                        onChange={handleFileChange}
                        disabled={disabled}
                        className="hidden"
                    />
                    <span className="text-2xl font-bold text-surface-300 dark:text-surface-dark-600">
                        {slotNum}
                    </span>
                    <div className="text-center">
                        <p className="text-sm font-medium text-surface-600 dark:text-surface-dark-300">
                            Document {slotNum}
                        </p>
                        <p className="mt-1 text-xs text-surface-400 dark:text-surface-dark-500">
                            {ALLOWED_EXTENSIONS_LABEL}
                        </p>
                    </div>
                </button>
            </GlowingEffectCard>
        );
    }

    // ── Filled slot ──────────────────────────────────────────────────────
    const displayName = docRef?.filename ?? file?.name ?? "";
    const fileType = docRef?.file_type ?? (file ? file.type.split("/").pop()?.toLowerCase() ?? "" : "");
    const fileSize = docRef?.file_size ?? file?.size ?? 0;
    const status = docRef?.status ?? "pending";

    return (
        <GlowingEffectCard className="h-full">
            <div className="flex h-full min-h-[180px] flex-col rounded-2xl bg-white p-5 dark:bg-surface-dark-900">
                {/* Top row: icon + remove button */}
                <div className="mb-3 flex items-start justify-between">
                    <div className={cn("rounded-lg p-2", FILE_BG_COLORS[fileType] ?? FILE_BG_COLORS.txt)}>
                        <FileIcon className={FILE_COLORS[fileType] ?? FILE_COLORS.txt} />
                    </div>
                    <button
                        type="button"
                        onClick={onRemove}
                        className="rounded-md p-1 text-surface-400 transition-colors hover:bg-surface-100 hover:text-surface-600 dark:text-surface-dark-400 dark:hover:bg-surface-dark-800 dark:hover:text-surface-dark-200"
                        title="Remove file"
                    >
                        <XIcon />
                    </button>
                </div>

                {/* Filename */}
                <p className="truncate text-sm font-medium text-surface-800 dark:text-surface-dark-100" title={displayName}>
                    {displayName}
                </p>

                {/* File type badge + size */}
                <div className="mt-1 flex items-center gap-2">
                    <span className={cn(
                        "rounded px-1.5 py-0.5 text-xs font-semibold",
                        FILE_BG_COLORS[fileType] ?? FILE_BG_COLORS.txt,
                        FILE_COLORS[fileType] ?? FILE_COLORS.txt,
                    )}>
                        {mimeToLabel(fileType === "pdf" ? "application/pdf" :
                            fileType === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" :
                                "text/plain")}
                    </span>
                    <span className="text-xs text-surface-400 dark:text-surface-dark-500">
                        {formatBytes(fileSize)}
                    </span>
                </div>

                {/* Status pill (only after upload) */}
                {docRef && (
                    <div className="mt-3">
                        <StatusPill status={status} />
                    </div>
                )}
            </div>
        </GlowingEffectCard>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Project New Page
// ═══════════════════════════════════════════════════════════════════════════════

export default function ProjectNew() {
    const [files, setFiles] = useState<(File | null)[]>(Array(SLOT_COUNT).fill(null));
    const [project, setProject] = useState<ProjectResponse | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // ── Poll ingestion status until all docs are indexed ──────────────────
    const projectStatus = project?.status;
    useEffect(() => {
        if (!project?.id || projectStatus === "ready" || projectStatus === "error") return;

        const interval = setInterval(async () => {
            try {
                const updated = await getProject(project.id);
                setProject(updated);
            } catch { /* silently ignore poll errors */ }
        }, POLL_INTERVAL_MS);

        return () => clearInterval(interval);
    }, [project?.id, projectStatus]);

    // ── Set a file in a specific slot ─────────────────────────────────────
    const handleFileSelect = useCallback((index: number, file: File) => {
        if (!isAllowedFile(file)) {
            setError(`"${file.name}" is not a supported type. Use ${ALLOWED_EXTENSIONS_LABEL}.`);
            return;
        }
        setError(null);
        setFiles((prev) => {
            const next = [...prev];
            next[index] = file;
            return next;
        });
    }, []);

    // ── Remove a file from a slot ────────────────────────────────────────
    const handleFileRemove = useCallback((index: number) => {
        // If already uploaded, don't allow removal (would orphan the doc)
        if (project) return;
        setFiles((prev) => {
            const next = [...prev];
            next[index] = null;
            return next;
        });
    }, [project]);

    // ── Upload all selected files ────────────────────────────────────────
    const handleUpload = async () => {
        const selectedFiles = files.filter((f): f is File => f !== null);
        if (selectedFiles.length === 0) return;

        setIsUploading(true);
        setError(null);
        try {
            const proj = await createProject(selectedFiles);
            setProject(proj);
            setFiles(Array(SLOT_COUNT).fill(null)); // Clear files, use docRefs from now on
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
        } finally {
            setIsUploading(false);
        }
    };

    // ── Derived state ────────────────────────────────────────────────────
    const selectedCount = files.filter(Boolean).length;
    const canUpload = selectedCount > 0 && !isUploading && !project;
    const isReady = project?.status === "ready";
    const hasError = project?.status === "error" || project?.documents.some((d) => d.status === "error");
    const isPolling = project && project.status === "indexing";

    // ── Build slot data: prefer docRef from project, fall back to local File ──
    const slots = Array.from({ length: SLOT_COUNT }, (_, i) => ({
        index: i,
        file: files[i],
        docRef: project?.documents[i] ?? null,
    }));

    return (
        <div className="px-4 py-12">
            <div className="mx-auto max-w-5xl">
                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="mb-8">
                    <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">
                        New Project
                    </h1>
                    <p className="mt-1 text-sm text-surface-700 dark:text-surface-dark-300">
                        Upload 1-3 project documents (meeting notes, requirements, decision records, etc.)
                        for AI analysis. Supported: {ALLOWED_EXTENSIONS_LABEL}.
                    </p>
                </div>

                {/* ── Upload Slots ──────────────────────────────────────── */}
                <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
                    {slots.map((slot) => (
                        <UploadSlot
                            key={slot.index}
                            index={slot.index}
                            file={slot.file}
                            docRef={slot.docRef}
                            onSelect={(f) => handleFileSelect(slot.index, f)}
                            onRemove={() => handleFileRemove(slot.index)}
                            disabled={!!project}
                        />
                    ))}
                </div>

                {/* ── Error Banner ──────────────────────────────────────── */}
                {error && (
                    <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
                        {error}
                        <button
                            type="button"
                            onClick={() => setError(null)}
                            className="ml-3 font-medium underline hover:no-underline"
                        >
                            Dismiss
                        </button>
                    </div>
                )}

                {/* ── Action Bar ────────────────────────────────────────── */}
                <div className="flex flex-col items-center gap-3">
                    {!project && (
                        <button
                            type="button"
                            onClick={handleUpload}
                            disabled={!canUpload}
                            className={cn(
                                "inline-flex items-center gap-2 rounded-xl px-8 py-3 text-sm font-semibold transition-all",
                                canUpload
                                    ? "bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-500/25 active:scale-[0.98]"
                                    : "cursor-not-allowed bg-surface-200 text-surface-400 dark:bg-surface-dark-800 dark:text-surface-dark-500",
                            )}
                        >
                            {isUploading ? (
                                <>
                                    <Spinner /> Uploading...
                                </>
                            ) : (
                                <>
                                    <ArrowRightIcon /> Upload Documents
                                </>
                            )}
                        </button>
                    )}

                    {project && (
                        <button
                            type="button"
                            disabled={!isReady}
                            className={cn(
                                "inline-flex items-center gap-2 rounded-xl px-8 py-3 text-sm font-semibold transition-all",
                                isReady
                                    ? "bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-700 hover:to-violet-700 shadow-lg shadow-indigo-500/25 active:scale-[0.98]"
                                    : "cursor-not-allowed border-2 border-surface-300 bg-transparent text-surface-400 dark:border-surface-dark-700 dark:text-surface-dark-500",
                            )}
                        >
                            {isPolling ? (
                                <>
                                    <Spinner /> Indexing documents...
                                </>
                            ) : hasError ? (
                                <>
                                    <AlertTriangleIcon className="text-red-500" /> Indexing failed
                                </>
                            ) : (
                                <>
                                    Start Analysis <ArrowRightIcon />
                                </>
                            )}
                        </button>
                    )}

                    {project && (
                        <p className="text-xs text-surface-400 dark:text-surface-dark-500">
                            {isPolling
                                ? "Documents are being processed. This may take a minute for large files."
                                : isReady
                                    ? "All documents indexed — ready for AI analysis."
                                    : hasError
                                        ? "One or more documents failed to index. Remove the project and try again."
                                        : ""
                            }
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
