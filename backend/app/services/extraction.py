# ── Extraction Service ────────────────────────────────────────────────────────
# Multi-step LangChain ChatOllama pipeline that analyses 1-3 vectorized project
# documents against an organizational policy knowledge base.
#
# Architecture — four sequential phases, each a narrow, focused LLM call:
#
#   Phase 1: PER-DOCUMENT EXTRACTION (parallel)
#     Each project document gets its own LLM call with ONLY that document's
#     chunks.  Extracts facts, decisions, assumptions, risks, open questions,
#     and action items.  Source attribution is trivially correct because the
#     LLM only sees one document at a time.
#
#   Phase 2: CROSS-DOCUMENT CONFLICT DETECTION
#     LLM receives only the structured findings from Phase 1 (no raw chunks).
#     Input is ~1K tokens of bullet-point summaries, so the 7B model can
#     reason clearly about contradictions.
#
#   Phase 3: POLICY GAP ANALYSIS
#     Backend searches the policy KB with keywords derived from Phase 1
#     findings.  The LLM then compares Phase 1 findings against the matched
#     policy chunks to identify missing actions.
#
#   Phase 4: EXECUTIVE SUMMARY SYNTHESIS
#     One final call with condensed findings from all phases produces the
#     human-readable summary.
#
# Why not a single giant prompt?
#   • A 7B model producing 4K tokens across 8 categories inevitably produces
#     shallow, inconsistent results.
#   • Source attribution hallucination is eliminated — Phase 1 calls each see
#     only one document.
#   • Policy search is targeted — the backend searches with terms from actual
#     findings, not a vague "organizational policies" query.
#   • Failure isolation — if one phase fails, only that phase needs retry.

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.schemas.extraction import (
    ConflictDetectionResult,
    ExtractionResult,
    PerDocumentExtraction,
    PolicyGapResult,
    SummaryResult,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  Public API — called by the FastAPI router
# ═══════════════════════════════════════════════════════════════════════════════


async def run_extraction(
    db: AsyncSession,
    project_doc_ids: list[UUID],
) -> ExtractionResult:
    """Orchestrate the full 4-phase extraction pipeline.

    Args:
        db: An active async database session.
        project_doc_ids: UUIDs of the KnowledgeDocuments in this project (1-3).

    Returns:
        A complete ExtractionResult assembled from all four phases.
    """
    # ── Phase 1: Per-document extraction (parallel) ────────────────────────
    logger.info("Phase 1: extracting %d document(s) in parallel", len(project_doc_ids))
    doc_extractions = await _phase1_extract_all(db, project_doc_ids)

    # ── Phase 2: Cross-document conflict + repeat detection ────────────────
    logger.info("Phase 2: detecting cross-document conflicts and repeats")
    conflicts, repeated = await _phase2_detect_conflicts(doc_extractions)

    # ── Phase 3: Policy gap analysis ───────────────────────────────────────
    logger.info("Phase 3: analysing policy gaps")
    missing_actions, missing_questions = await _phase3_analyse_policy_gaps(
        db, doc_extractions, project_doc_ids
    )

    # ── Phase 4: Executive summary synthesis ───────────────────────────────
    logger.info("Phase 4: synthesising executive summary")
    summary = await _phase4_synthesise_summary(
        doc_extractions, conflicts, missing_actions, repeated, missing_questions
    )

    # ── Assemble final result ──────────────────────────────────────────────
    result = ExtractionResult(
        summary=summary,
        facts=[f for d in doc_extractions for f in d.facts],
        decisions=[d for d_ in doc_extractions for d in d_.decisions],
        assumptions=[a for d in doc_extractions for a in d.assumptions],
        risks=[r for d in doc_extractions for r in d.risks],
        open_questions=[q for d in doc_extractions for q in d.open_questions],
        action_items=[a for d in doc_extractions for a in d.action_items],
        document_conflicts=conflicts,
        missing_actions=missing_actions,
        missing_questions=missing_questions,
        repeated_statements=repeated,
    )
    logger.info(
        "Pipeline complete: %d facts, %d decisions, %d assumptions, "
        "%d risks, %d questions, %d actions, %d conflicts, %d missing "
        "actions, %d missing questions, %d repeats",
        len(result.facts),
        len(result.decisions),
        len(result.assumptions),
        len(result.risks),
        len(result.open_questions),
        len(result.action_items),
        len(result.document_conflicts),
        len(result.missing_actions),
        len(result.missing_questions),
        len(result.repeated_statements),
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 1 — Per-Document Extraction (parallel)
# ═══════════════════════════════════════════════════════════════════════════════

PHASE1_SYSTEM_PROMPT = """\
You are a human-in-the-loop document extraction assistant. You are analysing \
ONE document at a time. Your job is to surface what this document contains; \
you do NOT make decisions or assign tasks.

The context you receive contains chunks from a SINGLE document, formatted as:

  [SECTION: chunk <n> (<metadata>)]
  <text content>

Extract the following from this ONE document:

1. DOCUMENT TYPE — identify what kind of document this is (requirements doc,
   design spec, risk assessment, meeting notes, project charter, etc.).

2. FACTS — statements the document presents as verifiable or objective.
   Assign confidence: 'high' for definitive statements, 'medium' for
   qualified statements, 'low' for uncertain or hedged claims.

3. DECISIONS — choices that were made and recorded.  Include stakeholders
   (people, roles, teams) when mentioned.

4. ASSUMPTIONS — premises the document takes for granted without proof.
   Mark validation_needed=true unless the assumption is trivially true.

5. RISKS — potential negative outcomes, threats, or failure modes.
   Assign severity ('critical', 'high', 'medium', 'low') and include any
   mitigation mentioned.

6. OPEN QUESTIONS — explicit or implied questions the document raises but
   does not answer.  Suggest an owner role if inferable.

7. ACTION ITEMS — tasks explicitly stated in the source text.  IMPORTANT:
   ONLY extract items that are explicitly stated.  NEVER invent, create,
   or auto-assign tasks.  If none exist, return an empty list.

CRITICAL RULES:
- EVERY item MUST include 'source_document' (the filename from the context
  header) and 'source_section' (the [SECTION: ...] label).  Never leave
  these empty.
- If unsure whether something is a fact or assumption, classify it as an
  assumption with confidence='low'.
- Be thorough — it is better to extract too many items than to miss
  something important.  The human reviewer will filter.
"""

PHASE2_SYSTEM_PROMPT = """\
You are a human-in-the-loop document reviewer. You are given structured \
summaries of findings extracted from multiple project documents. Your jobs:

1. Find CONFLICTS — statements that contradict each other across documents.
   For each conflict, provide:
   - statement_a / statement_b: the two contradictory statements
   - document_a / document_b: which document each statement came from
   - section_a / section_b: the section within each document
   - resolution_suggestion: how a human reviewer might resolve this (or "" if unclear)

2. Find REPEATED STATEMENTS — identical or substantially similar statements
   that appear in two different documents.  These are NOT contradictions;
   they are the same information stated twice.  For each repeated statement:
   - statement: the repeated content
   - document_a / document_b: which documents contain it
   - section_a / section_b: the sections within each document
   - is_exact_match: true if word-for-word identical, false if substantially same

If nothing is found, return empty lists.  Do NOT fabricate items.
"""

PHASE3_SYSTEM_PROMPT = """\
You are a human-in-the-loop compliance reviewer. You are given:
  1. Structured findings extracted from project documents.
  2. Relevant chunks from organizational policies and standards.

Your jobs:

1. Identify MISSING ACTIONS — things that SHOULD exist in the project \
documents based on the policies, but are currently ABSENT.  For each:
- description: what needs to be done
- policy_reference: the policy filename that mandates this
- policy_section: the section/chunk in the policy
- urgency: 'critical' | 'high' | 'medium' | 'low' based on policy language

2. Identify MISSING QUESTIONS — questions the project documents SHOULD be \
asking based on the policies, but aren't.  For each:
- question: the question that should be asked
- policy_reference: the policy filename that implies this question
- policy_section: the section/chunk in the policy
- urgency: 'critical' | 'high' | 'medium' | 'low'

Do NOT suggest actions or questions the policies don't actually require.  \
If the policies don't reveal any gaps, return empty lists.
"""

PHASE4_SYSTEM_PROMPT = """\
You are a document analysis summariser. You will receive a condensed summary \
of findings from a multi-phase document analysis pipeline. Write a concise \
executive summary (150-300 words) covering:

1. What types of documents were analysed.
2. Key themes and notable facts.
3. The most important risks and decisions identified.
4. Any cross-document conflicts detected.
5. Any repeated statements found across documents.
6. Critical policy gaps (missing actions and missed questions) that need attention.

Write in clear, professional prose.  Do NOT use bullet points — this is a \
narrative summary for a human reviewer.
"""

# ── Phase 1 — Per-Document Extraction Implementation ──────────────────────


async def _phase1_extract_all(
    db: AsyncSession,
    project_doc_ids: list[UUID],
) -> list[PerDocumentExtraction]:
    """Run Phase 1 extraction for every project document in parallel."""
    doc_data = await _fetch_document_data(db, project_doc_ids)
    tasks = [
        _phase1_extract_one(filename, chunks_and_sections)
        for filename, chunks_and_sections in doc_data
    ]
    return list(await asyncio.gather(*tasks))


async def _phase1_extract_one(
    filename: str,
    chunks: list[tuple[str, str]],  # (content, section_label)
) -> PerDocumentExtraction:
    """Extract findings from a single document via one LLM call."""
    parts = [f"=== DOCUMENT: {filename} ==="]
    for content, section_label in chunks:
        parts.append(f"[SECTION: {section_label}]\n{content}\n")
    context = "\n".join(parts)

    logger.info("Phase 1: extracting from '%s' (%d chunks)", filename, len(chunks))
    return await asyncio.to_thread(
        _invoke_structured, PHASE1_SYSTEM_PROMPT, context, PerDocumentExtraction
    )


# ── Phase 2 — Conflict Detection Implementation ───────────────────────────


async def _phase2_detect_conflicts(
    doc_extractions: list[PerDocumentExtraction],
) -> tuple[list, list]:
    """Detect contradictions and repeated statements between documents.

    Returns:
        (conflicts, repeated_statements) — two lists, each may be empty.
    """
    if len(doc_extractions) < 2:
        logger.info("Phase 2: skipped — only %d document(s)", len(doc_extractions))
        return [], []

    parts = ["=== CROSS-DOCUMENT CONFLICT ANALYSIS ===", ""]
    for i, ext in enumerate(doc_extractions):
        label = ext.facts[0].source_document if ext.facts else f"Document {i + 1}"
        parts.append(f"--- Document: {label} ---")
        parts.append(f"Type: {ext.document_type}")
        for f in ext.facts:
            parts.append(f"  FACT [{f.source_section}]: {f.content}")
        for d in ext.decisions:
            stake = ", ".join(d.stakeholders) if d.stakeholders else "none"
            parts.append(
                f"  DECISION [{d.source_section}]: {d.content} (stakeholders: {stake})"
            )
        for r in ext.risks:
            parts.append(
                f"  RISK [{r.source_section}]: {r.content} (severity: {r.severity})"
            )
        parts.append("")

    context = "\n".join(parts)
    logger.info("Phase 2: conflict detection context = %d chars", len(context))

    result = await asyncio.to_thread(
        _invoke_structured, PHASE2_SYSTEM_PROMPT, context, ConflictDetectionResult
    )
    return result.conflicts, result.repeated_statements


# ── Phase 3 — Policy Gap Analysis Implementation ──────────────────────────


async def _phase3_analyse_policy_gaps(
    db: AsyncSession,
    doc_extractions: list[PerDocumentExtraction],
    project_doc_ids: list[UUID],
) -> tuple[list, list]:
    """Identify missing actions and questions by comparing project findings against policies.

    Returns:
        (missing_actions, missing_questions) — two lists, each may be empty.
    """
    queries = _derive_policy_queries(doc_extractions)

    # Search FAISS for each query, deduplicate
    all_policy_chunks: dict[str, tuple[int, str, dict | None, str]] = {}
    for query in queries:
        hits = await _search_policy_chunks(
            db, query, project_doc_ids, settings.EXTRACTION_POLICY_TOP_K
        )
        for idx, content, meta, filename in hits:
            key = f"{filename}::chunk_{idx}"
            if key not in all_policy_chunks:
                all_policy_chunks[key] = (idx, content, meta, filename)

    if not all_policy_chunks:
        logger.info("Phase 3: no relevant policy chunks found — skipping")
        return [], []

    # Format project findings summary
    parts = ["=== POLICY GAP ANALYSIS ===", "", "--- PROJECT FINDINGS ---"]
    for ext in doc_extractions:
        label = ext.facts[0].source_document if ext.facts else "Unknown"
        parts.append(f"Document '{label}' ({ext.document_type}):")
        for f in ext.facts:
            parts.append(f"  FACT: {f.content}")
        for d in ext.decisions:
            parts.append(f"  DECISION: {d.content}")
        for r in ext.risks:
            parts.append(f"  RISK: {r.content} (severity: {r.severity})")
        for q in ext.open_questions:
            parts.append(f"  QUESTION: {q.content}")
        parts.append("")

    # Format policy chunks
    parts.append("--- RELEVANT POLICIES ---")
    for idx, content, meta, filename in all_policy_chunks.values():
        section_label = _format_section_label(idx, meta)
        parts.append(f"[POLICY: {filename}] [SECTION: {section_label}]\n{content}\n")

    context = "\n".join(parts)
    logger.info(
        "Phase 3: policy gap context = %d chars (%d unique policy chunks from %d queries)",
        len(context),
        len(all_policy_chunks),
        len(queries),
    )

    result = await asyncio.to_thread(
        _invoke_structured, PHASE3_SYSTEM_PROMPT, context, PolicyGapResult
    )
    return result.missing_actions, result.missing_questions


def _derive_policy_queries(doc_extractions: list[PerDocumentExtraction]) -> list[str]:
    """Derive targeted FAISS search queries from Phase 1 extracted content."""
    import re

    combined_content: list[str] = []
    capitalized: set[str] = set()

    for ext in doc_extractions:
        for f in ext.facts:
            combined_content.append(f.content)
        for d in ext.decisions:
            combined_content.append(d.content)
        for r in ext.risks:
            combined_content.append(r.content)
            if r.mitigation:
                combined_content.append(r.mitigation)
        for q in ext.open_questions:
            combined_content.append(q.content)

    queries: list[str] = []

    # Broad query: all content concatenated (capped at ~2KB)
    broad = " ".join(combined_content)[:2048]
    if broad.strip():
        queries.append(broad)

    # Targeted queries: capitalized phrases (proper nouns, acronyms, standards)
    for text in combined_content:
        found = re.findall(
            r"\b[A-Z][A-Za-z0-9\-]{1,}(?:\s+[A-Z][A-Za-z0-9\-]{1,}){0,2}\b", text
        )
        for phrase in found:
            if len(phrase) > 3 and phrase.lower() not in {
                "the",
                "this",
                "that",
                "with",
                "from",
                "they",
                "them",
                "have",
                "been",
                "were",
                "will",
                "shall",
                "must",
                "each",
            }:
                capitalized.add(phrase)

    for term in list(capitalized)[:3]:
        if term not in broad:
            queries.append(term)

    logger.info("Phase 3: derived %d policy search queries", len(queries))
    return queries


# ── Phase 4 — Summary Synthesis Implementation ────────────────────────────


async def _phase4_synthesise_summary(
    doc_extractions: list[PerDocumentExtraction],
    conflicts: list,
    missing_actions: list,
    repeated: list,
    missing_questions: list,
) -> str:
    """Synthesise an executive summary from all previous phase outputs."""
    parts = ["=== EXECUTIVE SUMMARY SYNTHESIS ===", ""]

    parts.append("--- DOCUMENTS ANALYSED ---")
    for ext in doc_extractions:
        label = ext.facts[0].source_document if ext.facts else "Unknown"
        parts.append(
            f"'{label}' — {ext.document_type}: {len(ext.facts)} facts, "
            f"{len(ext.decisions)} decisions, {len(ext.risks)} risks, "
            f"{len(ext.assumptions)} assumptions, {len(ext.open_questions)} "
            f"questions, {len(ext.action_items)} actions"
        )

    # Key high-confidence facts (limit 5)
    high_facts = [f for d in doc_extractions for f in d.facts if f.confidence == "high"]
    parts.append("\n--- KEY FACTS (high confidence) ---")
    for f in high_facts[:5]:
        parts.append(f"  [{f.source_document}] {f.content}")

    # Key decisions (limit 5)
    all_decisions = [d for d_ in doc_extractions for d in d_.decisions]
    parts.append("\n--- KEY DECISIONS ---")
    for d in all_decisions[:5]:
        parts.append(f"  [{d.source_document}] {d.content}")

    # Critical/high risks (limit 5)
    high_risks = [
        r
        for d in doc_extractions
        for r in d.risks
        if r.severity in ("critical", "high")
    ]
    parts.append("\n--- KEY RISKS ---")
    for r in high_risks[:5]:
        parts.append(f"  [{r.source_document}] {r.content} (severity: {r.severity})")

    # Conflicts
    if conflicts:
        parts.append(f"\n--- CONFLICTS DETECTED ({len(conflicts)}) ---")
        for c in conflicts[:3]:
            parts.append(f"  {c.document_a} vs {c.document_b}: {c.statement_a[:80]}...")
    else:
        parts.append("\n--- CONFLICTS DETECTED: 0 ---")

    # Critical/high missing actions
    urgent = [m for m in missing_actions if m.urgency in ("critical", "high")]
    if urgent:
        parts.append(f"\n--- CRITICAL/HIGH POLICY GAPS ({len(urgent)}) ---")
        for m in urgent[:5]:
            parts.append(f"  [{m.policy_reference}] {m.description[:100]}")
    else:
        parts.append(
            f"\n--- POLICY GAPS: {len(missing_actions)} total, 0 critical/high ---"
        )

    # Repeated statements
    if repeated:
        parts.append(f"\n--- REPEATED STATEMENTS ({len(repeated)}) ---")
        for r in repeated[:3]:
            parts.append(f"  {r.document_a} ≅ {r.document_b}: {r.statement[:80]}...")
    else:
        parts.append("\n--- REPEATED STATEMENTS: 0 ---")

    # Missing questions
    urgent_q = [q for q in missing_questions if q.urgency in ("critical", "high")]
    if urgent_q:
        parts.append(
            f"\n--- MISSED QUESTIONS FROM POLICIES ({len(urgent_q)} critical/high) ---"
        )
        for q in urgent_q[:3]:
            parts.append(f"  [{q.policy_reference}] {q.question[:100]}")
    else:
        parts.append(
            f"\n--- MISSED QUESTIONS: {len(missing_questions)} total, 0 critical/high ---"
        )

    context = "\n".join(parts)
    logger.info("Phase 4: summary context = %d chars", len(context))

    result = await asyncio.to_thread(
        _invoke_structured, PHASE4_SYSTEM_PROMPT, context, SummaryResult
    )
    return result.summary


# ═══════════════════════════════════════════════════════════════════════════════
#  Shared Utilities
# ═══════════════════════════════════════════════════════════════════════════════


def _build_llm():
    """Create a fresh ChatOllama instance with project settings.

    Returns a new instance each call — LangChain chat models are not
    thread-safe for concurrent use across asyncio.to_thread workers.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        temperature=0,
        base_url=settings.OLLAMA_BASE_URL,
        num_ctx=settings.OLLAMA_NUM_CTX,
        num_predict=settings.OLLAMA_NUM_PREDICT,
    )


def _invoke_structured(
    system_prompt: str,
    context: str,
    schema: type,
):
    """Invoke ChatOllama with structured output bound to *schema*.

    Args:
        system_prompt: The system message for this phase.
        context: The formatted context string.
        schema: A Pydantic model class for with_structured_output().

    Returns:
        An instance of *schema* parsed from the LLM's JSON response.

    Raises:
        RuntimeError: If the LLM is unreachable, times out, or returns
            unparseable output.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = _build_llm()
    structured_llm = llm.with_structured_output(schema, method="json_schema")
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "{context}")]
    )
    chain = prompt | structured_llm

    schema_name = schema.__name__
    logger.debug("Invoking %s (context=%d chars)", schema_name, len(context))
    try:
        result = chain.invoke({"context": context})
        logger.debug("%s complete", schema_name)
        return result
    except Exception as exc:
        logger.exception("%s failed", schema_name)
        raise RuntimeError(
            f"LLM call failed during {schema_name}: {exc}. "
            f"Check that Ollama is running and the model "
            f"'{settings.OLLAMA_MODEL}' is pulled."
        ) from exc


async def _fetch_document_data(
    db: AsyncSession,
    doc_ids: list[UUID],
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Fetch chunks for each document, ordered by chunk_index.

    Returns:
        List of (filename, [(content, section_label), ...]) in doc_ids order.
    """
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids))
    )
    docs_by_id: dict[UUID, KnowledgeDocument] = {
        d.id: d for d in doc_result.scalars().all()
    }

    result: list[tuple[str, list[tuple[str, str]]]] = []
    for doc_id in doc_ids:
        doc = docs_by_id.get(doc_id)
        if doc is None:
            continue

        chunks_result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
            .limit(settings.EXTRACTION_CHUNKS_PER_DOC),
        )
        chunks: list[tuple[str, str]] = []
        for chunk in chunks_result.scalars().all():
            section_label = _format_section_label(
                chunk.chunk_index, chunk.metadata_json
            )
            chunks.append((chunk.content, section_label))
        result.append((doc.filename, chunks))

    return result


def _format_section_label(chunk_index: int, metadata: dict | None) -> str:
    """Build a human-readable section label from chunk_index and loader metadata.

    Examples:
        "chunk 3 (page 2)"     — PDF with page number
        "chunk 7"              — plain text, no metadata
    """
    label = f"chunk {chunk_index}"
    if metadata:
        page = metadata.get("page") or metadata.get("page_number")
        if page is not None:
            label += f" (page {page})"
    return label


async def _search_policy_chunks(
    db: AsyncSession,
    query: str,
    exclude_doc_ids: list[UUID],
    top_k: int,
) -> list[tuple[int, str, dict | None, str]]:
    """Semantically search FAISS for policy chunks and filter to public docs.

    Searches for 2× top_k to allow for post-filtering, then takes the top_k
    after removing private and project-owned documents.

    Returns:
        List of (chunk_index, content, metadata_json, parent_filename).
    """
    from app.services.faiss_service import get_faiss_service
    from app.services.vectorization import _get_embedding_model

    faiss = get_faiss_service()
    if faiss._index.ntotal == 0:
        logger.debug("FAISS index empty — skipping policy search")
        return []

    model = _get_embedding_model()
    query_embedding = model.embed_query(query)
    hits = faiss.search(query_embedding, top_k * 2)
    if not hits:
        return []

    chunk_ids = [cid for cid, _ in hits]
    score_by_id = {cid: score for cid, score in hits}

    result = await db.execute(
        select(DocumentChunk)
        .options(selectinload(DocumentChunk.document))
        .where(DocumentChunk.id.in_(chunk_ids)),
    )
    chunks = result.scalars().all()

    filtered: list[tuple[int, str, dict | None, str, float]] = []
    for chunk in chunks:
        doc = chunk.document
        if doc is None or doc.visibility != "public" or doc.id in exclude_doc_ids:
            continue
        score = score_by_id.get(chunk.id, 0.0)
        filtered.append(
            (chunk.chunk_index, chunk.content, chunk.metadata_json, doc.filename, score)
        )

    filtered.sort(key=lambda x: x[4], reverse=True)
    return [
        (idx, content, meta, fname) for idx, content, meta, fname, _ in filtered[:top_k]
    ]
