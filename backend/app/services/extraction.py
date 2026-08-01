# ── Extraction Service ────────────────────────────────────────────────────────
# LangChain tools agent that analyses 1-3 vectorized project documents against
# an organizational policy knowledge base.
#
# Architecture:
#   The LLM (qwen2.5:14b with strong function-calling) is given two tools:
#     1. retrieve_document_chunks(filename) — fetch chunks from pgvector
#     2. search_policy_kb(query)            — FAISS semantic search on policies
#   The agent autonomously explores: reads each document, searches for relevant
#   policies based on what it finds, then produces a natural-language summary.
#   The backend then feeds that summary + all tool outputs into a final
#   with_structured_output(ExtractionResult) call to produce typed JSON.

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.schemas.extraction import ExtractionResult

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

    try:
        agent_result = await asyncio.to_thread(_run_agent, doc_names, tools)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise RuntimeError(
            f"LLM agent failed: {exc}. "
            f"Check that Ollama is running and the model "
            f"'{settings.OLLAMA_MODEL}' is pulled."
        ) from exc

    full_context = await _compile_context(db, project_doc_ids, agent_result)

    logger.info(
        "Running final structured extraction (context=%d chars)", len(full_context)
    )
    return await asyncio.to_thread(
        _invoke_structured, _EXTRACTION_SYSTEM_PROMPT, full_context, ExtractionResult
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompts
# ═══════════════════════════════════════════════════════════════════════════════

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
4. When you have gathered sufficient information, produce a concise natural-
   language summary of what you found: document types, key themes, notable
   facts and decisions, risks identified, any apparent contradictions between
   documents, and policy areas that should be checked.
"""

_EXTRACTION_SYSTEM_PROMPT = """\
You are a human-in-the-loop document extraction assistant. You are given \
the complete text of project documents and relevant organizational policies. \
Your job is to produce a structured extraction — you do NOT make decisions \
or assign tasks.

The context contains:
  [DOCUMENT: <filename>]
  [SECTION: chunk <n> (<metadata>)]
  <text content>
  ... (chunks from all project documents)

  [POLICY: <filename>]
  [SECTION: chunk <n> (<metadata>)]
  <text content>
  ... (policy chunks found by the exploration agent)

Extract the following:

1. SUMMARY — Identify what type each DOCUMENT is and write an executive
   summary covering key themes, notable facts, decisions, risks, conflicts,
   and policy gaps across all loaded files.

2. FACTS — Confirmed, verifiable statements.  Assign confidence:
   'high' for definitive, 'medium' for qualified, 'low' for hedged.

3. DECISIONS — Choices made and recorded.  Include stakeholders when mentioned.

4. ASSUMPTIONS — Premises taken for granted without proof.
   Mark validation_needed=true unless trivially true.

5. RISKS — Potential negative outcomes, threats, or failure modes.
   Assign severity ('critical', 'high', 'medium', 'low') and include mitigation.

6. OPEN QUESTIONS — Questions the documents raise but don't answer.
   Suggest an owner role if inferable.

7. ACTION ITEMS — Tasks EXPLICITLY stated in the source text.
   NEVER invent or auto-assign tasks.  Empty list if none exist.

8. DOCUMENT CONFLICTS — Statements in different DOCUMENT blocks that
   contradict each other.  Quote both, name both documents, suggest resolution.

9. REPEATED STATEMENTS — Identical or substantially similar statements found
   in multiple documents.  Mark is_exact_match=true for word-for-word matches.

10. MISSING ACTIONS — Things that SHOULD exist based on the POLICY blocks
    but are absent from project documents.  Reference policy filename + section.

11. MISSING QUESTIONS — Questions the project SHOULD be asking based on
    policies but isn't.  Reference policy filename + section.

CRITICAL RULES:
- EVERY Fact, Decision, Assumption, Risk, OpenQuestion, and ActionItem MUST
  include 'source_document' (match the [DOCUMENT: ...] header) and
  'source_section' (match the [SECTION: ...] header).  Never leave them empty.
- DocumentConflict uses document_a/document_b and section_a/section_b.
- MissingAction and MissingQuestion use policy_reference and policy_section.
- Be thorough — extract too many items rather than miss something.
- Output ONLY valid JSON matching the schema exactly.  Every array field must
  be present, even if empty ([]).
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Tool Builder
# ═══════════════════════════════════════════════════════════════════════════════


async def _build_tools(
    db: AsyncSession,
    project_doc_ids: list[UUID],
) -> list:
    """Build two LangChain @tools as closures capturing db + doc_ids."""
    from langchain_core.tools import tool

    # Fetch document filename→id mapping directly (we're in the main event loop)
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(project_doc_ids))
    )
    doc_map = {d.filename: d.id for d in result.scalars().all()}

    @tool
    def retrieve_document_chunks(filename: str) -> str:
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
            return f"ERROR: Document '{filename}' not found. " f"Available: {available}"

        async def _fetch():
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

        try:
            return asyncio.run(_fetch())
        except Exception as exc:
            return f"ERROR retrieving document '{filename}': {exc}"

    @tool
    def search_policy_kb(query: str) -> str:
        """Search the organizational policy knowledge base.

        Use AFTER reading project documents to find policies relevant to
        specific topics, risks, or standards mentioned.  Use specific queries:
        instead of 'safety', search for 'fall protection scaffolding safety'.

        Args:
            query: Natural-language query for relevant policies/standards.

        Returns:
            Policy document chunks with [POLICY: ...] [SECTION: ...] labels.
        """

        async def _search():
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

        try:
            return asyncio.run(_search())
        except Exception as exc:
            return f"ERROR searching policy KB for '{query}': {exc}"

    logger.info("Built 2 tools for agent: %d document(s)", len(doc_map))
    return [retrieve_document_chunks, search_policy_kb]


# ═══════════════════════════════════════════════════════════════════════════════
#  Agent Runner
# ═══════════════════════════════════════════════════════════════════════════════


def _run_agent(doc_names: list[str], tools: list) -> dict:
    """Create and invoke the LangChain tools agent."""
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate

    llm = _build_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _AGENT_SYSTEM_PROMPT),
            ("human", _build_agent_input(doc_names)),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=settings.AGENT_MAX_ITERATIONS,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

    logger.info("Invoking agent (max %d iterations)", settings.AGENT_MAX_ITERATIONS)
    result = executor.invoke({"input": _build_agent_input(doc_names)})

    doc_outputs: list[tuple[str, str]] = []
    policy_outputs: list[tuple[str, str]] = []

    for action, observation in result.get("intermediate_steps", []):
        tool_name = action.tool
        tool_input = action.tool_input
        if tool_name == "retrieve_document_chunks":
            doc_outputs.append(
                (tool_input.get("filename", "unknown"), str(observation))
            )
        elif tool_name == "search_policy_kb":
            policy_outputs.append(
                (tool_input.get("query", "unknown"), str(observation))
            )

    logger.info(
        "Agent complete: %d doc calls, %d policy calls, "
        "%d iterations, output=%d chars",
        len(doc_outputs),
        len(policy_outputs),
        len(result.get("intermediate_steps", [])),
        len(str(result.get("output", ""))),
    )

    return {
        "summary": str(result.get("output", "")),
        "doc_outputs": doc_outputs,
        "policy_outputs": policy_outputs,
    }


def _build_agent_input(doc_names: list[str]) -> str:
    """Build the initial task description for the agent."""
    names_str = "\n".join(f"  - {n}" for n in doc_names)
    return (
        f"Analyse the following project document(s):\n{names_str}\n\n"
        f"Call retrieve_document_chunks() for each document, then use "
        f"search_policy_kb() to find relevant organizational policies "
        f"based on what you discover.  When finished, produce a summary "
        f"of what you found."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Context Compiler
# ═══════════════════════════════════════════════════════════════════════════════


async def _compile_context(
    db: AsyncSession,
    project_doc_ids: list[UUID],
    agent_result: dict,
) -> str:
    """Compile context from agent tool outputs + fresh DB reads."""
    parts: list[str] = []

    doc_data = await _fetch_document_data(db, project_doc_ids)
    for filename, chunks in doc_data:
        parts.append(f"[DOCUMENT: {filename}]")
        for content, section_label in chunks:
            parts.append(f"[SECTION: {section_label}]\n{content}\n")
        parts.append("")

    seen: set[str] = set()
    for _, output in agent_result.get("policy_outputs", []):
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("[POLICY:") and "[SECTION:" in line:
                if line not in seen:
                    seen.add(line)
                    parts.append(line)

    context = "\n".join(parts)
    logger.info("Compiled context: %d chars", len(context))
    return context


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
    )


def _invoke_structured(
    system_prompt: str,
    context: str,
    schema: type,
):
    """Invoke ChatOllama with structured output bound to *schema*."""
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
