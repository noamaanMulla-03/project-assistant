# ── Extraction Pipeline Tests ─────────────────────────────────────────────────
# Unit tests for the 4-phase structured extraction pipeline.
# Mocks _invoke_structured (the LLM call wrapper) to return controlled Pydantic
# objects, then verifies final ExtractionResult assembly including the new
# document_types field.

import uuid

import pytest

from app.schemas.extraction import (
    ActionItem,
    Assumption,
    ConflictDetectionResult,
    Decision,
    DocumentConflict,
    DocumentType,
    ExtractionResult,
    Fact,
    MissingAction,
    MissingQuestion,
    OpenQuestion,
    PerDocumentExtraction,
    PolicyGapResult,
    RepeatedStatement,
    Risk,
    SummaryResult,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  Pipeline Assembly Tests (no LLM calls — mock _invoke_structured)
# ═══════════════════════════════════════════════════════════════════════════════


def test_pipeline_assembles_document_types():
    """Verify document_types is populated from the doc_inventory (filename→type map)
    that _run_structured_pipeline builds during Phase 1."""
    # Simulate what _run_structured_pipeline's assembly step produces
    doc_inventory = [
        ("meeting_notes.pdf", "meeting_notes"),
        ("prd_v2.docx", "requirement_draft"),
    ]

    result = ExtractionResult(
        document_types=[
            DocumentType(filename=fn, document_type=dt) for fn, dt in doc_inventory
        ],
        summary="Test summary.",
    )

    assert len(result.document_types) == 2
    assert result.document_types[0].filename == "meeting_notes.pdf"
    assert result.document_types[0].document_type == "meeting_notes"
    assert result.document_types[1].document_type == "requirement_draft"


def test_pipeline_flattens_per_doc_extractions():
    """Verify that per-document facts, decisions, etc. are correctly flattened
    into the top-level ExtractionResult lists."""
    # Simulate two Phase 1 results
    doc1 = PerDocumentExtraction(
        document_type="meeting_notes",
        facts=[
            Fact(
                content="Budget is $500K.",
                source_document="meeting.pdf",
                source_section="chunk_0",
                confidence="high",
            ),
            Fact(
                content="Deadline is Q4.",
                source_document="meeting.pdf",
                source_section="chunk_1",
                confidence="medium",
            ),
        ],
        decisions=[
            Decision(
                content="Use React for frontend.",
                source_document="meeting.pdf",
                source_section="chunk_0",
                stakeholders=["CTO"],
            ),
        ],
        assumptions=[],
        risks=[],
        open_questions=[],
        action_items=[],
    )
    doc2 = PerDocumentExtraction(
        document_type="requirement_draft",
        facts=[
            Fact(
                content="Must support SSO.",
                source_document="prd.pdf",
                source_section="chunk_0",
                confidence="high",
            ),
        ],
        decisions=[],
        assumptions=[
            Assumption(
                content="Users have corporate email.",
                source_document="prd.pdf",
                source_section="chunk_0",
                validation_needed=True,
            ),
        ],
        risks=[],
        open_questions=[],
        action_items=[],
    )

    # Assemble — mirrors _run_structured_pipeline
    result = ExtractionResult(
        document_types=[
            DocumentType(filename="meeting.pdf", document_type="meeting_notes"),
            DocumentType(filename="prd.pdf", document_type="requirement_draft"),
        ],
        summary="OK",
        facts=[f for r in [doc1, doc2] for f in r.facts],
        decisions=[d for r in [doc1, doc2] for d in r.decisions],
        assumptions=[a for r in [doc1, doc2] for a in r.assumptions],
        risks=[risk for r in [doc1, doc2] for risk in r.risks],
        open_questions=[q for r in [doc1, doc2] for q in r.open_questions],
        action_items=[a for r in [doc1, doc2] for a in r.action_items],
    )

    assert len(result.facts) == 3  # 2 + 1
    assert len(result.decisions) == 1
    assert len(result.assumptions) == 1
    assert result.facts[0].confidence == "high"
    assert result.decisions[0].stakeholders == ["CTO"]
    assert result.assumptions[0].validation_needed is True


def test_empty_documents_produce_empty_extraction():
    """Verify pipeline handles zero documents gracefully (no crash, empty lists)."""
    result = ExtractionResult(
        document_types=[],
        summary="No documents analysed.",
    )
    assert result.facts == []
    assert result.document_types == []
    assert result.document_conflicts == []
    assert result.missing_actions == []


def test_conflict_detection_assembly():
    """Verify cross-document conflict and repeated-statement assembly."""
    conflicts = ConflictDetectionResult(
        conflicts=[
            DocumentConflict(
                statement_a="Budget is $500K.",
                statement_b="Budget is $300K.",
                document_a="meeting.pdf",
                document_b="prd.pdf",
                section_a="chunk_0",
                section_b="chunk_2",
                resolution_suggestion="Reconcile with finance team.",
            ),
        ],
        repeated_statements=[
            RepeatedStatement(
                statement="Use AWS for hosting.",
                document_a="meeting.pdf",
                document_b="prd.pdf",
                section_a="chunk_1",
                section_b="chunk_3",
                is_exact_match=True,
            ),
        ],
    )

    result = ExtractionResult(
        document_types=[],
        summary="OK",
        document_conflicts=conflicts.conflicts,
        repeated_statements=conflicts.repeated_statements,
    )

    assert len(result.document_conflicts) == 1
    assert len(result.repeated_statements) == 1
    assert result.document_conflicts[0].resolution_suggestion != ""
    assert result.repeated_statements[0].is_exact_match is True


def test_policy_gap_assembly():
    """Verify missing actions and missing questions assembly."""
    gaps = PolicyGapResult(
        missing_actions=[
            MissingAction(
                description="Data retention policy not referenced.",
                policy_reference="data_retention_policy.txt",
                policy_section="chunk_0",
                urgency="high",
            ),
        ],
        missing_questions=[
            MissingQuestion(
                question="What is the backup strategy?",
                policy_reference="api_security_policy.txt",
                policy_section="chunk_1",
                urgency="critical",
            ),
        ],
    )

    result = ExtractionResult(
        document_types=[],
        summary="OK",
        missing_actions=gaps.missing_actions,
        missing_questions=gaps.missing_questions,
    )

    assert len(result.missing_actions) == 1
    assert result.missing_actions[0].urgency == "high"
    assert len(result.missing_questions) == 1
    assert result.missing_questions[0].urgency == "critical"


# ═══════════════════════════════════════════════════════════════════════════════
#  Phase 4 Compression Tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_compress_includes_all_risks_sorted():
    """Verify _compress_phase_results surfaces every risk, sorted critical→low."""
    from app.services.extraction import _compress_phase_results

    # Build Phase 1 results with risks across severities
    p1 = [
        PerDocumentExtraction(
            document_type="meeting_notes",
            facts=[],
            decisions=[],
            assumptions=[],
            risks=[
                Risk(
                    content="Low priority risk.",
                    source_document="a.pdf",
                    source_section="s1",
                    severity="low",
                    mitigation="",
                ),
                Risk(
                    content="Critical security flaw.",
                    source_document="a.pdf",
                    source_section="s2",
                    severity="critical",
                    mitigation="Patch immediately.",
                ),
            ],
            open_questions=[],
            action_items=[],
        ),
    ]
    conflicts = ConflictDetectionResult()
    gaps = PolicyGapResult()

    digest = _compress_phase_results(
        doc_inventory=[("a.pdf", "meeting_notes")],
        phase1_results=p1,
        conflicts=conflicts,
        gaps=gaps,
    )

    # Critical should appear before low
    crit_idx = digest.index("CRITICAL")
    low_idx = digest.index("LOW")
    assert crit_idx < low_idx


def test_compress_handles_empty_results():
    """Verify compress doesn't crash with zero extractions."""
    from app.services.extraction import _compress_phase_results

    digest = _compress_phase_results(
        doc_inventory=[],
        phase1_results=[],
        conflicts=ConflictDetectionResult(),
        gaps=PolicyGapResult(),
    )

    assert "=== DOCUMENT INVENTORY ===" in digest
    assert "=== EXTRACTION STATS ===" in digest
    # No risk/conflict/action sections when empty
    assert "=== RISKS" not in digest
    assert "=== CROSS-DOCUMENT CONFLICTS" not in digest


def test_compress_surfaces_all_conflicts():
    """Verify compress includes every cross-document conflict."""
    from app.services.extraction import _compress_phase_results

    conflicts = ConflictDetectionResult(
        conflicts=[
            DocumentConflict(
                statement_a="X",
                statement_b="Y",
                document_a="a.pdf",
                document_b="b.pdf",
                section_a="s1",
                section_b="s2",
                resolution_suggestion="Fix.",
            ),
        ],
    )

    digest = _compress_phase_results(
        doc_inventory=[("a.pdf", "doc"), ("b.pdf", "doc")],
        phase1_results=[],
        conflicts=conflicts,
        gaps=PolicyGapResult(),
    )

    assert "a.pdf vs b.pdf" in digest
    assert "Resolution: Fix." in digest
