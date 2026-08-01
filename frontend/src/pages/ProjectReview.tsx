// ── Project Review Workspace ──────────────────────────────────────────────────
// Interactive split-screen workspace for reviewing AI-extracted items.
// Left pane: editable cards for Facts, Conflicts, and Action Items.
// Right pane: document text viewer with section highlighting.
//
// Architecture:
//   • Receives ExtractionResult + ProjectDocumentRef[] as props (no own fetch)
//   • Transforms raw extraction data into mutable review state on mount
//   • "View Source" badge on each card updates selectedSource → right pane
//   • "Finalize & Save" logs the full mutable state as JSON to console

import { useCallback, useEffect, useMemo, useState } from "react";
import Split from "react-split";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { cn } from "../components/utils";
import { fetchDocumentText } from "../api/knowledge";
import type {
    ExtractionResult,
    Fact,
    DocumentConflict,
    ActionItem,
    ProjectDocumentRef,
} from "../api/project";

// ═══════════════════════════════════════════════════════════════════════════════
//  Types
// ═══════════════════════════════════════════════════════════════════════════════

// ── Review-specific item wrappers — extend extraction types with UI state ─────

/** Fact extended with a reclassifiable category. */
interface FactReviewItem extends Fact {
    classification: "fact" | "assumption" | "unresolved";
}

/** Conflict extended with resolution tracking. */
interface ConflictReviewItem extends DocumentConflict {
    resolution_note: string;
    resolved: boolean;
}

/** Action item extended with human validation status. */
interface ActionReviewItem extends ActionItem {
    status: "pending" | "approved" | "rejected";
    edited_content: string;
}

/** The full mutable review state for the entire workspace. */
interface ReviewState {
    facts: FactReviewItem[];
    conflicts: ConflictReviewItem[];
    action_items: ActionReviewItem[];
}

/** Metadata passed to the right pane when "View Source" is clicked. */
interface SelectedSource {
    documentId: string;
    documentName: string;
    section: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════════════════

/** Build a lookup from source_document filename → document ID + filename. */
function buildDocLookup(
    docs: ProjectDocumentRef[],
): Map<string, { id: string; filename: string }> {
    const map = new Map<string, { id: string; filename: string }>();
    for (const d of docs) {
        map.set(d.filename, { id: d.id, filename: d.filename });
    }
    return map;
}

/** Transform raw ExtractionResult into mutable ReviewState. */
function initReviewState(result: ExtractionResult): ReviewState {
    return {
        facts: result.facts.map((f) => ({
            ...f,
            classification: "fact" as const,
        })),
        conflicts: result.document_conflicts.map((c) => ({
            ...c,
            resolution_note: "",
            resolved: false,
        })),
        action_items: result.action_items.map((a) => ({
            ...a,
            status: "pending" as const,
            edited_content: a.content,
        })),
    };
}

// ── Classification colour helpers ────────────────────────────────────────────

const CLASSIFICATION_COLORS: Record<string, string> = {
    fact: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
    assumption:
        "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    unresolved:
        "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
};

const STATUS_COLORS: Record<string, string> = {
    pending: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
    approved:
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
    rejected: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
};

const PRIORITY_COLORS: Record<string, string> = {
    high: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
    medium:
        "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

// ═══════════════════════════════════════════════════════════════════════════════
//  Sub-components
// ═══════════════════════════════════════════════════════════════════════════════

// ── Clickable "View Source" badge ────────────────────────────────────────────

function SourceButton({
    document,
    section,
    onClick,
}: {
    document: string;
    section: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-surface-100 px-2 py-0.5 text-xs text-surface-500 transition-colors hover:bg-primary-100 hover:text-primary-700 dark:bg-surface-dark-800 dark:text-surface-dark-400 dark:hover:bg-primary-900/30 dark:hover:text-primary-400"
            aria-label={`View source: ${document}, ${section}`}
        >
            <svg
                className="h-3 w-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
            >
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            {document} · {section}
        </button>
    );
}

// ── Fact Card ────────────────────────────────────────────────────────────────

function FactCard({
    item,
    index,
    docId,
    onUpdate,
    onViewSource,
}: {
    item: FactReviewItem;
    index: number;
    docId: string;
    onUpdate: (index: number, patch: Partial<FactReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string) => void;
}) {
    return (
        <Card
            size="sm"
            className="border-l-4 border-l-emerald-400 dark:border-l-emerald-600"
        >
            <CardHeader className="flex flex-row items-center gap-2">
                {/* Icon */}
                <svg
                    className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22,4 12,14.01 9,11.01" />
                </svg>
                <CardTitle className="text-sm">Fact #{index + 1}</CardTitle>
                {/* Classification badge */}
                <span
                    className={cn(
                        "ml-auto rounded px-1.5 py-0.5 text-xs font-medium",
                        CLASSIFICATION_COLORS[item.classification] ??
                        CLASSIFICATION_COLORS.fact,
                    )}
                >
                    {item.classification}
                </span>
            </CardHeader>

            <CardContent className="flex flex-col gap-3">
                {/* Editable content textarea */}
                <textarea
                    className="w-full resize-y rounded-md border border-surface-200 bg-surface-50 px-3 py-2 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                    rows={3}
                    value={item.content}
                    onChange={(e) =>
                        onUpdate(index, { content: e.target.value })
                    }
                    aria-label={`Fact ${index + 1} content`}
                />

                <div className="flex items-center gap-3">
                    {/* Reclassification dropdown */}
                    <select
                        className="rounded-md border border-surface-200 bg-surface-50 px-2 py-1 text-xs text-surface-700 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-200"
                        value={item.classification}
                        onChange={(e) =>
                            onUpdate(index, {
                                classification: e.target.value as
                                    | "fact"
                                    | "assumption"
                                    | "unresolved",
                            })
                        }
                        aria-label="Reclassify item"
                    >
                        <option value="fact">Fact</option>
                        <option value="assumption">Assumption</option>
                        <option value="unresolved">Unresolved</option>
                    </select>

                    {/* Confidence pill (read-only from extraction) */}
                    <span className="rounded bg-surface-100 px-1.5 py-0.5 text-xs text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                        confidence: {item.confidence}
                    </span>

                    {/* View Source button */}
                    <div className="ml-auto">
                        <SourceButton
                            document={item.source_document}
                            section={item.source_section}
                            onClick={() =>
                                onViewSource(
                                    docId,
                                    item.source_document,
                                    item.source_section,
                                )
                            }
                        />
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

// ── Conflict Card ────────────────────────────────────────────────────────────

function ConflictCard({
    item,
    index,
    docIdA,
    docIdB,
    onUpdate,
    onViewSource,
}: {
    item: ConflictReviewItem;
    index: number;
    docIdA: string;
    docIdB: string;
    onUpdate: (index: number, patch: Partial<ConflictReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string) => void;
}) {
    return (
        <Card
            size="sm"
            className={cn(
                "border-l-4",
                item.resolved
                    ? "border-l-emerald-400 dark:border-l-emerald-600"
                    : "border-l-red-400 dark:border-l-red-600",
            )}
        >
            <CardHeader className="flex flex-row items-center gap-2">
                {/* Icon */}
                <svg
                    className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
                <CardTitle className="text-sm">Conflict #{index + 1}</CardTitle>
                {/* Resolved toggle */}
                <button
                    type="button"
                    onClick={() =>
                        onUpdate(index, { resolved: !item.resolved })
                    }
                    className={cn(
                        "ml-auto rounded-md px-2 py-0.5 text-xs font-medium transition-colors",
                        item.resolved
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
                            : "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
                    )}
                >
                    {item.resolved ? "Resolved ✓" : "Unresolved"}
                </button>
            </CardHeader>

            <CardContent className="flex flex-col gap-3">
                {/* Side-by-side contradictory statements */}
                <div className="grid grid-cols-2 gap-3">
                    {/* Statement A */}
                    <div className="rounded-md border border-red-200 bg-red-50/50 p-3 dark:border-red-800 dark:bg-red-950/20">
                        <p className="mb-2 text-xs font-medium text-red-600 dark:text-red-400">
                            Statement A — {item.document_a}
                        </p>
                        <blockquote className="text-xs leading-relaxed text-surface-700 dark:text-surface-dark-200">
                            {item.statement_a}
                        </blockquote>
                        <button
                            type="button"
                            onClick={() =>
                                onViewSource(
                                    docIdA,
                                    item.document_a,
                                    item.section_a,
                                )
                            }
                            className="mt-2 text-xs text-primary-500 hover:underline"
                        >
                            View source · {item.section_a}
                        </button>
                    </div>

                    {/* Statement B */}
                    <div className="rounded-md border border-red-200 bg-red-50/50 p-3 dark:border-red-800 dark:bg-red-950/20">
                        <p className="mb-2 text-xs font-medium text-red-600 dark:text-red-400">
                            Statement B — {item.document_b}
                        </p>
                        <blockquote className="text-xs leading-relaxed text-surface-700 dark:text-surface-dark-200">
                            {item.statement_b}
                        </blockquote>
                        <button
                            type="button"
                            onClick={() =>
                                onViewSource(
                                    docIdB,
                                    item.document_b,
                                    item.section_b,
                                )
                            }
                            className="mt-2 text-xs text-primary-500 hover:underline"
                        >
                            View source · {item.section_b}
                        </button>
                    </div>
                </div>

                {/* Resolution note input */}
                <input
                    type="text"
                    className="w-full rounded-md border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                    placeholder="Resolution note..."
                    value={item.resolution_note}
                    onChange={(e) =>
                        onUpdate(index, { resolution_note: e.target.value })
                    }
                    aria-label={`Resolution note for conflict ${index + 1}`}
                />

                {/* AI suggestion (read-only) */}
                {item.resolution_suggestion && (
                    <p className="rounded-md bg-surface-100 px-3 py-2 text-xs text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                        💡 AI suggestion: {item.resolution_suggestion}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

// ── Action Item Card ─────────────────────────────────────────────────────────

function ActionItemCard({
    item,
    index,
    docId,
    onUpdate,
    onViewSource,
}: {
    item: ActionReviewItem;
    index: number;
    docId: string;
    onUpdate: (index: number, patch: Partial<ActionReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string) => void;
}) {
    return (
        <Card
            size="sm"
            className={cn(
                "border-l-4",
                item.status === "approved"
                    ? "border-l-emerald-400 dark:border-l-emerald-600"
                    : item.status === "rejected"
                        ? "border-l-red-400 dark:border-l-red-600"
                        : "border-l-blue-400 dark:border-l-blue-600",
            )}
        >
            <CardHeader className="flex flex-row items-center gap-2">
                {/* Task icon */}
                <svg
                    className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14,2 14,8 20,8" />
                </svg>
                <CardTitle className="text-sm">
                    Action #{index + 1}
                </CardTitle>
                {/* Status badge */}
                <span
                    className={cn(
                        "ml-auto rounded px-1.5 py-0.5 text-xs font-medium",
                        STATUS_COLORS[item.status] ?? STATUS_COLORS.pending,
                    )}
                >
                    {item.status}
                </span>
            </CardHeader>

            <CardContent className="flex flex-col gap-3">
                {/* Editable task details */}
                <input
                    type="text"
                    className="w-full rounded-md border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                    placeholder="Task description..."
                    value={item.edited_content}
                    onChange={(e) =>
                        onUpdate(index, { edited_content: e.target.value })
                    }
                    aria-label={`Action item ${index + 1} description`}
                />

                <div className="flex items-center gap-2">
                    {/* Priority badge (read-only) */}
                    <span
                        className={cn(
                            "rounded px-1.5 py-0.5 text-xs font-medium",
                            PRIORITY_COLORS[item.priority] ??
                            PRIORITY_COLORS.medium,
                        )}
                    >
                        {item.priority}
                    </span>

                    {/* Deadline (read-only) */}
                    {item.deadline && (
                        <span className="text-xs text-surface-500 dark:text-surface-dark-400">
                            deadline: {item.deadline}
                        </span>
                    )}

                    {/* View Source */}
                    <div className="ml-auto">
                        <SourceButton
                            document={item.source_document}
                            section={item.source_section}
                            onClick={() =>
                                onViewSource(
                                    docId,
                                    item.source_document,
                                    item.source_section,
                                )
                            }
                        />
                    </div>
                </div>

                {/* Approve / Reject buttons */}
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={() =>
                            onUpdate(index, { status: "approved" })
                        }
                        disabled={item.status === "approved"}
                        className="flex-1 rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-emerald-700 dark:hover:bg-emerald-600"
                    >
                        ✓ Approve
                    </button>
                    <button
                        type="button"
                        onClick={() =>
                            onUpdate(index, { status: "rejected" })
                        }
                        disabled={item.status === "rejected"}
                        className="flex-1 rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-red-700 dark:hover:bg-red-600"
                    >
                        ✗ Reject
                    </button>
                </div>
            </CardContent>
        </Card>
    );
}

// ── Document Viewer (right pane) ─────────────────────────────────────────────

function DocumentViewer({ source }: { source: SelectedSource | null }) {
    const [text, setText] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch document text whenever the selected source changes
    useEffect(() => {
        if (!source) {
            setText(null);
            setError(null);
            return;
        }
        setLoading(true);
        setError(null);
        fetchDocumentText(source.documentId)
            .then((data) => setText(data.content))
            .catch(() => setError("Failed to load document text."))
            .finally(() => setLoading(false));
    }, [source]);

    // ── Empty state ─────────────────────────────────────────────────────
    if (!source) {
        return (
            <div className="flex h-full items-center justify-center px-6">
                <div className="text-center">
                    <svg
                        className="mx-auto mb-3 h-10 w-10 text-surface-300 dark:text-surface-dark-600"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                    <p className="text-sm text-surface-400 dark:text-surface-dark-500">
                        Click &ldquo;View Source&rdquo; on any item to see the
                        original document here.
                    </p>
                </div>
            </div>
        );
    }

    // ── Loading / Error states ──────────────────────────────────────────
    if (loading) {
        return (
            <div className="flex h-full items-center justify-center">
                <p className="text-sm text-surface-400 dark:text-surface-dark-500">
                    Loading document...
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex h-full items-center justify-center px-6">
                <p className="text-sm text-red-500">{error}</p>
            </div>
        );
    }

    // ── Render document text with section highlighting ──────────────────
    // Split into paragraphs and highlight any that contain the section tag
    const paragraphs = (text ?? "").split("\n\n").filter(Boolean);

    return (
        <div className="h-full overflow-y-auto">
            {/* Header bar */}
            <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-surface-200 bg-surface-50 px-4 py-3 dark:border-surface-dark-700 dark:bg-surface-dark-900">
                <svg
                    className="h-4 w-4 text-surface-400 dark:text-surface-dark-500"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
                <span className="text-sm font-medium text-surface-700 dark:text-surface-dark-200">
                    {source.documentName}
                </span>
                <span className="rounded bg-yellow-200 px-1.5 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-800 dark:text-yellow-200">
                    § {source.section}
                </span>
            </div>

            {/* Document body */}
            <div className="px-4 py-3 font-mono text-sm leading-relaxed text-surface-700 dark:text-surface-dark-200">
                {paragraphs.map((para, i) => {
                    // Highlight paragraph if it contains the section identifier
                    const isHighlighted = para.includes(source.section);
                    return (
                        <p
                            key={i}
                            className={cn(
                                "mb-3 rounded px-3 py-2 transition-colors",
                                isHighlighted &&
                                "bg-yellow-100 dark:bg-yellow-900/30",
                            )}
                        >
                            {para}
                        </p>
                    );
                })}
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Main Component
// ═══════════════════════════════════════════════════════════════════════════════

interface ProjectReviewProps {
    result: ExtractionResult;
    documents: ProjectDocumentRef[];
}

export default function ProjectReview({
    result,
    documents,
}: ProjectReviewProps) {
    // ── State ────────────────────────────────────────────────────────────
    const [reviewState, setReviewState] = useState<ReviewState>(() =>
        initReviewState(result),
    );
    const [selectedSource, setSelectedSource] =
        useState<SelectedSource | null>(null);

    // Build filename → { id, filename } lookup map for source navigation
    const docLookup = useMemo(() => buildDocLookup(documents), [documents]);

    // ── Handlers ─────────────────────────────────────────────────────────

    /** Update a Fact card by index with a partial patch. */
    const updateFact = useCallback(
        (index: number, patch: Partial<FactReviewItem>) => {
            setReviewState((prev) => {
                const facts = [...prev.facts];
                facts[index] = { ...facts[index], ...patch };
                return { ...prev, facts };
            });
        },
        [],
    );

    /** Update a Conflict card by index with a partial patch. */
    const updateConflict = useCallback(
        (index: number, patch: Partial<ConflictReviewItem>) => {
            setReviewState((prev) => {
                const conflicts = [...prev.conflicts];
                conflicts[index] = { ...conflicts[index], ...patch };
                return { ...prev, conflicts };
            });
        },
        [],
    );

    /** Update an Action Item card by index with a partial patch. */
    const updateActionItem = useCallback(
        (index: number, patch: Partial<ActionReviewItem>) => {
            setReviewState((prev) => {
                const action_items = [...prev.action_items];
                action_items[index] = { ...action_items[index], ...patch };
                return { ...prev, action_items };
            });
        },
        [],
    );

    /** Set the selected source for the right pane document viewer. */
    const handleViewSource = useCallback(
        (docId: string, docName: string, section: string) => {
            setSelectedSource({ documentId: docId, documentName: docName, section });
        },
        [],
    );

    /** Log the full review state as JSON to console. */
    const handleFinalize = useCallback(() => {
        console.log(
            "Finalize & Save Action Summary:",
            JSON.stringify(reviewState, null, 2),
        );
    }, [reviewState]);

    // ── Render ───────────────────────────────────────────────────────────
    return (
        <Split
            className="flex h-[calc(100vh-4rem)]"
            sizes={[50, 50]}
            minSize={[320, 320]}
            gutterSize={6}
            gutter={() => {
                // Create a styled gutter handle element
                const gutter = document.createElement("div");
                gutter.className =
                    "group/gutter flex cursor-col-resize items-center justify-center bg-surface-100 hover:bg-primary-100 dark:bg-surface-dark-800 dark:hover:bg-primary-900/30 transition-colors";
                const handle = document.createElement("div");
                handle.className =
                    "h-8 w-1 rounded-full bg-surface-300 group-hover/gutter:bg-primary-400 dark:bg-surface-dark-600 dark:group-hover/gutter:bg-primary-500 transition-colors";
                gutter.appendChild(handle);
                return gutter;
            }}
        >
            {/* ── Left Pane: Review Cards ────────────────────────────────── */}
            <div className="flex h-full flex-col overflow-hidden">
                {/* Header with Finalize button */}
                <div className="flex shrink-0 items-center justify-between border-b border-surface-200 bg-surface-50 px-4 py-3 dark:border-surface-dark-700 dark:bg-surface-dark-900">
                    <h2 className="text-sm font-semibold text-surface-800 dark:text-surface-dark-100">
                        Review Workspace
                    </h2>
                    <button
                        type="button"
                        onClick={handleFinalize}
                        className="rounded-lg bg-primary-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary-700 dark:bg-primary-500 dark:hover:bg-primary-400 dark:text-surface-dark-950"
                    >
                        Finalize &amp; Save Action Summary
                    </button>
                </div>

                {/* Scrollable card list */}
                <div className="flex-1 overflow-y-auto px-4 py-4">
                    <div className="flex flex-col gap-4">
                        {/* ── Facts Section ──────────────────────────────── */}
                        {reviewState.facts.length > 0 && (
                            <>
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-dark-500">
                                    Facts ({reviewState.facts.length})
                                </h3>
                                {reviewState.facts.map((item, i) => {
                                    const docRef = docLookup.get(
                                        item.source_document,
                                    );
                                    return (
                                        <FactCard
                                            key={i}
                                            item={item}
                                            index={i}
                                            docId={docRef?.id ?? ""}
                                            onUpdate={updateFact}
                                            onViewSource={
                                                handleViewSource
                                            }
                                        />
                                    );
                                })}
                            </>
                        )}

                        {/* ── Conflicts Section ──────────────────────────── */}
                        {reviewState.conflicts.length > 0 && (
                            <>
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-dark-500">
                                    Conflicts ({reviewState.conflicts.length})
                                </h3>
                                {reviewState.conflicts.map((item, i) => {
                                    const docRefA = docLookup.get(
                                        item.document_a,
                                    );
                                    const docRefB = docLookup.get(
                                        item.document_b,
                                    );
                                    return (
                                        <ConflictCard
                                            key={i}
                                            item={item}
                                            index={i}
                                            docIdA={docRefA?.id ?? ""}
                                            docIdB={docRefB?.id ?? ""}
                                            onUpdate={updateConflict}
                                            onViewSource={
                                                handleViewSource
                                            }
                                        />
                                    );
                                })}
                            </>
                        )}

                        {/* ── Action Items Section ───────────────────────── */}
                        {reviewState.action_items.length > 0 && (
                            <>
                                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-400 dark:text-surface-dark-500">
                                    Action Items (
                                    {reviewState.action_items.length})
                                </h3>
                                {reviewState.action_items.map((item, i) => {
                                    const docRef = docLookup.get(
                                        item.source_document,
                                    );
                                    return (
                                        <ActionItemCard
                                            key={i}
                                            item={item}
                                            index={i}
                                            docId={docRef?.id ?? ""}
                                            onUpdate={updateActionItem}
                                            onViewSource={
                                                handleViewSource
                                            }
                                        />
                                    );
                                })}
                            </>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Right Pane: Document Viewer ────────────────────────────── */}
            <div className="h-full overflow-hidden bg-surface-50 dark:bg-surface-dark-900">
                <DocumentViewer source={selectedSource} />
            </div>
        </Split>
    );
}
