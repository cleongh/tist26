"""
Tests for temporal extraction diagnostics.

Per LOGIC_DESIGN.md:
- Diagnostics do NOT affect logic
- Diagnostics do NOT block execution
- Diagnostics are logged for evaluation
"""

import pytest
from scripts.extraction.temporal_diagnostics import (
    scan_for_temporal_markers,
    check_after_links,
    check_temporal_constraints,
    analyze_temporal_extraction,
    get_temporal_diagnostic_summary,
    TemporalDiagnostic,
)


class TestScanForTemporalMarkers:
    """Tests for temporal marker scanning."""
    
    def test_finds_before(self):
        """Should detect 'before' as temporal marker."""
        text = "Before Harry could leave, Hagrid arrived."
        markers = scan_for_temporal_markers(text)
        assert "before" in markers
    
    def test_finds_after(self):
        """Should detect 'after' as temporal marker."""
        text = "After the feast ended, they went to bed."
        markers = scan_for_temporal_markers(text)
        assert "after" in markers
    
    def test_finds_had_already(self):
        """Should detect 'had already' as temporal marker."""
        text = "She had already left earlier that morning."
        markers = scan_for_temporal_markers(text)
        assert "had already" in markers
    
    def test_finds_previously(self):
        """Should detect 'previously' as temporal marker."""
        text = "He had previously visited the castle."
        markers = scan_for_temporal_markers(text)
        assert "previously" in markers
    
    def test_finds_multiple_markers(self):
        """Should detect multiple distinct markers."""
        text = "Before the sun rose, after much deliberation, they had already decided."
        markers = scan_for_temporal_markers(text)
        assert "before" in markers
        assert "after" in markers
        assert "had already" in markers
    
    def test_no_markers_in_neutral_text(self):
        """Should return empty list for text without temporal markers."""
        text = "Harry walked into the room and sat down."
        markers = scan_for_temporal_markers(text)
        assert len(markers) == 0
    
    def test_case_insensitive(self):
        """Should detect markers regardless of case."""
        text = "BEFORE he could react, AFTER the explosion, Previously known dangers emerged."
        markers = scan_for_temporal_markers(text)
        assert "before" in markers
        assert "after" in markers
        assert "previously" in markers


class TestCheckAfterLinks:
    """Tests for after-link detection in events."""
    
    def test_detects_after_link(self):
        """Should return True when event has non-null after."""
        events = [
            {"id": "e1", "type": "arrive", "after": None},
            {"id": "e2", "type": "talk", "after": "e1"},
        ]
        assert check_after_links(events) is True
    
    def test_no_after_links(self):
        """Should return False when no events have after links."""
        events = [
            {"id": "e1", "type": "arrive", "after": None},
            {"id": "e2", "type": "talk", "after": None},
        ]
        assert check_after_links(events) is False
    
    def test_empty_events(self):
        """Should return False for empty events list."""
        assert check_after_links([]) is False
    
    def test_string_null_after(self):
        """Should treat string 'null' as no after link."""
        events = [
            {"id": "e1", "type": "arrive", "after": "null"},
        ]
        assert check_after_links(events) is False
    
    def test_empty_string_after(self):
        """Should treat empty string as no after link."""
        events = [
            {"id": "e1", "type": "arrive", "after": ""},
        ]
        assert check_after_links(events) is False


class TestCheckTemporalConstraints:
    """Tests for temporal constraints detection."""
    
    def test_detects_constraints(self):
        """Should return True when temporal_constraints has entries."""
        result = {
            "events": [],
            "temporal_constraints": [
                {"type": "previous", "event": "leave", "reference": "earlier"}
            ]
        }
        assert check_temporal_constraints(result) is True
    
    def test_no_constraints(self):
        """Should return False when temporal_constraints is empty."""
        result = {
            "events": [],
            "temporal_constraints": []
        }
        assert check_temporal_constraints(result) is False
    
    def test_missing_constraints_key(self):
        """Should return False when temporal_constraints key is missing."""
        result = {"events": []}
        assert check_temporal_constraints(result) is False


class TestAnalyzeTemporalExtraction:
    """Tests for full temporal extraction analysis."""
    
    def test_recall_failure_detected(self):
        """Should detect recall failure when temporal language exists but no predicates."""
        chapter_text = "Before Harry could leave, Hagrid arrived."
        extraction_result = {
            "events": [{"id": "e1", "type": "arrive", "after": None}],
            "temporal_constraints": []
        }
        
        diagnostic = analyze_temporal_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=False,  # Don't log in tests
        )
        
        assert diagnostic.temporal_language_detected is True
        assert diagnostic.temporal_predicates_extracted is False
        assert diagnostic.recall_failure is True
        assert "before" in diagnostic.temporal_markers_found
    
    def test_no_recall_failure_with_after_link(self):
        """Should NOT flag recall failure when after links exist."""
        chapter_text = "After the feast ended, they went to bed."
        extraction_result = {
            "events": [
                {"id": "e1", "type": "feast", "after": None},
                {"id": "e2", "type": "leave", "after": "e1"},
            ],
            "temporal_constraints": []
        }
        
        diagnostic = analyze_temporal_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=False,
        )
        
        assert diagnostic.temporal_language_detected is True
        assert diagnostic.temporal_predicates_extracted is True
        assert diagnostic.recall_failure is False
    
    def test_no_recall_failure_with_temporal_constraints(self):
        """Should NOT flag recall failure when temporal_constraints exist."""
        chapter_text = "She had already left earlier that morning."
        extraction_result = {
            "events": [],
            "temporal_constraints": [
                {"type": "previous", "event": "leave", "reference": "earlier that morning"}
            ]
        }
        
        diagnostic = analyze_temporal_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=False,
        )
        
        assert diagnostic.temporal_language_detected is True
        assert diagnostic.temporal_predicates_extracted is True
        assert diagnostic.recall_failure is False
    
    def test_no_temporal_language_no_failure(self):
        """Should NOT flag recall failure when no temporal language exists."""
        chapter_text = "Harry walked into the room and sat down."
        extraction_result = {
            "events": [{"id": "e1", "type": "arrive", "after": None}],
            "temporal_constraints": []
        }
        
        diagnostic = analyze_temporal_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=False,
        )
        
        assert diagnostic.temporal_language_detected is False
        assert diagnostic.recall_failure is False


class TestGetTemporalDiagnosticSummary:
    """Tests for summary generation across multiple chapters."""
    
    def test_summary_with_failures(self):
        """Should correctly summarize diagnostics with recall failures."""
        diagnostics = [
            TemporalDiagnostic(
                chapter_id="ch1",
                temporal_markers_found=["before"],
                has_after_links=False,
                has_temporal_constraints=False,
            ),
            TemporalDiagnostic(
                chapter_id="ch2",
                temporal_markers_found=["after"],
                has_after_links=True,
                has_temporal_constraints=False,
            ),
            TemporalDiagnostic(
                chapter_id="ch3",
                temporal_markers_found=[],
                has_after_links=False,
                has_temporal_constraints=False,
            ),
        ]
        
        summary = get_temporal_diagnostic_summary(diagnostics)
        
        assert summary["total_chapters"] == 3
        assert summary["chapters_with_temporal_language"] == 2
        assert summary["chapters_with_temporal_predicates"] == 1
        assert summary["recall_failures"] == 1
        assert "ch1" in summary["failed_chapters"]
        assert "ch2" not in summary["failed_chapters"]
    
    def test_empty_diagnostics(self):
        """Should handle empty diagnostics list."""
        summary = get_temporal_diagnostic_summary([])
        
        assert summary["total_chapters"] == 0
        assert summary["recall_failures"] == 0
        assert summary["recall_failure_rate"] == 0.0
