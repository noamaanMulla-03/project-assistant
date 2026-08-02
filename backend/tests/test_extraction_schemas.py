import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    Fact,
    Risk,
    ExtractionItem,
    ConflictDetectionResult,
    DocumentConflict,
)


def test_fact_validates_confidence():
    """Test that Fact correctly enforces the confidence literal."""
    # Valid
    fact = Fact(
        content="The sky is blue.",
        source_document="doc1",
        source_section="intro",
        confidence="high",
    )
    assert fact.confidence == "high"

    # Invalid
    with pytest.raises(ValidationError):
        Fact(
            content="The sky is blue.",
            source_document="doc1",
            source_section="intro",
            confidence="absolute",  # Not high/medium/low
        )


def test_risk_validates_severity():
    """Test that Risk correctly enforces the severity literal."""
    # Valid
    risk = Risk(
        content="Project might run out of funding.",
        source_document="doc1",
        source_section="budget",
        severity="critical",
        mitigation="Secure more funding.",
    )
    assert risk.severity == "critical"

    # Invalid
    with pytest.raises(ValidationError):
        Risk(
            content="Project might run out of funding.",
            source_document="doc1",
            source_section="budget",
            severity="bad",  # Not critical/high/medium/low
            mitigation="None",
        )


def test_conflict_detection_result_empty():
    """Test that ConflictDetectionResult handles empty conflicts correctly."""
    result = ConflictDetectionResult(conflicts=[], repeated_statements=[])
    assert len(result.conflicts) == 0
    assert len(result.repeated_statements) == 0
