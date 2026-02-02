"""
Tests for detectability classification.

Per LOGIC_DESIGN.md:
- Deterministic behavior
- Does NOT affect runtime logic
- Lives in evaluation/reporting code only
"""

import pytest
from scripts.evaluation.detectability import (
    DetectabilityStatus,
    ImplantedError,
    DetectabilityResult,
    classify_detectability,
    classify_all_chapters,
    get_detectability_summary,
    format_detectability_report,
)
from scripts.extraction.extraction_diagnostics import (
    ChapterDiagnostic,
    EvidenceType,
    EvidenceRecord,
)


class TestDetectabilityStatus:
    """Tests for DetectabilityStatus enum."""
    
    def test_enum_values(self):
        """Should have all expected values."""
        assert DetectabilityStatus.DETECTED.value == "detected"
        assert DetectabilityStatus.DETECTABLE_BUT_MISSED.value == "detectable_but_missed"
        assert DetectabilityStatus.UNDETECTABLE_BY_DESIGN.value == "undetectable_by_design"


class TestImplantedError:
    """Tests for ImplantedError dataclass."""
    
    def test_creation(self):
        """Should create ImplantedError with all fields."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Hostile character shows kindness",
            required_evidence_types=[EvidenceType.EMOTIONAL],
            expected_violation_rule="emotional_mismatch",
        )
        assert error.chapter_id == "ch5"
        assert error.error_type == "emotional_inconsistency"
        assert EvidenceType.EMOTIONAL in error.required_evidence_types


class TestClassifyDetectability:
    """Tests for classify_detectability function."""
    
    def test_no_implanted_error(self):
        """Should classify as DETECTED when no error implanted."""
        result = classify_detectability(
            chapter_id="ch1",
            implanted_error=None,
            extraction_diagnostic=None,
            asp_violations=[],
        )
        
        assert result.status == DetectabilityStatus.DETECTED
        assert "No implanted error" in result.notes[0]
    
    def test_detected_via_violation(self):
        """Should classify as DETECTED when ASP violation matches."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Hostile shows kindness",
            required_evidence_types=[EvidenceType.EMOTIONAL],
            expected_violation_rule="emotional_mismatch",
        )
        
        violations = [{"rule": "emotional_mismatch", "chapter": "ch5"}]
        
        result = classify_detectability(
            chapter_id="ch5",
            implanted_error=error,
            extraction_diagnostic=None,
            asp_violations=violations,
        )
        
        assert result.status == DetectabilityStatus.DETECTED
        assert result.expected_violation_matched is True
        assert "emotional_mismatch" in result.asp_violations_found
    
    def test_detected_via_related_violation(self):
        """Should classify as DETECTED when related ASP rule fires."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Hostile shows kindness",
            required_evidence_types=[EvidenceType.EMOTIONAL],
        )
        
        # Different but related violation
        violations = [{"rule": "hostile_kindness_violation"}]
        
        result = classify_detectability(
            chapter_id="ch5",
            implanted_error=error,
            extraction_diagnostic=None,
            asp_violations=violations,
        )
        
        assert result.status == DetectabilityStatus.DETECTED
    
    def test_detectable_but_missed(self):
        """Should classify as DETECTABLE_BUT_MISSED when predicates exist but no violation."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Hostile shows kindness",
            required_evidence_types=[EvidenceType.EMOTIONAL],
        )
        
        # Create diagnostic showing emotional predicates were extracted
        diag = ChapterDiagnostic(chapter_id="ch5")
        diag.evidence_records[EvidenceType.EMOTIONAL].detected = True
        diag.evidence_records[EvidenceType.EMOTIONAL].predicate_emitted = True
        
        result = classify_detectability(
            chapter_id="ch5",
            implanted_error=error,
            extraction_diagnostic=diag,
            asp_violations=[],  # No violations!
        )
        
        assert result.status == DetectabilityStatus.DETECTABLE_BUT_MISSED
        assert EvidenceType.EMOTIONAL in result.present_evidence_types
        assert "logic/normalization/integration bug" in result.notes[1]
    
    def test_undetectable_under_extracted(self):
        """Should classify as UNDETECTABLE when evidence was under-extracted."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Hostile shows kindness",
            required_evidence_types=[EvidenceType.EMOTIONAL],
        )
        
        # Create diagnostic showing emotional evidence detected but not extracted
        diag = ChapterDiagnostic(chapter_id="ch5")
        diag.evidence_records[EvidenceType.EMOTIONAL].detected = True
        diag.evidence_records[EvidenceType.EMOTIONAL].predicate_emitted = False  # Under-extracted!
        
        result = classify_detectability(
            chapter_id="ch5",
            implanted_error=error,
            extraction_diagnostic=diag,
            asp_violations=[],
        )
        
        assert result.status == DetectabilityStatus.UNDETECTABLE_BY_DESIGN
        assert EvidenceType.EMOTIONAL in result.under_extracted_types
        assert "Under-extraction prevented detection" in result.notes[1]
    
    def test_undetectable_no_evidence(self):
        """Should classify as UNDETECTABLE when required evidence not found."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="temporal_violation",
            description="Timeline error",
            required_evidence_types=[EvidenceType.TEMPORAL],
        )
        
        # Create diagnostic showing no temporal evidence
        diag = ChapterDiagnostic(chapter_id="ch5")
        diag.evidence_records[EvidenceType.TEMPORAL].detected = False
        diag.evidence_records[EvidenceType.TEMPORAL].predicate_emitted = False
        
        result = classify_detectability(
            chapter_id="ch5",
            implanted_error=error,
            extraction_diagnostic=diag,
            asp_violations=[],
        )
        
        assert result.status == DetectabilityStatus.UNDETECTABLE_BY_DESIGN


class TestDetectabilityResultToDict:
    """Tests for DetectabilityResult serialization."""
    
    def test_to_dict(self):
        """Should serialize to dictionary correctly."""
        error = ImplantedError(
            chapter_id="ch5",
            error_type="emotional_inconsistency",
            description="Test error",
            required_evidence_types=[],
        )
        
        result = DetectabilityResult(
            chapter_id="ch5",
            implanted_error=error,
            status=DetectabilityStatus.DETECTED,
            asp_violations_found=["emotional_mismatch"],
            expected_violation_matched=True,
        )
        
        d = result.to_dict()
        
        assert d["chapter_id"] == "ch5"
        assert d["detectability_status"] == "detected"
        assert d["implanted_error"]["type"] == "emotional_inconsistency"
        assert d["expected_violation_matched"] is True


class TestClassifyAllChapters:
    """Tests for batch classification."""
    
    def test_classifies_all_chapters(self):
        """Should classify all provided chapters."""
        errors = {
            "ch5": ImplantedError(
                chapter_id="ch5",
                error_type="emotional_inconsistency",
                description="Test",
                required_evidence_types=[EvidenceType.EMOTIONAL],
            ),
        }
        
        diagnostics = {
            "ch5": ChapterDiagnostic(chapter_id="ch5"),
        }
        diagnostics["ch5"].evidence_records[EvidenceType.EMOTIONAL].detected = True
        diagnostics["ch5"].evidence_records[EvidenceType.EMOTIONAL].predicate_emitted = True
        
        asp_results = {
            "ch5": [{"rule": "emotional_mismatch"}],
        }
        
        results = classify_all_chapters(errors, diagnostics, asp_results)
        
        assert len(results) == 1
        assert results[0].chapter_id == "ch5"
        assert results[0].status == DetectabilityStatus.DETECTED


class TestGetDetectabilitySummary:
    """Tests for summary generation."""
    
    def test_summary_with_mixed_results(self):
        """Should correctly summarize mixed results."""
        error = ImplantedError(
            chapter_id="test",
            error_type="test",
            description="test",
            required_evidence_types=[],
        )
        
        results = [
            DetectabilityResult(
                chapter_id="ch1",
                implanted_error=error,
                status=DetectabilityStatus.DETECTED,
            ),
            DetectabilityResult(
                chapter_id="ch2",
                implanted_error=error,
                status=DetectabilityStatus.DETECTABLE_BUT_MISSED,
            ),
            DetectabilityResult(
                chapter_id="ch3",
                implanted_error=error,
                status=DetectabilityStatus.UNDETECTABLE_BY_DESIGN,
            ),
            DetectabilityResult(
                chapter_id="ch4",
                implanted_error=None,  # No error
                status=DetectabilityStatus.DETECTED,
            ),
        ]
        
        summary = get_detectability_summary(results)
        
        assert summary["total_chapters"] == 4
        assert summary["with_implanted_errors"] == 3
        assert summary["detected"] == 1
        assert summary["detectable_but_missed"] == 1
        assert summary["undetectable_by_design"] == 1
        assert summary["detection_rate"] == pytest.approx(1/3)
        assert summary["potential_detection_rate"] == pytest.approx(2/3)
    
    def test_empty_results(self):
        """Should handle empty results."""
        summary = get_detectability_summary([])
        
        assert summary["total_chapters"] == 0
        assert summary["detection_rate"] == 0.0


class TestFormatDetectabilityReport:
    """Tests for report formatting."""
    
    def test_formats_report(self):
        """Should format a readable report."""
        summary = {
            "total_chapters": 10,
            "with_implanted_errors": 5,
            "detected": 2,
            "detectable_but_missed": 1,
            "undetectable_by_design": 2,
            "detection_rate": 0.4,
            "potential_detection_rate": 0.6,
            "detected_chapters": ["ch1", "ch3"],
            "missed_chapters": ["ch5"],
            "undetectable_chapters": ["ch7", "ch9"],
        }
        
        report = format_detectability_report(summary)
        
        assert "DETECTABILITY CLASSIFICATION REPORT" in report
        assert "DETECTED:                 2" in report
        assert "DETECTABLE_BUT_MISSED:   1" in report
        assert "40.0%" in report
        assert "ch5" in report
