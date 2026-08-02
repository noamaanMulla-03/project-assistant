// ── Project Results Page ─────────────────────────────────────────────────────
// Displays the structured extraction output from POST /projects/{id}/analyze.
// Each category renders as a section card; every item shows its source
// document and section for UI highlighting.
//
// Analysis results are cached in the DB — on mount, we first check whether
// the project already has a cached analysis_result (via GET /projects/{id}).
// If so, we display it instantly.  If not, we run the analysis.
// The "Redo Analysis" button forces a fresh LLM run via ?force=true.

import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { cn } from "../components/utils";
import ProjectNavbar from "../components/ProjectNavbar";
import {
    analyzeProject,
    getProject,
    type ExtractionResult,
    type ProjectResponse,
} from "../api/project";

// ── Confidence / Severity / Urgency colour maps ──────────────────────────────

const CONFIDENCE_COLORS: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
    medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    low: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
};

const SEVERITY_COLORS: Record<string, string> = {
    critical: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
    high: "bg-orange-100 text-orange-700 dark:bg-orange-950/30 dark:text-orange-400",
    medium: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    low: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

// ── Source Attribution Pill ──────────────────────────────────────────────────

function SourcePill({
    document,
    section,
}: {
    document: string;
    section: string;
}) {
    return (
        <span className="inline-flex items-center gap-1 rounded-md bg-surface-100 px-2 py-0.5 text-xs text-surface-500 dark:bg-surface-dark-800 dark:text-surface-dark-400">
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
        </span>
    );
}

// ── Section Card ─────────────────────────────────────────────────────────────

function SectionCard({
    title,
    icon,
    accentClass,
    children,
    count,
}: {
    title: string;
    icon: React.ReactNode;
    accentClass: string;
    children: React.ReactNode;
    count: number;
}) {
    return (
        <div className="rounded-xl border border-surface-200 bg-white dark:border-surface-dark-700 dark:bg-surface-dark-900">
            <div
                className={cn(
                    "flex items-center gap-2 rounded-t-xl border-b border-surface-200 px-5 py-3 dark:border-surface-dark-700",
                    accentClass,
                )}
            >
                {icon}
                <h3 className="text-sm font-semibold">{title}</h3>
                <span className="ml-auto rounded-full bg-white/50 px-2 py-0.5 text-xs font-medium dark:bg-black/20">
                    {count}
                </span>
            </div>
            <div className="divide-y divide-surface-100 dark:divide-surface-dark-800">
                {children}
            </div>
        </div>
    );
}

// ── Item Row ─────────────────────────────────────────────────────────────────

function ItemRow({
    source_document,
    source_section,
    badges,
    children,
}: {
    source_document: string;
    source_section: string;
    badges?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <div className="px-5 py-3">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <SourcePill document={source_document} section={source_section} />
                {badges}
            </div>
            <p className="text-sm leading-relaxed text-surface-700 dark:text-surface-dark-200">
                {children}
            </p>
        </div>
    );
}

// ── Icon Components ──────────────────────────────────────────────────────────

function FactIcon() {
    return (
        <svg className="h-4 w-4 text-emerald-600 dark:text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22,4 12,14.01 9,11.01" />
        </svg>
    );
}
function DecisionIcon() {
    return (
        <svg className="h-4 w-4 text-blue-600 dark:text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
        </svg>
    );
}
function RiskIcon() {
    return (
        <svg className="h-4 w-4 text-orange-600 dark:text-orange-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
    );
}
function QuestionIcon() {
    return (
        <svg className="h-4 w-4 text-violet-600 dark:text-violet-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
    );
}
function ConflictIcon() {
    return (
        <svg className="h-4 w-4 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
    );
}
function RepeatIcon() {
    return (
        <svg className="h-4 w-4 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="17,1 21,5 17,9" />
            <path d="M3 11V9a4 4 0 0 1 4-4h14" />
            <polyline points="7,23 3,19 7,15" />
            <path d="M21 13v2a4 4 0 0 1-4 4H3" />
        </svg>
    );
}
function Spinner() {
    return (
        <svg className="animate-spin h-5 w-5 text-indigo-500" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
    );
}

// ── Redo Analysis Icon ──────────────────────────────────────────────────────

function RedoIcon() {
    return (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23,4 23,10 17,10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Project Results Page
// ═══════════════════════════════════════════════════════════════════════════════

function normalizeExtraction(res: ExtractionResult | null): ExtractionResult | null {
    if (!res) return null;
    return {
        ...res,
        document_types: res.document_types ?? [],
        summary: res.summary ?? "",
        facts: res.facts ?? [],
        decisions: res.decisions ?? [],
        assumptions: res.assumptions ?? [],
        risks: res.risks ?? [],
        open_questions: res.open_questions ?? [],
        action_items: res.action_items ?? [],
        document_conflicts: res.document_conflicts ?? [],
        repeated_statements: res.repeated_statements ?? [],
        missing_actions: res.missing_actions ?? [],
        missing_questions: res.missing_questions ?? [],
    };
}

// ── Toast Notification ──────────────────────────────────────────────────────

function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
    useEffect(() => {
        const t = setTimeout(onDismiss, 4000);
        return () => clearTimeout(t);
    }, [onDismiss]);
    return (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 shadow-lg dark:border-amber-800 dark:bg-amber-950/70">
            <svg className="h-4 w-4 shrink-0 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span className="text-sm font-medium text-amber-800 dark:text-amber-200">{message}</span>
            <button onClick={onDismiss} className="ml-1 text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-200" aria-label="Dismiss">
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            </button>
        </div>
    );
}

export default function ProjectResults() {
    const { id } = useParams<{ id: string }>();
    const [result, setResult] = useState<ExtractionResult | null>(null);
    const [project, setProject] = useState<ProjectResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [redoing, setRedoing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [toast, setToast] = useState<string | null>(null);

    // ── Load project and use cached analysis or run fresh ──────────────
    useEffect(() => {
        if (!id) return;
        setLoading(true);
        setError(null);

        getProject(id)
            .then((proj) => {
                setProject(proj);
                // If cached analysis exists, use it directly
                if (proj.analysis_result) {
                    setResult(normalizeExtraction(proj.analysis_result));
                    setLoading(false);
                } else {
                    // No cached result — run analysis for the first time
                    return analyzeProject(id).then((extraction) => {
                        setResult(normalizeExtraction(extraction));
                        // Refresh project to get the now-cached result
                        return getProject(id).then(setProject);
                    });
                }
            })
            .catch((err: unknown) => {
                const detail =
                    (err as { response?: { data?: { detail?: string } } })?.response?.data
                        ?.detail ?? "Failed to load analysis results.";
                setError(detail);
            })
            .finally(() => setLoading(false));
    }, [id]);

    // ── Redo Analysis handler ──────────────────────────────────────────
    const handleRedo = async () => {
        if (!id) return;
        setRedoing(true);
        setError(null);
        try {
            const extraction = await analyzeProject(id, true);
            setResult(normalizeExtraction(extraction));
            // Refresh project — review_summary is now null on the server
            const updated = await getProject(id);
            setProject(updated);
            // Notify the user that the previous review was cleared
            setToast("Analysis updated — your previous review has been reset to match the new results.");
        } catch (err: unknown) {
            const detail =
                (err as { response?: { data?: { detail?: string } } })?.response?.data
                    ?.detail ?? "Redo analysis failed.";
            setError(detail);
        } finally {
            setRedoing(false);
        }
    };

    // ── Loading state ──────────────────────────────────────────────────────
    if (loading) {
        return (
            <div className="flex h-full flex-col">
                {/* Navbar shown even during loading */}
                {id && <ProjectNavbar projectId={id} hasAnalysis={false} />}
                <div className="flex min-h-[60vh] items-center justify-center px-4">
                    <div className="flex flex-col items-center gap-4">
                        <Spinner />
                        <p className="text-sm text-surface-500 dark:text-surface-dark-400">
                            Running AI analysis on your documents...
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    // ── Error state ────────────────────────────────────────────────────────
    if (error || !result) {
        return (
            <div className="flex h-full flex-col">
                {id && <ProjectNavbar projectId={id} hasAnalysis={!!project?.analysis_result} />}
                <div className="px-4 py-12">
                    <div className="mx-auto max-w-2xl">
                        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center dark:border-red-800 dark:bg-red-950/30">
                            <p className="text-sm text-red-700 dark:text-red-400">{error ?? "No results found."}</p>
                            <button
                                onClick={() => window.location.reload()}
                                className="mt-4 text-sm font-medium text-red-600 underline hover:no-underline dark:text-red-400"
                            >
                                Retry
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // ── Derived state for navbar ───────────────────────────────────────────
    const hasAnalysis = !!project?.analysis_result;

    // ── Results view ────────────────────────────────────────────────────────
    return (
        <div className="flex h-full flex-col">
            {/* Stage navbar */}
            {id && <ProjectNavbar projectId={id} hasAnalysis={hasAnalysis} />}

            {/* Toast notification */}
            {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}

            <div className="flex-1 overflow-y-auto px-4 py-12">
                <div className="mx-auto max-w-5xl">
                    {/* Header with Redo Analysis button */}
                    <div className="mb-8">
                        <div className="flex items-center justify-between">
                            <div>
                                <h1 className="text-2xl font-semibold text-surface-800 dark:text-surface-dark-100">
                                    Analysis Results
                                </h1>
                                <p className="mt-1 text-sm text-surface-700 dark:text-surface-dark-300">
                                    AI-extracted facts, decisions, risks, and policy gaps from your
                                    project documents. Every item is linked to its source.
                                </p>
                            </div>
                            {/* Redo Analysis button */}
                            <button
                                type="button"
                                onClick={handleRedo}
                                disabled={redoing}
                                className={cn(
                                    "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium transition-colors",
                                    redoing
                                        ? "cursor-not-allowed bg-surface-200 text-surface-400 dark:bg-surface-dark-800 dark:text-surface-dark-500"
                                        : "border border-surface-300 bg-white text-surface-600 hover:bg-surface-50 hover:text-surface-800 dark:border-surface-dark-600 dark:bg-surface-dark-800 dark:text-surface-dark-300 dark:hover:bg-surface-dark-700 dark:hover:text-surface-dark-100",
                                )}
                            >
                                {redoing ? (
                                    <>
                                        <Spinner /> Reanalyzing...
                                    </>
                                ) : (
                                    <>
                                        <RedoIcon /> Redo Analysis
                                    </>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Executive Summary */}
                    <div className="mb-8 rounded-xl border border-indigo-200 bg-indigo-50/50 p-6 dark:border-indigo-800 dark:bg-indigo-950/20">
                        <h2 className="mb-2 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
                            Executive Summary
                        </h2>
                        <div className="prose prose-sm max-w-none text-surface-700 dark:text-surface-dark-200 [&_h3]:mt-4 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-surface-900 dark:[&_h3]:text-surface-dark-100 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:mb-1 [&_strong]:font-semibold [&_p]:mb-2 [&_p]:leading-relaxed [&_em]:italic">
                            <ReactMarkdown>{result.summary}</ReactMarkdown>
                        </div>
                    </div>

                    {/* Document Types — per-document classification */}
                    {(result.document_types?.length ?? 0) > 0 && (
                        <div className="mb-8 rounded-xl border border-surface-200 bg-white p-5 dark:border-surface-dark-700 dark:bg-surface-dark-900">
                            <h2 className="mb-3 text-sm font-semibold text-surface-700 dark:text-surface-dark-200">
                                Document Types
                            </h2>
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-surface-100 text-left dark:border-surface-dark-800">
                                        <th className="pb-2 pr-4 text-xs font-medium text-surface-500 dark:text-surface-dark-400">Filename</th>
                                        <th className="pb-2 text-xs font-medium text-surface-500 dark:text-surface-dark-400">Identified Type</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(result.document_types ?? []).map((dt, i) => (

                                        <tr key={i} className="border-b border-surface-50 last:border-0 dark:border-surface-dark-850">
                                            <td className="py-2 pr-4 text-surface-800 dark:text-surface-dark-100">{dt.filename}</td>
                                            <td className="py-2">
                                                <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                                                    {dt.document_type.replace(/_/g, " ")}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Results grid */}
                    <div className="space-y-6">
                        {/* Facts */}
                        {result.facts.length > 0 && (
                            <SectionCard
                                title="Facts"
                                icon={<FactIcon />}
                                accentClass="bg-emerald-50/70 dark:bg-emerald-950/20"
                                count={result.facts.length}
                            >
                                {result.facts.map((f, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={f.source_document}
                                        source_section={f.source_section}
                                        badges={
                                            <span
                                                className={cn(
                                                    "rounded px-1.5 py-0.5 text-xs font-medium",
                                                    CONFIDENCE_COLORS[f.confidence] ?? CONFIDENCE_COLORS.medium,
                                                )}
                                            >
                                                {f.confidence}
                                            </span>
                                        }
                                    >
                                        {f.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Decisions */}
                        {result.decisions.length > 0 && (
                            <SectionCard
                                title="Decisions"
                                icon={<DecisionIcon />}
                                accentClass="bg-blue-50/70 dark:bg-blue-950/20"
                                count={result.decisions.length}
                            >
                                {result.decisions.map((d, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={d.source_document}
                                        source_section={d.source_section}
                                        badges={
                                            d.stakeholders.length > 0 && (
                                                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-400">
                                                    {d.stakeholders.join(", ")}
                                                </span>
                                            )
                                        }
                                    >
                                        {d.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Assumptions */}
                        {result.assumptions.length > 0 && (
                            <SectionCard
                                title="Assumptions"
                                icon={<QuestionIcon />}
                                accentClass="bg-violet-50/70 dark:bg-violet-950/20"
                                count={result.assumptions.length}
                            >
                                {result.assumptions.map((a, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={a.source_document}
                                        source_section={a.source_section}
                                        badges={
                                            a.validation_needed && (
                                                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                                                    needs validation
                                                </span>
                                            )
                                        }
                                    >
                                        {a.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Risks */}
                        {result.risks.length > 0 && (
                            <SectionCard
                                title="Risks"
                                icon={<RiskIcon />}
                                accentClass="bg-orange-50/70 dark:bg-orange-950/20"
                                count={result.risks.length}
                            >
                                {result.risks.map((r, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={r.source_document}
                                        source_section={r.source_section}
                                        badges={
                                            <>
                                                <span
                                                    className={cn(
                                                        "rounded px-1.5 py-0.5 text-xs font-medium",
                                                        SEVERITY_COLORS[r.severity] ?? SEVERITY_COLORS.medium,
                                                    )}
                                                >
                                                    {r.severity}
                                                </span>
                                                {r.mitigation && (
                                                    <span className="rounded bg-surface-100 px-1.5 py-0.5 text-xs text-surface-600 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                                                        mitigation: {r.mitigation}
                                                    </span>
                                                )}
                                            </>
                                        }
                                    >
                                        {r.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Open Questions */}
                        {result.open_questions.length > 0 && (
                            <SectionCard
                                title="Open Questions"
                                icon={<QuestionIcon />}
                                accentClass="bg-violet-50/70 dark:bg-violet-950/20"
                                count={result.open_questions.length}
                            >
                                {result.open_questions.map((q, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={q.source_document}
                                        source_section={q.source_section}
                                        badges={
                                            q.suggested_owner && (
                                                <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700 dark:bg-violet-950/30 dark:text-violet-400">
                                                    owner: {q.suggested_owner}
                                                </span>
                                            )
                                        }
                                    >
                                        {q.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Action Items */}
                        {result.action_items.length > 0 && (
                            <SectionCard
                                title="Action Items"
                                icon={<DecisionIcon />}
                                accentClass="bg-blue-50/70 dark:bg-blue-950/20"
                                count={result.action_items.length}
                            >
                                {result.action_items.map((a, i) => (
                                    <ItemRow
                                        key={i}
                                        source_document={a.source_document}
                                        source_section={a.source_section}
                                        badges={
                                            <>
                                                <span className="rounded bg-surface-100 px-1.5 py-0.5 text-xs font-medium text-surface-600 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                                                    {a.priority}
                                                </span>
                                                {a.deadline && (
                                                    <span className="rounded bg-surface-100 px-1.5 py-0.5 text-xs text-surface-600 dark:bg-surface-dark-800 dark:text-surface-dark-400">
                                                        {a.deadline}
                                                    </span>
                                                )}
                                            </>
                                        }
                                    >
                                        {a.content}
                                    </ItemRow>
                                ))}
                            </SectionCard>
                        )}

                        {/* Document Conflicts */}
                        {result.document_conflicts.length > 0 && (
                            <SectionCard
                                title="Document Conflicts"
                                icon={<ConflictIcon />}
                                accentClass="bg-red-50/70 dark:bg-red-950/20"
                                count={result.document_conflicts.length}
                            >
                                {result.document_conflicts.map((c, i) => (
                                    <div key={i} className="px-5 py-3">
                                        <p className="mb-2 text-sm">
                                            <span className="font-medium text-red-700 dark:text-red-400">
                                                {c.document_a}
                                            </span>{" "}
                                            <span className="text-surface-400">vs</span>{" "}
                                            <span className="font-medium text-red-700 dark:text-red-400">
                                                {c.document_b}
                                            </span>
                                        </p>
                                        <div className="mb-2 space-y-1.5 rounded-lg bg-red-50 p-3 dark:bg-red-950/20">
                                            <div className="flex items-start gap-2">
                                                <SourcePill document={c.document_a} section={c.section_a} />
                                                <p className="text-sm text-surface-700 dark:text-surface-dark-200">
                                                    {c.statement_a}
                                                </p>
                                            </div>
                                            <div className="flex items-start gap-2">
                                                <SourcePill document={c.document_b} section={c.section_b} />
                                                <p className="text-sm text-surface-700 dark:text-surface-dark-200">
                                                    {c.statement_b}
                                                </p>
                                            </div>
                                        </div>
                                        {c.resolution_suggestion && (
                                            <p className="text-xs text-surface-500 dark:text-surface-dark-400">
                                                <span className="font-medium">Suggestion:</span>{" "}
                                                {c.resolution_suggestion}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </SectionCard>
                        )}

                        {/* Repeated Statements */}
                        {result.repeated_statements.length > 0 && (
                            <SectionCard
                                title="Repeated Statements"
                                icon={<RepeatIcon />}
                                accentClass="bg-teal-50/70 dark:bg-teal-950/20"
                                count={result.repeated_statements.length}
                            >
                                {result.repeated_statements.map((r, i) => (
                                    <div key={i} className="px-5 py-3">
                                        <div className="mb-2 flex flex-wrap items-center gap-2">
                                            <SourcePill document={r.document_a} section={r.section_a} />
                                            <span className="text-xs text-surface-400">&cong;</span>
                                            <SourcePill document={r.document_b} section={r.section_b} />
                                            {r.is_exact_match && (
                                                <span className="rounded bg-teal-100 px-1.5 py-0.5 text-xs text-teal-700 dark:bg-teal-950/30 dark:text-teal-400">
                                                    exact match
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-sm text-surface-700 dark:text-surface-dark-200">
                                            {r.statement}
                                        </p>
                                    </div>
                                ))}
                            </SectionCard>
                        )}

                        {/* Missing Actions */}
                        {result.missing_actions.length > 0 && (
                            <SectionCard
                                title="Missing Actions (Policy Gaps)"
                                icon={<RiskIcon />}
                                accentClass="bg-amber-50/70 dark:bg-amber-950/20"
                                count={result.missing_actions.length}
                            >
                                {result.missing_actions.map((m, i) => (
                                    <div key={i} className="px-5 py-3">
                                        <div className="mb-1.5 flex flex-wrap items-center gap-2">
                                            <SourcePill
                                                document={m.policy_reference}
                                                section={m.policy_section}
                                            />
                                            <span
                                                className={cn(
                                                    "rounded px-1.5 py-0.5 text-xs font-medium",
                                                    SEVERITY_COLORS[m.urgency] ?? SEVERITY_COLORS.medium,
                                                )}
                                            >
                                                {m.urgency}
                                            </span>
                                        </div>
                                        <p className="text-sm text-surface-700 dark:text-surface-dark-200">
                                            {m.description}
                                        </p>
                                    </div>
                                ))}
                            </SectionCard>
                        )}

                        {/* Missing Questions */}
                        {result.missing_questions.length > 0 && (
                            <SectionCard
                                title="Missed Questions (Policy Gaps)"
                                icon={<QuestionIcon />}
                                accentClass="bg-violet-50/70 dark:bg-violet-950/20"
                                count={result.missing_questions.length}
                            >
                                {result.missing_questions.map((q, i) => (
                                    <div key={i} className="px-5 py-3">
                                        <div className="mb-1.5 flex flex-wrap items-center gap-2">
                                            <SourcePill
                                                document={q.policy_reference}
                                                section={q.policy_section}
                                            />
                                            <span
                                                className={cn(
                                                    "rounded px-1.5 py-0.5 text-xs font-medium",
                                                    SEVERITY_COLORS[q.urgency] ?? SEVERITY_COLORS.medium,
                                                )}
                                            >
                                                {q.urgency}
                                            </span>
                                        </div>
                                        <p className="text-sm font-medium text-surface-800 dark:text-surface-dark-100">
                                            {q.question}
                                        </p>
                                    </div>
                                ))}
                            </SectionCard>
                        )}

                        {/* Empty state — all arrays empty */}
                        {result.facts.length === 0 &&
                            result.decisions.length === 0 &&
                            result.assumptions.length === 0 &&
                            result.risks.length === 0 &&
                            result.open_questions.length === 0 &&
                            result.action_items.length === 0 &&
                            result.document_conflicts.length === 0 &&
                            result.repeated_statements.length === 0 &&
                            result.missing_actions.length === 0 &&
                            result.missing_questions.length === 0 && (
                                <div className="rounded-xl border border-surface-200 bg-white p-8 text-center dark:border-surface-dark-700 dark:bg-surface-dark-900">
                                    <p className="text-sm text-surface-500 dark:text-surface-dark-400">
                                        No items were extracted from your documents. This may indicate
                                        that the documents contain little structured information, or
                                        the AI model had difficulty parsing them.
                                    </p>
                                </div>
                            )}
                    </div>
                </div>
            </div>
        </div>
    );
}
