// ── Project Review Workspace ──────────────────────────────────────────────────
// Interactive split-screen workspace for reviewing AI-extracted items.
// Tabbed left pane: Facts | Conflicts | Actions with lightweight collapsible cards.
// Right pane: document text viewer with section highlighting.
//
// Architecture:
//   • Receives ExtractionResult + ProjectDocumentRef[] as props
//   • Transforms raw extraction data into mutable review state on mount
//   • Pure CSS accordion cards (grid-rows trick, no runtime animation library)
//   • react-split for the horizontal divider, height inherited from parent

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Split from "react-split";
import { motion, AnimatePresence } from "motion/react";
import { cn } from "../components/utils";
import { fetchDocumentText } from "../api/knowledge";
import apiClient from "../api/client";
import { useParams } from "react-router-dom";
import ProjectNavbar from "../components/ProjectNavbar";
import {
    getProject,
    saveReview,
    type ExtractionResult,
    type Fact,
    type DocumentConflict,
    type ActionItem,
    type ProjectDocumentRef,
    type ProjectResponse,
    type ReviewSummary,
} from "../api/project";

// ═══════════════════════════════════════════════════════════════════════════════
//  Types
// ═══════════════════════════════════════════════════════════════════════════════

interface FactReviewItem extends Fact {
    classification: "fact" | "assumption" | "unresolved";
}

interface ConflictReviewItem extends DocumentConflict {
    resolution_note: string;
    resolved: boolean;
}

interface ActionReviewItem extends ActionItem {
    status: "pending" | "approved" | "rejected";
    edited_content: string;
}

interface ReviewState {
    facts: FactReviewItem[];
    conflicts: ConflictReviewItem[];
    action_items: ActionReviewItem[];
}

interface SelectedSource {
    documentId: string;
    documentName: string;
    section: string;
    fileType: string; // drives rendering: "pdf" → iframe, "docx"/"txt" → paragraphs
}

type TabId = "facts" | "conflicts" | "actions";

// ═══════════════════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════════════════

function buildDocLookup(
    docs: ProjectDocumentRef[],
): Map<string, { id: string; filename: string; file_type: string }> {
    const map = new Map<string, { id: string; filename: string; file_type: string }>();
    for (const d of docs) map.set(d.filename, { id: d.id, filename: d.filename, file_type: d.file_type });
    return map;
}

function initReviewState(result: ExtractionResult): ReviewState {
    return {
        facts: result.facts.map((f) => ({ ...f, classification: "fact" as const })),
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

// ── Colour maps ──────────────────────────────────────────────────────────────

const CLASSIFICATION_COLORS: Record<string, string> = {
    fact: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
    assumption: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    unresolved: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
};


const PRIORITY_COLORS: Record<string, string> = {
    high: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
    medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

// ═══════════════════════════════════════════════════════════════════════════════
//  Shared Sub-components
// ═══════════════════════════════════════════════════════════════════════════════

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
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            {document} · {section}
        </button>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Merged Header — tabs + compact summary row (replaces old StatsBar + TabBar)
// ═══════════════════════════════════════════════════════════════════════════════

function ReviewHeader({
    active,
    onTab,
    state,
}: {
    active: TabId;
    onTab: (t: TabId) => void;
    state: ReviewState;
}) {
    const tabs: { id: TabId; label: string; count: number }[] = [
        { id: "facts", label: "Facts", count: state.facts.length },
        { id: "conflicts", label: "Conflicts", count: state.conflicts.length },
        { id: "actions", label: "Actions", count: state.action_items.length },
    ];
    // Compact summary badges
    const pending = state.action_items.filter((a) => a.status === "pending").length;
    const unresolved = state.conflicts.filter((c) => !c.resolved).length;

    return (
        <div className="flex shrink-0 items-center gap-2 border-b border-surface-200 bg-surface-50/90 px-3 py-2 backdrop-blur dark:border-surface-dark-700 dark:bg-surface-dark-900/80">
            {/* Tab pills */}
            <div className="flex gap-1">
                {tabs.map((t) => (
                    <button
                        key={t.id}
                        type="button"
                        onClick={() => onTab(t.id)}
                        className={cn(
                            "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors",
                            active === t.id
                                ? "bg-white text-surface-800 shadow-sm ring-1 ring-surface-200 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:ring-surface-dark-700"
                                : "text-surface-500 hover:text-surface-700 dark:text-surface-dark-400 dark:hover:text-surface-dark-200",
                        )}
                    >
                        {t.label}
                        <span className={cn(
                            "rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none",
                            active === t.id
                                ? "bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300"
                                : "bg-surface-200 text-surface-500 dark:bg-surface-dark-700 dark:text-surface-dark-400",
                        )}>
                            {t.count}
                        </span>
                    </button>
                ))}
            </div>
            {/* Compact status summary */}
            <div className="ml-auto flex items-center gap-3 text-[11px] text-surface-500 dark:text-surface-dark-400">
                {unresolved > 0 && <span className="text-red-600 dark:text-red-400">{unresolved} unresolved</span>}
                {pending > 0 && <span className="text-amber-600 dark:text-amber-400">{pending} pending</span>}
                {unresolved === 0 && pending === 0 && (
                    <span className="text-emerald-600 dark:text-emerald-400">✓ all reviewed</span>
                )}
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Accordion Card — pure CSS expand/collapse via grid-rows trick
//  No motion library; no AnimatePresence. Snappy 200ms transition.
// ═══════════════════════════════════════════════════════════════════════════════

function AccordionCard({
    open,
    onToggle,
    header,
    children,
    className,
}: {
    open: boolean;
    onToggle: () => void;
    header: React.ReactNode;
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div
            className={cn(
                "cursor-pointer rounded-lg border border-surface-200 bg-white transition-shadow hover:shadow-sm dark:border-surface-dark-700 dark:bg-surface-dark-900",
                className,
            )}
            onClick={onToggle}
        >
            {/* Header row — always visible */}
            <div className="flex items-center gap-2 px-3 py-2">
                {header}
                {/* Chevron — rotates via CSS transition when open */}
                <svg
                    className={cn(
                        "ml-auto h-3.5 w-3.5 shrink-0 text-surface-400 transition-transform duration-200 dark:text-surface-dark-500",
                        open && "rotate-180",
                    )}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <polyline points="6,9 12,15 18,9" />
                </svg>
            </div>

            {/* Expandable body — CSS grid-rows transition */}
            <div
                className={cn(
                    "grid transition-[grid-template-rows] duration-200 ease-in-out",
                    open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                )}
            >
                <div className="overflow-hidden">
                    <div
                        className="flex flex-col gap-2 px-3 pb-3 pt-0"
                        onClick={(e) => e.stopPropagation()} // Prevent toggle when editing
                    >
                        {children}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Fact Card — accordion with classification reclass + confidence
// ═══════════════════════════════════════════════════════════════════════════════

function FactCard({
    item,
    index,
    open,
    docId,
    docType,
    onToggle,
    onUpdate,
    onViewSource,
}: {
    item: FactReviewItem;
    index: number;
    open: boolean;
    docId: string;
    onToggle: () => void;
    onUpdate: (index: number, patch: Partial<FactReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string, fileType: string) => void;
    docType: string;
}) {
    // Truncate content for collapsed header display
    const truncated = item.content.length > 80 ? item.content.slice(0, 80) + "\u2026" : item.content;

    return (
        <AccordionCard
            open={open}
            onToggle={onToggle}
            header={
                <>
                    {/* Small coloured dot instead of thick left border */}
                    <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-400 dark:bg-emerald-500" />
                    <span className="truncate text-xs text-surface-700 dark:text-surface-dark-200">
                        {open ? item.content : truncated}
                    </span>
                    {/* Classification tag — capitalized, left-aligned */}
                    <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", CLASSIFICATION_COLORS[item.classification] ?? CLASSIFICATION_COLORS.fact)}>
                        {item.classification.charAt(0).toUpperCase() + item.classification.slice(1)}
                    </span>
                </>
            }
        >
            <textarea
                className="w-full resize-y rounded-md border border-surface-200 bg-surface-50 px-3 py-2 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                rows={3}
                value={item.content}
                onChange={(e) => onUpdate(index, { content: e.target.value })}
                aria-label={`Fact ${index + 1} content`}
            />
            <div className="flex items-center gap-2">
                <select
                    className="rounded-md border border-surface-200 bg-surface-50 px-2 py-1 text-xs text-surface-700 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-200"
                    value={item.classification}
                    onChange={(e) => onUpdate(index, { classification: e.target.value as FactReviewItem["classification"] })}
                    aria-label="Reclassify item"
                >
                    <option value="fact">Fact</option>
                    <option value="assumption">Assumption</option>
                    <option value="unresolved">Unresolved</option>
                </select>
                <span className="rounded bg-surface-100 px-1.5 py-0.5 text-xs text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                    {item.confidence}
                </span>
                <div className="ml-auto">
                    <SourceButton document={item.source_document} section={item.source_section} onClick={() => onViewSource(docId, item.source_document, item.source_section, docType)} />
                </div>
            </div>
        </AccordionCard>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Conflict Card — accordion with side-by-side statements
// ═══════════════════════════════════════════════════════════════════════════════

function ConflictCard({
    item,
    index,
    open,
    docIdA,
    docIdB,
    docTypeA,
    docTypeB,
    onToggle,
    onUpdate,
    onViewSource,
}: {
    item: ConflictReviewItem;
    index: number;
    open: boolean;
    docIdA: string;
    docIdB: string;
    onToggle: () => void;
    onUpdate: (index: number, patch: Partial<ConflictReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string, fileType: string) => void;
    docTypeA: string;
    docTypeB: string;
}) {
    const truncated = item.statement_a.length > 60 ? item.statement_a.slice(0, 60) + "\u2026" : item.statement_a;

    return (
        <AccordionCard
            open={open}
            onToggle={onToggle}
            header={
                <>
                    {/* Status dot — resolved = green, unresolved = red */}
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", item.resolved ? "bg-emerald-400 dark:bg-emerald-500" : "bg-red-400 dark:bg-red-500")} />
                    <span className="truncate text-xs text-surface-700 dark:text-surface-dark-200">
                        {open ? item.statement_a : truncated}
                    </span>
                    {/* Resolved/unresolved toggle button */}
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onUpdate(index, { resolved: !item.resolved }); }}
                        className={cn(
                            "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                            item.resolved
                                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
                                : "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
                        )}
                    >
                        {item.resolved ? "Resolved \u2713" : "Unresolved"}
                    </button>
                </>
            }
        >
            <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-red-200 bg-red-50/50 p-3 dark:border-red-800 dark:bg-red-950/20">
                    <p className="mb-2 text-xs font-medium text-red-600 dark:text-red-400">Statement A — {item.document_a}</p>
                    <blockquote className="text-xs leading-relaxed text-surface-700 dark:text-surface-dark-200">{item.statement_a}</blockquote>
                    <button type="button" onClick={() => onViewSource(docIdA, item.document_a, item.section_a, docTypeA)} className="mt-2 text-xs text-primary-500 hover:underline">View source · {item.section_a}</button>
                </div>
                <div className="rounded-md border border-red-200 bg-red-50/50 p-3 dark:border-red-800 dark:bg-red-950/20">
                    <p className="mb-2 text-xs font-medium text-red-600 dark:text-red-400">Statement B — {item.document_b}</p>
                    <blockquote className="text-xs leading-relaxed text-surface-700 dark:text-surface-dark-200">{item.statement_b}</blockquote>
                    <button type="button" onClick={() => onViewSource(docIdB, item.document_b, item.section_b, docTypeB)} className="mt-2 text-xs text-primary-500 hover:underline">View source · {item.section_b}</button>
                </div>
            </div>
            <input
                type="text"
                className="w-full rounded-md border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                placeholder="Resolution note..."
                value={item.resolution_note}
                onChange={(e) => onUpdate(index, { resolution_note: e.target.value })}
                aria-label={`Resolution note for conflict ${index + 1}`}
            />
            {/* Resolve button — marks conflict as resolved after filling the note */}
            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onUpdate(index, { resolved: true }); }}
                    disabled={item.resolved}
                    className={cn(
                        "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                        item.resolved
                            ? "cursor-not-allowed bg-surface-100 text-surface-400 dark:bg-surface-dark-800 dark:text-surface-dark-500"
                            : "bg-emerald-600 text-white hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:text-white",
                    )}
                >
                    {item.resolved ? "Resolved \u2713" : "Resolve Conflict"}
                </button>
                {!item.resolved && !item.resolution_note.trim() && (
                    <span className="text-[10px] text-surface-400 dark:text-surface-dark-500">Add a resolution note above first</span>
                )}
            </div>
            {item.resolution_suggestion && (
                <p className="rounded-md bg-surface-100 px-3 py-2 text-xs text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                    💡 AI suggestion: {item.resolution_suggestion}
                </p>
            )}
        </AccordionCard>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Action Item Card — single cycle button replaces old approve/reject
// ═══════════════════════════════════════════════════════════════════════════════

function ActionItemCard({
    item,
    index,
    open,
    docId,
    docType,
    onToggle,
    onUpdate,
    onViewSource,
}: {
    item: ActionReviewItem;
    index: number;
    open: boolean;
    docId: string;
    onToggle: () => void;
    onUpdate: (index: number, patch: Partial<ActionReviewItem>) => void;
    onViewSource: (docId: string, docName: string, section: string, fileType: string) => void;
    docType: string;
}) {
    const truncated = item.edited_content.length > 70 ? item.edited_content.slice(0, 70) + "\u2026" : item.edited_content;
    const statusDot: Record<ActionReviewItem["status"], string> = {
        pending: "bg-blue-400 dark:bg-blue-500",
        approved: "bg-emerald-400 dark:bg-emerald-500",
        rejected: "bg-red-400 dark:bg-red-500",
    };

    return (
        <AccordionCard
            open={open}
            onToggle={onToggle}
            header={
                <>
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", statusDot[item.status])} />
                    <span className={cn("truncate text-xs", item.status === "rejected" && "line-through opacity-60")}>
                        {open ? item.edited_content : truncated}
                    </span>
                    {/* Dropdown for status — consistent with Facts tab */}
                    <select
                        className="shrink-0 rounded-md border border-surface-200 bg-surface-50 px-2 py-0.5 text-[10px] font-medium text-surface-700 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-200"
                        value={item.status}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => { e.stopPropagation(); onUpdate(index, { status: e.target.value as ActionReviewItem["status"] }); }}
                        aria-label="Action status"
                    >
                        <option value="pending">Pending</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                    </select>
                </>
            }
        >
            <input
                type="text"
                className="w-full rounded-md border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400 dark:border-surface-dark-700 dark:bg-surface-dark-800 dark:text-surface-dark-100 dark:placeholder:text-surface-dark-500"
                placeholder="Task description..."
                value={item.edited_content}
                onChange={(e) => onUpdate(index, { edited_content: e.target.value })}
                aria-label={`Action item ${index + 1} description`}
            />
            <div className="flex items-center gap-2">
                <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", PRIORITY_COLORS[item.priority] ?? PRIORITY_COLORS.medium)}>{item.priority}</span>
                {item.deadline && <span className="text-xs text-surface-500 dark:text-surface-dark-400">deadline: {item.deadline}</span>}
                <div className="ml-auto">
                    <SourceButton document={item.source_document} section={item.source_section} onClick={() => onViewSource(docId, item.source_document, item.source_section, docType)} />
                </div>
            </div>
        </AccordionCard>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Document Viewer (right pane)
//  PDF: rendered natively via iframe (blob URL, browser handles inline).
//  DOCX/TXT: reconstructed text from backend chunks, displayed as styled
//  paragraphs with section highlighting and auto-scroll.
// ═══════════════════════════════════════════════════════════════════════════════

function DocumentViewer({ source }: { source: SelectedSource | null }) {
    const [content, setContent] = useState<string | null>(null); // text for DOCX/TXT; blob URL for PDF
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const paraRefs = useRef<Map<number, HTMLParagraphElement>>(new Map());

    useEffect(() => {
        if (!source) {
            setContent(null);
            setError(null);
            return;
        }

        setLoading(true);
        setError(null);
        setContent(null);
        paraRefs.current.clear();

        // PDF: fetch as blob → object URL → render in iframe
        if (source.fileType === "pdf") {
            let objectUrl: string | null = null;
            apiClient
                .get(`/knowledge/documents/${source.documentId}`, { responseType: "blob" })
                .then((res) => {
                    const blob = new Blob([res.data], { type: "application/pdf" });
                    objectUrl = URL.createObjectURL(blob);
                    setContent(objectUrl);
                })
                .catch(() => setError("Failed to load PDF."))
                .finally(() => setLoading(false));
            // Revoke the object URL when source changes or component unmounts
            return () => {
                if (objectUrl) URL.revokeObjectURL(objectUrl);
            };
        }

        // DOCX / TXT: fetch reconstructed text from backend chunks
        fetchDocumentText(source.documentId)
            .then((data) => setContent(data.content))
            .catch(() => setError("Failed to load document text."))
            .finally(() => setLoading(false));
    }, [source?.documentId]); // eslint-disable-line react-hooks/exhaustive-deps

    // Auto-scroll to the first highlighted paragraph after text loads (DOCX/TXT only)
    useEffect(() => {
        if (!content || loading || source?.fileType === "pdf" || !scrollRef.current) return;
        const paragraphs = content.split("\n\n").filter(Boolean);
        const targetIdx = paragraphs.findIndex((p) => p.includes(source!.section));
        if (targetIdx === -1) return;
        const el = paraRefs.current.get(targetIdx);
        if (el) {
            requestAnimationFrame(() => {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
            });
        }
    }, [content, loading, source]);

    // ── Empty state ─────────────────────────────────────────────────────
    if (!source) {
        return (
            <div className="flex h-full items-center justify-center bg-surface-50 dark:bg-surface-dark-950">
                <div className="text-center">
                    <svg className="mx-auto mb-4 h-12 w-12 text-surface-300 dark:text-surface-dark-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                    <p className="text-sm text-surface-400 dark:text-surface-dark-500">
                        Click "View Source" on any item to see the original document here.
                    </p>
                </div>
            </div>
        );
    }

    if (loading || !content) {
        return (
            <div className="flex h-full items-center justify-center bg-surface-50 dark:bg-surface-dark-950">
                <p className="text-sm text-surface-400 dark:text-surface-dark-500">Loading document...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex h-full items-center justify-center bg-surface-50 px-6 dark:bg-surface-dark-950">
                <p className="text-sm text-red-500">{error}</p>
            </div>
        );
    }

    // ── Render ───────────────────────────────────────────────────────────
    const typeLabel = source.fileType.toUpperCase();

    // PDF: render natively via iframe (browser handles inline PDF viewing)
    if (source.fileType === "pdf") {
        return (
            <div className="flex h-full flex-col overflow-hidden">
                <div className="flex shrink-0 items-center gap-2 border-b border-surface-200 bg-white/90 px-4 py-2 backdrop-blur dark:border-surface-dark-700 dark:bg-surface-dark-950/90">
                    <svg className="h-4 w-4 text-surface-400 dark:text-surface-dark-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                    <span className="truncate text-sm font-medium text-surface-700 dark:text-surface-dark-200">{source.documentName}</span>
                    <span className="shrink-0 rounded bg-surface-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-surface-500 dark:bg-surface-dark-700 dark:text-surface-dark-400">{typeLabel}</span>
                    <span className="shrink-0 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700 dark:bg-yellow-800/60 dark:text-yellow-200">§ {source.section}</span>
                </div>
                <iframe src={content!} className="h-full w-full border-0" title={source.documentName} />
            </div>
        );
    }

    // DOCX / TXT: reconstructed text with section highlighting + auto-scroll
    const paragraphs = (content ?? "").split("\n\n").filter(Boolean);

    return (
        <div className="flex h-full flex-col overflow-hidden bg-white dark:bg-surface-dark-950">
            {/* Header bar */}
            <div className="flex shrink-0 items-center gap-2 border-b border-surface-200 bg-surface-50/90 px-4 py-2.5 backdrop-blur dark:border-surface-dark-700 dark:bg-surface-dark-900/80">
                <svg className="h-4 w-4 text-surface-400 dark:text-surface-dark-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
                <span className="truncate text-sm font-medium text-surface-700 dark:text-surface-dark-200">{source.documentName}</span>
                <span className="shrink-0 rounded bg-surface-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-surface-500 dark:bg-surface-dark-700 dark:text-surface-dark-400">{typeLabel}</span>
                <span className="shrink-0 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700 dark:bg-yellow-800/60 dark:text-yellow-200">§ {source.section}</span>
            </div>

            {/* Document body — auto-scrolls to highlighted paragraph */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 text-sm leading-relaxed text-surface-700 dark:text-surface-dark-200">
                {paragraphs.map((para, i) => {
                    const isHighlighted = para.includes(source.section);
                    return (
                        <p
                            key={i}
                            ref={(el) => { if (el) paraRefs.current.set(i, el); }}
                            className={cn(
                                "mb-3 rounded-lg px-3 py-2",
                                isHighlighted
                                    ? "bg-yellow-50 ring-1 ring-yellow-200 dark:bg-yellow-900/20 dark:ring-yellow-800/50"
                                    : "",
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

export default function ProjectReview() {
    const { id } = useParams<{ id: string }>();
    const [project, setProject] = useState<ProjectResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!id) return;
        setLoading(true);
        setError(null);
        getProject(id)
            .then(p => setProject(p))
            .catch(() => setError("Failed to load project."))
            .finally(() => setLoading(false));
    }, [id]);

    if (loading) {
        return (
            <div className="flex h-full flex-col">
                {id && <ProjectNavbar projectId={id} hasAnalysis={false} />}
                <div className="flex flex-1 items-center justify-center text-sm text-surface-500">Loading review...</div>
            </div>
        );
    }

    if (error || !project || !project.analysis_result) {
        return (
            <div className="flex h-full flex-col">
                {id && <ProjectNavbar projectId={id} hasAnalysis={!!project?.analysis_result} />}
                <div className="flex flex-1 items-center justify-center text-sm text-red-500">{error || "Analysis not found."}</div>
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col">
            <ProjectNavbar projectId={id!} hasAnalysis={true} />
            <div className="flex-1 overflow-hidden">
                <ProjectReviewWorkspace projectId={id!} result={project.analysis_result} reviewSummary={project.review_summary} documents={project.documents} />
            </div>
        </div>
    );
}

interface ProjectReviewProps {
    projectId: string;
    result: ExtractionResult;
    reviewSummary?: ReviewSummary | null;
    documents: ProjectDocumentRef[];
}

function ProjectReviewWorkspace({ projectId, result, reviewSummary, documents }: ProjectReviewProps) {
    const [reviewState, setReviewState] = useState<ReviewState>(() => {
        if (reviewSummary) {
            // The saved summary perfectly matches ReviewState structure
            return reviewSummary as unknown as ReviewState;
        }
        return initReviewState(result);
    });
    const [selectedSource, setSelectedSource] = useState<SelectedSource | null>(null);
    const [activeTab, setActiveTab] = useState<TabId>("facts");
    const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());

    const docLookup = useMemo(() => buildDocLookup(documents), [documents]);

    // Auto-select initial tab based on data availability
    useEffect(() => {
        if (reviewState.facts.length === 0 && reviewState.conflicts.length > 0) setActiveTab("conflicts");
        else if (reviewState.facts.length === 0 && reviewState.conflicts.length === 0 && reviewState.action_items.length > 0) setActiveTab("actions");
    }, []);

    // ── Handlers ─────────────────────────────────────────────────────────

    const updateFact = useCallback((index: number, patch: Partial<FactReviewItem>) => {
        setReviewState((prev) => {
            const facts = [...prev.facts];
            facts[index] = { ...facts[index], ...patch };
            return { ...prev, facts };
        });
    }, []);

    const updateConflict = useCallback((index: number, patch: Partial<ConflictReviewItem>) => {
        setReviewState((prev) => {
            const conflicts = [...prev.conflicts];
            conflicts[index] = { ...conflicts[index], ...patch };
            return { ...prev, conflicts };
        });
    }, []);

    const updateActionItem = useCallback((index: number, patch: Partial<ActionReviewItem>) => {
        setReviewState((prev) => {
            const action_items = [...prev.action_items];
            action_items[index] = { ...action_items[index], ...patch };
            return { ...prev, action_items };
        });
    }, []);

    const handleViewSource = useCallback((docId: string, docName: string, section: string, fileType: string) => {
        setSelectedSource({ documentId: docId, documentName: docName, section, fileType });
    }, []);

    const toggleCard = useCallback((index: number) => {
        setExpandedCards((prev) => {
            const next = new Set(prev);
            if (next.has(index)) next.delete(index); else next.add(index);
            return next;
        });
    }, []);

    // ── Save state ───────────────────────────────────────────────────────
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<"idle" | "success" | "error">("idle");

    const handleFinalize = useCallback(async () => {
        if (!projectId) return;
        setSaving(true);
        setSaveStatus("idle");
        try {
            await saveReview(projectId, {
                facts: reviewState.facts,
                conflicts: reviewState.conflicts,
                action_items: reviewState.action_items,
            });
            setSaveStatus("success");
        } catch {
            setSaveStatus("error");
        } finally {
            setSaving(false);
        }
    }, [projectId, reviewState]);

    // ── Computed ─────────────────────────────────────────────────────────

    const pendingCount = reviewState.action_items.filter((a) => a.status === "pending").length;
    const unresolvedCount = reviewState.conflicts.filter((c) => !c.resolved).length;

    // ── Render ───────────────────────────────────────────────────────────
    return (
        <Split
            className="flex h-full"
            sizes={[50, 50]}
            minSize={[300, 300]}
            gutterSize={6}
            gutterStyle={() => ({
                backgroundColor: "transparent",
            })}
            dragInterval={1}
        >
            {/* ── Left Pane: Review Workspace ───────────────────────────── */}
            <div className="flex h-full flex-col overflow-hidden bg-surface-50 dark:bg-surface-dark-950">
                <ReviewHeader active={activeTab} onTab={setActiveTab} state={reviewState} />

                {/* Card list */}
                <div className="flex-1 overflow-y-auto px-2.5 py-2">
                    <AnimatePresence mode="wait">
                        {/* ── Facts Tab ──────────────────────────────── */}
                        {activeTab === "facts" && (
                            <motion.div
                                key="facts"
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -8 }}
                                transition={{ duration: 0.15 }}
                                className="flex flex-col gap-1.5"
                            >
                                {reviewState.facts.length === 0 && (
                                    <p className="py-8 text-center text-xs text-surface-400 dark:text-surface-dark-500">No facts extracted.</p>
                                )}
                                {reviewState.facts.map((item, i) => {
                                    const docRef = docLookup.get(item.source_document);
                                    return (
                                        <FactCard
                                            key={i} item={item} index={i}
                                            open={expandedCards.has(i)}
                                            docId={docRef?.id ?? ""}
                                            docType={docRef?.file_type ?? ""}
                                            onToggle={() => toggleCard(i)}
                                            onUpdate={updateFact}
                                            onViewSource={handleViewSource}
                                        />
                                    );
                                })}
                            </motion.div>
                        )}

                        {/* ── Conflicts Tab ──────────────────────────── */}
                        {activeTab === "conflicts" && (
                            <motion.div
                                key="conflicts"
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -8 }}
                                transition={{ duration: 0.15 }}
                                className="flex flex-col gap-1.5"
                            >
                                {reviewState.conflicts.length === 0 && (
                                    <p className="py-8 text-center text-xs text-surface-400 dark:text-surface-dark-500">No conflicts detected between documents.</p>
                                )}
                                {reviewState.conflicts.map((item, i) => {
                                    const docRefA = docLookup.get(item.document_a);
                                    const docRefB = docLookup.get(item.document_b);
                                    return (
                                        <ConflictCard
                                            key={i} item={item} index={i}
                                            open={expandedCards.has(1000 + i)}
                                            docIdA={docRefA?.id ?? ""} docIdB={docRefB?.id ?? ""}
                                            docTypeA={docRefA?.file_type ?? ""} docTypeB={docRefB?.file_type ?? ""}
                                            onToggle={() => toggleCard(1000 + i)}
                                            onUpdate={updateConflict}
                                            onViewSource={handleViewSource}
                                        />
                                    );
                                })}
                            </motion.div>
                        )}

                        {/* ── Actions Tab ───────────────────────────── */}
                        {activeTab === "actions" && (
                            <motion.div
                                key="actions"
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -8 }}
                                transition={{ duration: 0.15 }}
                                className="flex flex-col gap-1.5"
                            >
                                {reviewState.action_items.length === 0 && (
                                    <p className="py-8 text-center text-xs text-surface-400 dark:text-surface-dark-500">No action items extracted.</p>
                                )}
                                {reviewState.action_items.map((item, i) => {
                                    const docRef = docLookup.get(item.source_document);
                                    return (
                                        <ActionItemCard
                                            key={i} item={item} index={i}
                                            open={expandedCards.has(2000 + i)}
                                            docId={docRef?.id ?? ""}
                                            docType={docRef?.file_type ?? ""}
                                            onToggle={() => toggleCard(2000 + i)}
                                            onUpdate={updateActionItem}
                                            onViewSource={handleViewSource}
                                        />
                                    );
                                })}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* ── Sticky Footer ────────────────────────────────────── */}
                <div className="flex shrink-0 items-center justify-between border-t border-surface-200 bg-surface-50/90 px-4 py-3 backdrop-blur dark:border-surface-dark-700 dark:bg-surface-dark-900/80">
                    <div className="flex gap-3 text-xs text-surface-500 dark:text-surface-dark-400">
                        {pendingCount > 0 && <span>🟡 {pendingCount} actions pending</span>}
                        {unresolvedCount > 0 && <span>🔴 {unresolvedCount} conflicts unresolved</span>}
                        {pendingCount === 0 && unresolvedCount === 0 && <span className="text-emerald-600 dark:text-emerald-400">✓ All items reviewed</span>}
                        {/* Save status feedback */}
                        {saveStatus === "success" && <span className="text-emerald-600 dark:text-emerald-400">✓ Saved</span>}
                        {saveStatus === "error" && <span className="text-red-500">✗ Save failed</span>}
                    </div>
                    <button
                        type="button"
                        onClick={handleFinalize}
                        disabled={saving}
                        className={cn(
                            "rounded-lg px-5 py-2 text-xs font-medium transition-colors",
                            saving
                                ? "cursor-not-allowed bg-surface-300 text-surface-500 dark:bg-surface-dark-700 dark:text-surface-dark-400"
                                : "bg-primary-600 text-white hover:bg-primary-700 dark:bg-primary-500 dark:hover:bg-primary-400 dark:text-surface-dark-950",
                        )}
                    >
                        {saving ? "Saving…" : "Finalize & Save"}
                    </button>
                </div>
            </div>

            {/* ── Right Pane: Document Viewer ──────────────────────────── */}
            <DocumentViewer source={selectedSource} />
        </Split>
    );
}
