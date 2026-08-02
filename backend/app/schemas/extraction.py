# ── Extraction Schemas ────────────────────────────────────────────────────────
# Strict Pydantic models that define the JSON contract for the LLM extraction
# pipeline.  ChatOllama.with_structured_output() binds these schemas so the
# frontend always receives perfectly typed, validated payloads.
#
# Design principles:
#   • Every extracted item carries mandatory source_document + source_section
#     so the frontend can highlight the originating text in the document viewer.
#   • All list fields default to [] — the LLM can never omit a key, which keeps
#     the frontend safe from undefined-access errors.
#   • ExtractionResult uses extra="forbid" to catch hallucinations.

from pydantic import BaseModel, Field
from typing import Literal

# ── Shared Base ───────────────────────────────────────────────────────────────


class ExtractionItem(BaseModel):
    """Base for all extracted facts, decisions, assumptions, etc.

    Every single item must reference its source so the UI can render
    inline highlights on the originating document.
    """

    content: str = Field(
        ...,
        description="The extracted information text — verbatim or lightly paraphrased",
    )
    source_document: str = Field(
        ...,
        description="Filename of the document this item was extracted from (match the [DOCUMENT: ...] header)",
    )
    source_section: str = Field(
        ...,
        description="Section/chunk identifier from the source document (match the [SECTION: ...] header)",
    )


# ── Typed Extraction Items ───────────────────────────────────────────────────


class Fact(ExtractionItem):
    """A confirmed, verifiable statement from the source documents."""

    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level: 'high' | 'medium' | 'low'",
        examples=["high"],
    )


class Decision(ExtractionItem):
    """A decision that was made, as recorded in the source documents."""

    stakeholders: list[str] = Field(
        default_factory=list,
        description="People, roles, or teams involved in or affected by this decision",
    )


class Assumption(ExtractionItem):
    """An unverified premise that the document relies on."""

    validation_needed: bool = Field(
        default=True,
        description="Whether this assumption should be flagged for human validation",
    )


class Risk(ExtractionItem):
    """A potential negative outcome or threat identified in the source."""

    severity: Literal["critical", "high", "medium", "low"] = Field(
        ...,
        description="Severity: 'critical' | 'high' | 'medium' | 'low'",
    )
    mitigation: str = Field(
        default="",
        description="Mitigation strategy if mentioned in the source, otherwise empty",
    )


class OpenQuestion(ExtractionItem):
    """An unanswered question raised by the documents."""

    suggested_owner: str = Field(
        default="",
        description="Person or role best suited to answer this question, if inferable",
    )


class ActionItem(ExtractionItem):
    """An explicit or implied task that needs to be done.

    NOTE: The LLM is instructed to extract action items that already exist
    in the documents — it must NEVER invent or auto-assign tasks.  The
    frontend renders these as read-only highlights, not as a task manager.
    """

    priority: Literal["high", "medium", "low"] = Field(
        ...,
        description="Priority/Importance: 'high' | 'medium' | 'low'",
    )
    deadline: str = Field(
        default="",
        description="Mentioned deadline or timeframe, empty if none specified",
    )


# ── Cross-Document Items (no source_document — each has two sources) ──────────


class DocumentConflict(BaseModel):
    """Two contradictory statements found across the loaded project documents."""

    statement_a: str = Field(
        ...,
        description="The first conflicting statement (verbatim or lightly paraphrased)",
    )
    statement_b: str = Field(
        ...,
        description="The second conflicting statement (verbatim or lightly paraphrased)",
    )
    document_a: str = Field(
        ...,
        description="Filename of the document containing statement_a",
    )
    document_b: str = Field(
        ...,
        description="Filename of the document containing statement_b",
    )
    section_a: str = Field(
        ...,
        description="Section identifier in document_a",
    )
    section_b: str = Field(
        ...,
        description="Section identifier in document_b",
    )
    resolution_suggestion: str = Field(
        default="",
        description="Suggested way to resolve the conflict, if inferable",
    )


class RepeatedStatement(BaseModel):
    """A statement that appears identically or substantially similarly in
    two different project documents."""

    statement: str = Field(
        ...,
        description="The repeated content (verbatim or lightly paraphrased)",
    )
    document_a: str = Field(
        ...,
        description="Filename of the first document containing this statement",
    )
    document_b: str = Field(
        ...,
        description="Filename of the second document containing this statement",
    )
    section_a: str = Field(
        ...,
        description="Section identifier in document_a",
    )
    section_b: str = Field(
        ...,
        description="Section identifier in document_b",
    )
    is_exact_match: bool = Field(
        default=False,
        description="True if the statements are word-for-word identical",
    )


class MissingAction(BaseModel):
    """An action that is missing from the project documents but should exist
    based on organizational policies and standards."""

    description: str = Field(
        ...,
        description="Description of the missing action that should be added",
    )
    policy_reference: str = Field(
        ...,
        description="The policy document filename that mandates this action",
    )
    policy_section: str = Field(
        ...,
        description="Section/chunk identifier in the policy document",
    )
    urgency: Literal["critical", "high", "medium", "low"] = Field(
        ...,
        description="Urgency: 'critical' | 'high' | 'medium' | 'low'",
    )


class MissingQuestion(BaseModel):
    """A question that the project documents SHOULD be asking based on
    organizational policies, but currently aren't."""

    question: str = Field(
        ...,
        description="The question that should be asked but isn't",
    )
    policy_reference: str = Field(
        ...,
        description="The policy document filename that implies this question",
    )
    policy_section: str = Field(
        ...,
        description="Section/chunk identifier in the policy document",
    )
    urgency: Literal["critical", "high", "medium", "low"] = Field(
        ...,
        description="Urgency: 'critical' | 'high' | 'medium' | 'low'",
    )


# ── Intermediate Pipeline Schemas ────────────────────────────────────────────
# Each phase of the multi-step extraction pipeline has its own narrow output
# schema so the 7B model never has to do too much in one call.


class PerDocumentExtraction(BaseModel):
    """Phase 1 output: a single document's extracted findings.

    The pipeline runs one LLM call per project document, each call seeing
    ONLY that document's chunks.  This eliminates cross-document confusion
    and makes source attribution trivially correct.
    """

    document_type: str = Field(
        ...,
        description=(
            "Identified document type, e.g. 'geotechnical survey', "
            "'project charter', 'meeting notes', 'risk assessment'"
        ),
    )
    facts: list[Fact] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ConflictDetectionResult(BaseModel):
    """Phase 2 output: contradictions and repeated statements across documents.

    The LLM receives only structured summaries from Phase 1 (not raw chunks)
    so it can reason clearly about conflicts without re-reading source text.
    """

    conflicts: list[DocumentConflict] = Field(
        default_factory=list,
        description="Contradictory statements found across the provided document summaries",
    )
    repeated_statements: list[RepeatedStatement] = Field(
        default_factory=list,
        description="Identical or substantially similar statements found in multiple documents",
    )

    model_config = {"extra": "forbid"}


class PolicyGapResult(BaseModel):
    """Phase 3 output: actions and questions missing from project docs
    based on organizational policies.

    The LLM receives Phase 1 findings plus policy chunks retrieved by the
    backend using keywords derived from the extracted content.
    """

    missing_actions: list[MissingAction] = Field(
        default_factory=list,
        description="Actions that should exist based on policy but are absent from project docs",
    )
    missing_questions: list[MissingQuestion] = Field(
        default_factory=list,
        description="Questions the project should be asking based on policy but isn't",
    )

    model_config = {"extra": "forbid"}


class SummaryResult(BaseModel):
    """Phase 4 output: executive summary synthesising all phases."""

    summary: str = Field(
        ...,
        description="Executive summary covering document types, key themes, and cross-cutting concerns",
    )

    model_config = {"extra": "forbid"}


# ── Per-Document Type ────────────────────────────────────────────────────────


class DocumentType(BaseModel):
    """Identified type for a single project document."""

    filename: str = Field(
        ...,
        description="Original filename of the document",
    )
    document_type: str = Field(
        ...,
        description=(
            "Identified document type from the canonical taxonomy: "
            "meeting_notes, requirement_draft, implementation_notes, "
            "project_update, decision_record, or a custom short label"
        ),
    )


# ── Root Extraction Result ───────────────────────────────────────────────────


class ExtractionResult(BaseModel):
    """The complete structured output from the multi-step extraction pipeline.

    This is the top-level response returned by POST /projects/{id}/analyze.
    It is assembled by the backend orchestrator from four sequential phases:
      1. Per-document extraction (parallel LLM calls)
      2. Cross-document conflict detection
      3. Policy gap analysis (backend-searched policy chunks + LLM)
      4. Executive summary synthesis

    Every field defaults to [] so the frontend can safely iterate over
    every array without null checks.
    """

    document_types: list[DocumentType] = Field(
        default_factory=list,
        description="Per-document type classification (one entry per uploaded doc)",
    )
    summary: str = Field(
        ...,
        description=(
            "Executive summary of the extraction: document types identified, "
            "key themes, and notable cross-cutting concerns across all loaded files"
        ),
    )
    facts: list[Fact] = Field(
        default_factory=list,
        description="Confirmed, verifiable statements extracted from the documents",
    )
    decisions: list[Decision] = Field(
        default_factory=list,
        description="Decisions recorded in the documents",
    )
    assumptions: list[Assumption] = Field(
        default_factory=list,
        description="Unverified premises the documents rely on",
    )
    risks: list[Risk] = Field(
        default_factory=list,
        description="Potential negative outcomes or threats identified",
    )
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description="Unanswered questions raised by the documents",
    )
    action_items: list[ActionItem] = Field(
        default_factory=list,
        description="Tasks mentioned in the documents (NOT auto-generated)",
    )
    document_conflicts: list[DocumentConflict] = Field(
        default_factory=list,
        description="Contradictory statements found between the loaded project documents",
    )
    missing_actions: list[MissingAction] = Field(
        default_factory=list,
        description="Actions missing from the project documents based on applicable policies",
    )
    missing_questions: list[MissingQuestion] = Field(
        default_factory=list,
        description="Questions the project should be asking based on applicable policies",
    )
    repeated_statements: list[RepeatedStatement] = Field(
        default_factory=list,
        description="Identical or substantially similar statements found across multiple documents",
    )

    model_config = {"extra": "forbid"}
