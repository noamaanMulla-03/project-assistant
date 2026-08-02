# ── Extraction Service ────────────────────────────────────────────────────────
# LangChain tools agent that analyses 1-3 vectorized project documents against
# an organizational policy knowledge base.
#
# Architecture:
#   Phase A — Agent: The LLM is given two @tools (retrieve documents from
#     pgvector, search policies via FAISS) and autonomously explores.
#   Phase B — 4-phase structured pipeline: Per-document extraction, cross-
#     document conflict detection, policy-gap analysis, executive summary.
#     Each phase uses Ollama's native JSON schema mode (via
#     with_structured_output) which constrains token sampling to the exact
#     Pydantic schema — no post-hoc parsing, regex, or synonym maps needed.

import logging
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
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
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════


async def run_extraction(
    db: AsyncSession,
    project_doc_ids: list[UUID],
) -> ExtractionResult:
    """Run the LangChain tools agent to explore documents + policies, then
    produce structured extraction output."""
    doc_result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(project_doc_ids))
    )
    documents = doc_result.scalars().all()
    doc_names = [d.filename for d in documents]
    logger.info("Starting agent extraction for: %s", doc_names)

    tools = await _build_tools(db, project_doc_ids)

    # ── Native async agent invocation (no more asyncio.to_thread) ──
    try:
        agent_result = await _run_agent(doc_names, tools)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise RuntimeError(
            f"LLM agent failed: {exc}. "
            f"Check that Ollama is running and the model "
            f"'{settings.OLLAMA_MODEL}' is pulled."
        ) from exc

    # ── Fetch document chunks per-file for Phase 1 ──
    doc_data = await _fetch_document_data(db, project_doc_ids)

    # ── Extract policy lines from agent output for Phase 3 ──
    policy_lines = _extract_policy_lines(agent_result)

    logger.info("Running 4-phase structured extraction pipeline")
    # ── continued: _run_structured_pipeline stays sync (LLM calls are
    #    internally synchronous), but it's wrapped in to_thread for safety ──
    import asyncio

    return await asyncio.to_thread(_run_structured_pipeline, doc_data, policy_lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompts
# ═══════════════════════════════════════════════════════════════════════════════

# ── Agent no longer produces a redundant full summary ───────────────
# Previously the agent was instructed to produce a "concise natural-language
# summary" at the end of its run.  That summary was never consumed downstream
# (only the tool outputs are used).  Phase 4 already synthesises the final
# executive summary, so the agent's summary was wasted inference.  Now the
# agent simply signals completion with a terse list of discovered topics.

_AGENT_SYSTEM_PROMPT = """\
You are a document exploration agent. Your ONLY job is to gather information \
about a set of project documents and any relevant organizational policies. \
You do NOT produce final analysis — the system will handle that separately.

You have two tools:
  - retrieve_document_chunks(filename): Get the text content of a project
    document.  You MUST call this for EACH document to understand what it
    contains.
  - search_policy_kb(query): Search the organizational policy knowledge base
    with a natural-language query.  Use this AFTER reading documents to find
    policies relevant to the specific topics, risks, or standards mentioned.

Your workflow:
1. Call retrieve_document_chunks() for every document listed in the project.
2. Based on what you find (key terms, risks, standards mentioned, compliance
   topics), call search_policy_kb() with targeted queries.  Be specific —
   instead of "safety", search for "fall protection scaffolding safety" if
   that's what the document mentions.
3. If your first policy search reveals new topics, follow up with additional
   targeted searches.
4. When you have gathered sufficient information, output ONLY the exact phrase
   "EXPLORATION COMPLETE" followed by a terse bullet list of discovered topics
   and policy areas (single words or short phrases, NOT full sentences).
   Do NOT write a narrative summary, analysis, or recommendations — the
   downstream pipeline handles all synthesis.
"""

_PHASE1_PER_DOC_PROMPT = """\
You are a document extraction specialist. You are given the text chunks of \
a SINGLE project document. Extract everything you can find into the exact \
JSON fields specified below.  The primary body text ALWAYS goes in \"content\".

Output a JSON object with these EXACT top-level keys and sub-fields:

{
  "document_type": "<string>",
  "facts": [
    {
      "content": "<the fact text — FIELD NAME IS content, NOT statement>",
      "confidence": "high" | "medium" | "low",
      "source_document": "<filename matching [DOCUMENT: ...]>",
      "source_section": "<section label matching [SECTION: ...]>"
    }
  ],
  "decisions": [
    {
      "content": "<the decision text — FIELD NAME IS content, NOT decision>",
      "stakeholders": ["<name or role>"],
      "source_document": "<filename>",
      "source_section": "<section label>"
    }
  ],
  "assumptions": [
    {
      "content": "<the assumption text — FIELD NAME IS content, NOT assumption>",
      "validation_needed": true | false,
      "source_document": "<filename>",
      "source_section": "<section label>"
    }
  ],
  "risks": [
    {
      "content": "<the risk description — FIELD NAME IS content, NOT risk>",
      "severity": "critical" | "high" | "medium" | "low",
      "mitigation": "<mitigation if mentioned, otherwise empty string \"\">",
      "source_document": "<filename>",
      "source_section": "<section label>"
    }
  ],
  "open_questions": [
    {
      "content": "<the question text — FIELD NAME IS content, NOT question>",
      "suggested_owner": "<name or role if inferable, otherwise empty string \"\">",
      "source_document": "<filename>",
      "source_section": "<section label>"
    }
  ],
  "action_items": [
    {
      "content": "<the task description — FIELD NAME IS content, NOT description>",
      "priority": "high" | "medium" | "low",
      "deadline": "<deadline if mentioned, otherwise empty string \"\">",
      "source_document": "<filename>",
      "source_section": "<section label>"
    }
  ]
}

ABSOLUTE RULES — VIOLATING ANY OF THESE WILL CAUSE A PARSE FAILURE:
1. The primary text ALWAYS goes in the field named \"content\".  NEVER use
   \"statement\", \"decision\", \"assumption\", \"risk\", \"question\",
   \"description\", \"owner\", \"due_date\", or any other alias.
2. \"mitigation\", \"suggested_owner\", and \"deadline\" are STRING fields.
   If no value is available, use \"\" (empty string).  NEVER use null.
3. Every array must be present, even if empty: [].
4. NEVER add fields beyond those shown above.
5. Output ONLY the JSON object.  No markdown fences, no explanatory text.
"""

_PHASE2_CONFLICT_PROMPT = """\
You are a cross-document analyst. You are given structured summaries of \
multiple project documents (facts, decisions, assumptions, risks, etc).
Your ONLY job is to find conflicts and repeated statements.

Output a JSON object with these EXACT keys and sub-fields:

{
  "conflicts": [
    {
      "statement_a": "<first contradictory statement>",
      "statement_b": "<second contradictory statement>",
      "document_a": "<filename of statement_a>",
      "document_b": "<filename of statement_b>",
      "section_a": "<section of statement_a>",
      "section_b": "<section of statement_b>",
      "resolution_suggestion": "<suggested resolution, or empty string \"\">"
    }
  ],
  "repeated_statements": [
    {
      "statement": "<the repeated content>",
      "document_a": "<first document filename>",
      "document_b": "<second document filename>",
      "section_a": "<section in first document>",
      "section_b": "<section in second document>",
      "is_exact_match": true | false
    }
  ]
}

ABSOLUTE RULES:
1. "resolution_suggestion" is a STRING.  Use \"\" if none, NEVER null.
2. Every array must be present, even if empty: [].
3. NEVER add fields beyond those shown above.
4. Output ONLY the JSON object, no markdown, no explanation.
"""

_PHASE3_POLICY_GAP_PROMPT = """\
You are a policy compliance analyst. You are given:
1. Structured summaries of project documents (facts, decisions, risks, etc.)
2. Relevant organizational policy chunks

Find gaps between what the project documents contain and what policies require.

Output a JSON object with these EXACT keys and sub-fields:

{
  "missing_actions": [
    {
      "description": "<what action is missing>",
      "policy_reference": "<policy document filename>",
      "policy_section": "<section/chunk in the policy>",
      "urgency": "critical" | "high" | "medium" | "low"
    }
  ],
  "missing_questions": [
    {
      "question": "<the question that should be asked>",
      "policy_reference": "<policy document filename>",
      "policy_section": "<section/chunk in the policy>",
      "urgency": "critical" | "high" | "medium" | "low"
    }
  ]
}

ABSOLUTE RULES:
1. "description" and "question" are STRING fields.  Never null.
2. Every array must be present, even if empty: [].
3. NEVER add fields beyond those shown above.
4. Output ONLY the JSON object, no markdown, no explanation.
"""

_PHASE4_SUMMARY_PROMPT = """\
You are an executive summarizer. You are given a COMPRESSED digest of \
extraction results from multiple analysis phases: per-document findings, \
cross-document conflicts, repeated statements, policy gaps, and missing \
actions/questions.  The digest highlights all critical signals.

Output a JSON object with this EXACT key:

{
  "summary": "<your executive summary text covering document types, key themes, cross-cutting concerns, and most critical risks and gaps>"
}

ABSOLUTE RULES:
1. The output object has exactly ONE key: "summary".
2. Output ONLY the JSON object, no markdown, no explanation.
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Tool Builder
# ═══════════════════════════════════════════════════════════════════════════════


async def _build_tools(
    db: AsyncSession,
    project_doc_ids: list[UUID],
) -> list:
    """Build two native async LangChain @tools as closures capturing db + doc_ids.

    ── Both tools are now `async def`.  They `await` the database
       directly instead of wrapping work in `asyncio.run()`, which caused nested
       event-loop errors when the agent was invoked from an async context.
    """
    from langchain_core.tools import tool

    # Fetch document filename→id mapping directly (we're in the main event loop)
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(project_doc_ids))
    )
    doc_map = {d.filename: d.id for d in result.scalars().all()}

    @tool
    async def retrieve_document_chunks(filename: str) -> str:
        """Retrieve the full text content of a project document by its filename.

        Args:
            filename: The exact filename of the project document (e.g.
                      'site-assessment.pdf', 'project-charter.docx').

        Returns:
            The document's text content split into labeled chunks with section
            identifiers for source attribution.
        """
        doc_id = doc_map.get(filename)
        if doc_id is None:
            available = list(doc_map.keys())
            return f"ERROR: Document '{filename}' not found. Available: {available}"

        try:
            chunks_result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(settings.EXTRACTION_CHUNKS_PER_DOC),
            )
            parts = [f"[DOCUMENT: {filename}]"]
            for chunk in chunks_result.scalars().all():
                section = _format_section_label(chunk.chunk_index, chunk.metadata_json)
                parts.append(f"[SECTION: {section}]\n{chunk.content}\n")
            return "\n".join(parts)
        except Exception as exc:
            return f"ERROR retrieving document '{filename}': {exc}"

    @tool
    async def search_policy_kb(query: str) -> str:
        """Search the organizational policy knowledge base.

        Use AFTER reading project documents to find policies relevant to
        specific topics, risks, or standards mentioned.  Use specific queries:
        instead of 'safety', search for 'fall protection scaffolding safety'.

        Args:
            query: Natural-language query for relevant policies/standards.

        Returns:
            Policy document chunks with [POLICY: ...] [SECTION: ...] labels.
        """
        try:
            hits = await _search_policy_chunks(
                db, query, project_doc_ids, settings.EXTRACTION_POLICY_TOP_K
            )
            if not hits:
                return f"No relevant policy documents found for query: '{query}'."
            parts = ["=== POLICY SEARCH RESULTS ==="]
            for idx, content, meta, filename in hits:
                section = _format_section_label(idx, meta)
                parts.append(f"[POLICY: {filename}] [SECTION: {section}]\n{content}\n")
            return "\n".join(parts)
        except Exception as exc:
            return f"ERROR searching policy KB for '{query}': {exc}"

    logger.info("Built 2 async tools for agent: %d document(s)", len(doc_map))
    return [retrieve_document_chunks, search_policy_kb]


# ═══════════════════════════════════════════════════════════════════════════════
#  Agent Runner
# ═══════════════════════════════════════════════════════════════════════════════


# ── _run_agent is now `async def` and uses `agent.ainvoke()` ──


async def _run_agent(doc_names: list[str], tools: list) -> dict:
    """Create and invoke a LangGraph ReAct agent with the given async tools.

    Uses native async invocation (ainvoke) so tool calls can `await` the
    database directly without nested event loops.
    """
    from langgraph.prebuilt import create_react_agent

    llm = _build_llm()

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=_AGENT_SYSTEM_PROMPT),
    )

    user_input = _build_agent_input(doc_names)
    logger.info(
        "Invoking LangGraph agent (max %d iterations)", settings.AGENT_MAX_ITERATIONS
    )

    # Native async invocation — tools are async, model is async
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=user_input)]},
        config={"recursion_limit": settings.AGENT_MAX_ITERATIONS},
    )

    # Parse intermediate steps from the message trail
    doc_outputs: list[tuple[str, str]] = []
    policy_outputs: list[tuple[str, str]] = []

    messages = result.get("messages", [])
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            # An AI message with tool calls — the NEXT message should be ToolMessage(s)
            for tc in msg.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_input = tc.get("args", {})
                # Find the matching ToolMessage response (it follows this AIMessage)
                output = _find_tool_output(messages, i + 1, tc.get("id"))
                if tool_name == "retrieve_document_chunks":
                    doc_outputs.append((tool_input.get("filename", "unknown"), output))
                elif tool_name == "search_policy_kb":
                    policy_outputs.append((tool_input.get("query", "unknown"), output))

    # ── Agent final output is now a terse "EXPLORATION COMPLETE"
    #    signal + topic list, not a redundant narrative summary.  We still
    #    capture it for logging but it is not consumed downstream. ──
    final_output = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            final_output = str(msg.content)
            break

    logger.info(
        "Agent complete: %d doc calls, %d policy calls, output=%d chars",
        len(doc_outputs),
        len(policy_outputs),
        len(final_output),
    )

    return {
        "summary": final_output,
        "doc_outputs": doc_outputs,
        "policy_outputs": policy_outputs,
    }


def _find_tool_output(messages: list, start_idx: int, tool_call_id: str | None) -> str:
    """Find the ToolMessage matching a given tool_call_id in the message list."""
    for msg in messages[start_idx:]:
        if isinstance(msg, ToolMessage) and (
            tool_call_id is None or msg.tool_call_id == tool_call_id
        ):
            return str(msg.content)
    return ""


def _build_agent_input(doc_names: list[str]) -> str:
    """Build the initial task description for the agent.

    ── No longer instructs the agent to "produce a summary" —
       the system prompt handles the completion signal. ──
    """
    names_str = "\n".join(f"  - {n}" for n in doc_names)
    return (
        f"Analyse the following project document(s):\n{names_str}\n\n"
        f"Call retrieve_document_chunks() for each document, then use "
        f"search_policy_kb() to find relevant organizational policies "
        f"based on what you discover."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  4-Phase Structured Extraction Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_policy_lines(agent_result: dict) -> list[str]:
    """Extract unique policy reference lines from agent tool outputs."""
    seen: set[str] = set()
    lines: list[str] = []
    for _, output in agent_result.get("policy_outputs", []):
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("[POLICY:") and "[SECTION:" in line:
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
    return lines


def _format_doc_context(filename: str, chunks: list[tuple[str, str]]) -> str:
    """Format a single document's chunks into a labeled context string."""
    parts = [f"[DOCUMENT: {filename}]"]
    for content, section_label in chunks:
        parts.append(f"[SECTION: {section_label}]\n{content}\n")
    return "\n".join(parts)


def _run_structured_pipeline(
    doc_data: list[tuple[str, list[tuple[str, str]]]],
    policy_lines: list[str],
) -> ExtractionResult:
    """Run 4 narrow LLM calls instead of 1 giant one to avoid output truncation.

    Phase 1: Per-document extraction (parallel-safe, each call sees 1 doc).
    Phase 2: Cross-document conflicts & repeated statements (reads Phase 1 JSON).
    Phase 3: Policy gap analysis (reads Phase 1 JSON + policy chunks).
    Phase 4: Executive summary (reads COMPRESSED digest of Phases 1-3).
    """
    import json

    # ── Phase 1: Per-document extraction ──
    phase1_results: list[PerDocumentExtraction] = []
    # ── Build doc_inventory for the compression step ──
    doc_inventory: list[tuple[str, str]] = []  # (filename, document_type)

    for filename, chunks in doc_data:
        doc_context = _format_doc_context(filename, chunks)
        result = _invoke_structured(
            _PHASE1_PER_DOC_PROMPT, doc_context, PerDocumentExtraction
        )
        phase1_results.append(result)
        doc_inventory.append((filename, result.document_type))

    # ── Phase 2: Cross-document conflict detection ──
    phase1_json = json.dumps([r.model_dump() for r in phase1_results], indent=2)
    conflicts = _invoke_structured(
        _PHASE2_CONFLICT_PROMPT, phase1_json, ConflictDetectionResult
    )

    # ── Phase 3: Policy gap analysis ──
    policy_context = phase1_json
    if policy_lines:
        policy_context += "\n\n=== RELEVANT POLICIES ===\n" + "\n".join(policy_lines)
    gaps = _invoke_structured(
        _PHASE3_POLICY_GAP_PROMPT, policy_context, PolicyGapResult
    )

    # ── Compress Phases 1-3 before Phase 4 ──────────────────────
    # Instead of dumping the full raw JSON (which can easily exceed 10K tokens
    # and cause "lost in the middle" dilution), we produce a plain-text digest
    # that surfaces ALL signals (document inventory, every risk, every conflict,
    # every missing action/question) — no arbitrary top-N truncation.
    compressed_context = _compress_phase_results(
        doc_inventory, phase1_results, conflicts, gaps
    )
    logger.debug(
        "Phase 4 context compressed: %d chars (was ~%d chars raw JSON)",
        len(compressed_context),
        len(
            json.dumps(
                {
                    "phase1_per_document": [r.model_dump() for r in phase1_results],
                    "phase2_conflicts": conflicts.model_dump(),
                    "phase3_policy_gaps": gaps.model_dump(),
                },
                indent=2,
            )
        ),
    )

    # ── Phase 4: Executive summary (reads compressed digest) ──
    summary_result = _invoke_structured(
        _PHASE4_SUMMARY_PROMPT, compressed_context, SummaryResult
    )

    # ── Assemble ──
    return ExtractionResult(
        summary=summary_result.summary,
        facts=[f for r in phase1_results for f in r.facts],
        decisions=[d for r in phase1_results for d in r.decisions],
        assumptions=[a for r in phase1_results for a in r.assumptions],
        risks=[risk for r in phase1_results for risk in r.risks],
        open_questions=[q for r in phase1_results for q in r.open_questions],
        action_items=[a for r in phase1_results for a in r.action_items],
        document_conflicts=conflicts.conflicts,
        repeated_statements=conflicts.repeated_statements,
        missing_actions=gaps.missing_actions,
        missing_questions=gaps.missing_questions,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 4 Compression (CHANGE 2)
# ═══════════════════════════════════════════════════════════════════════════════


def _compress_phase_results(
    doc_inventory: list[tuple[str, str]],
    phase1_results: list[PerDocumentExtraction],
    conflicts: ConflictDetectionResult,
    gaps: PolicyGapResult,
) -> str:
    """Compress multi-phase extraction results into a concise digest for Phase 4.

    Without this step, the full JSON dump of Phases 1-3 can exceed 10K tokens,
    causing the LLM to suffer "lost in the middle" context dilution.  This
    function surfaces ALL signals in a compact plain-text format:
      - Document inventory (filename + type)
      - Aggregate extraction stats
      - Every risk (all severities, sorted critical→low)
      - Every cross-document conflict
      - Every missing action (all urgencies, sorted critical→low)
      - Every missing question (all urgencies, sorted critical→low)

    Returns a plain-text digest, keeping Phase 4 focused on synthesis.
    """
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    parts: list[str] = []

    # ── Document inventory ──
    parts.append("=== DOCUMENT INVENTORY ===")
    for filename, doc_type in doc_inventory:
        parts.append(f"  - {filename}: {doc_type}")

    # ── Aggregate stats ──
    total_facts = sum(len(r.facts) for r in phase1_results)
    total_decisions = sum(len(r.decisions) for r in phase1_results)
    total_risks = sum(len(r.risks) for r in phase1_results)
    total_assumptions = sum(len(r.assumptions) for r in phase1_results)
    total_open_q = sum(len(r.open_questions) for r in phase1_results)
    total_actions = sum(len(r.action_items) for r in phase1_results)

    parts.append("\n=== EXTRACTION STATS ===")
    parts.append(
        f"  Facts: {total_facts}, Decisions: {total_decisions}, "
        f"Risks: {total_risks}, Assumptions: {total_assumptions}"
    )
    parts.append(f"  Open Questions: {total_open_q}, " f"Action Items: {total_actions}")

    # ── All risks (all severities, sorted critical→low) ──
    all_risks = [
        (r, severity_order.get(r.severity, 99)) for p in phase1_results for r in p.risks
    ]
    all_risks.sort(key=lambda x: x[1])
    if all_risks:
        parts.append(f"\n=== RISKS ({len(all_risks)} total) ===")
        for r, _ in all_risks:
            parts.append(
                f"  [{r.severity.upper()}] {r.content[:200]} "
                f"(source: {r.source_document}, {r.source_section})"
            )

    # ── All conflicts ──
    if conflicts.conflicts:
        parts.append(
            f"\n=== CROSS-DOCUMENT CONFLICTS " f"({len(conflicts.conflicts)} total) ==="
        )
        for c in conflicts.conflicts:
            parts.append(
                f"  - {c.document_a} vs {c.document_b}: " f"{c.statement_a[:150]}..."
            )
            if c.resolution_suggestion:
                parts.append(f"    Resolution: {c.resolution_suggestion[:150]}")

    # ── All missing actions (all urgencies, sorted critical→low) ──
    sorted_actions = sorted(
        gaps.missing_actions,
        key=lambda a: severity_order.get(a.urgency, 99),
    )
    if sorted_actions:
        parts.append(f"\n=== MISSING ACTIONS " f"({len(sorted_actions)} total) ===")
        for a in sorted_actions:
            parts.append(
                f"  [{a.urgency.upper()}] {a.description[:200]} "
                f"(policy: {a.policy_reference})"
            )

    # ── All missing questions (all urgencies, sorted critical→low) ──
    sorted_questions = sorted(
        gaps.missing_questions,
        key=lambda q: severity_order.get(q.urgency, 99),
    )
    if sorted_questions:
        parts.append(f"\n=== MISSING QUESTIONS " f"({len(sorted_questions)} total) ===")
        for q in sorted_questions:
            parts.append(
                f"  [{q.urgency.upper()}] {q.question[:200]} "
                f"(policy: {q.policy_reference})"
            )

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  Shared Utilities
# ═══════════════════════════════════════════════════════════════════════════════


def _build_llm():
    """Create a fresh ChatOllama instance with project settings."""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        temperature=0,
        base_url=settings.OLLAMA_BASE_URL,
        num_ctx=settings.OLLAMA_NUM_CTX,
        num_predict=settings.OLLAMA_NUM_PREDICT,
        timeout=300.0,
    )


def _invoke_structured(
    system_prompt: str,
    context: str,
    schema: type,
):
    """Invoke the LLM with Ollama's native JSON schema mode.

    with_structured_output() constrains token sampling to produce only
    valid JSON matching the Pydantic schema exactly — wrong field names,
    single-quotes, unterminated strings, and extra keys are all impossible.
    The return value is a fully validated Pydantic instance, no post-hoc
    parsing or synonym mapping needed.
    """
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        temperature=0,
        base_url=settings.OLLAMA_BASE_URL,
        num_ctx=settings.OLLAMA_NUM_CTX,
        num_predict=settings.OLLAMA_NUM_PREDICT,
    )
    structured_llm = llm.with_structured_output(schema, method="json_schema")

    schema_name = schema.__name__
    logger.debug("Invoking %s (context=%d chars)", schema_name, len(context))
    try:
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=context),
            ]
        )
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
    """Fetch chunks for each document, ordered by chunk_index."""
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
    """Build a human-readable section label from chunk_index and metadata."""
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
    """Semantically search FAISS for policy chunks and filter to public docs."""
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
