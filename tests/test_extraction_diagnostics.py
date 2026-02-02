"""
Tests for extraction diagnostics layer.

Per LOGIC_DESIGN.md:
- Diagnostics do NOT affect logic
- Diagnostics do NOT block execution
- Deterministic behavior
"""

import pytest
from scripts.extraction.extraction_diagnostics import (
    EvidenceType,
    EvidenceMatch,
    EvidenceRecord,
    ChapterDiagnostic,
    scan_for_evidence,
    scan_all_evidence,
    check_temporal_predicates,
    check_emotional_predicates,
    check_appearance_predicates,
    check_location_predicates,
    analyze_chapter_extraction,
    get_extraction_diagnostic_summary,
    format_diagnostic_report,
)


class TestScanForEvidence:
    """Tests for evidence scanning."""
    
    def test_temporal_before(self):
        """Should detect 'before' as temporal evidence."""
        text = "Before Harry could leave, Hagrid arrived."
        matches = scan_for_evidence(text, EvidenceType.TEMPORAL)
        assert len(matches) > 0
        assert any("before" in m.quote.lower() for m in matches)
    
    def test_temporal_after(self):
        """Should detect 'after' as temporal evidence."""
        text = "After the feast ended, they went to bed."
        matches = scan_for_evidence(text, EvidenceType.TEMPORAL)
        assert len(matches) > 0
    
    def test_emotional_warmth(self):
        """Should detect warmth/affection language."""
        text = "She smiled warmly and hugged him goodbye."
        matches = scan_for_evidence(text, EvidenceType.EMOTIONAL)
        assert len(matches) > 0
    
    def test_emotional_hostility(self):
        """Should detect hostility language."""
        text = "He glared at her and snapped at the child."
        matches = scan_for_evidence(text, EvidenceType.EMOTIONAL)
        assert len(matches) > 0
    
    def test_emotional_farewell(self):
        """Should detect farewell language."""
        text = "She waved goodbye and said farewell to her friends."
        matches = scan_for_evidence(text, EvidenceType.EMOTIONAL)
        assert len(matches) > 0
    
    def test_appearance_color_change(self):
        """Should detect color change language."""
        text = "His face turned pale green and he looked sick."
        matches = scan_for_evidence(text, EvidenceType.APPEARANCE)
        assert len(matches) > 0
    
    def test_appearance_physical_state(self):
        """Should detect physical state language."""
        text = "She was covered in mud and blood was dripping from her forehead."
        matches = scan_for_evidence(text, EvidenceType.APPEARANCE)
        assert len(matches) > 0
    
    def test_appearance_injury(self):
        """Should detect injury indicators."""
        text = "He was limping badly, his face bruised and swollen."
        matches = scan_for_evidence(text, EvidenceType.APPEARANCE)
        assert len(matches) > 0
    
    def test_location_spatial(self):
        """Should detect location references."""
        text = "In the kitchen, Harry found the letter on the table."
        matches = scan_for_evidence(text, EvidenceType.LOCATION)
        assert len(matches) > 0
    
    def test_location_movement(self):
        """Should detect movement to locations."""
        text = "He walked into the library and entered the vault."
        matches = scan_for_evidence(text, EvidenceType.LOCATION)
        assert len(matches) > 0
    
    def test_no_evidence_neutral_text(self):
        """Should return empty for neutral text."""
        text = "The cat sat on the mat."
        matches = scan_for_evidence(text, EvidenceType.EMOTIONAL)
        assert len(matches) == 0


class TestScanAllEvidence:
    """Tests for scanning all evidence types."""
    
    def test_scans_all_types(self):
        """Should scan for all evidence types."""
        text = "Before leaving, she smiled warmly. Her face was pale. In the kitchen, she waved goodbye."
        all_evidence = scan_all_evidence(text)
        
        assert EvidenceType.TEMPORAL in all_evidence
        assert EvidenceType.EMOTIONAL in all_evidence
        assert EvidenceType.APPEARANCE in all_evidence
        assert EvidenceType.LOCATION in all_evidence
    
    def test_finds_multiple_types(self):
        """Should find evidence of multiple types."""
        text = "Before leaving, she smiled warmly. Her face was pale. In the kitchen, she waved goodbye."
        all_evidence = scan_all_evidence(text)
        
        # Should find at least one of each
        assert len(all_evidence[EvidenceType.TEMPORAL]) > 0
        assert len(all_evidence[EvidenceType.EMOTIONAL]) > 0
        assert len(all_evidence[EvidenceType.APPEARANCE]) > 0
        assert len(all_evidence[EvidenceType.LOCATION]) > 0


class TestPredicateCheckers:
    """Tests for predicate emission checking."""
    
    def test_temporal_after_links(self):
        """Should detect temporal predicates via after links."""
        result = {
            "events": [
                {"id": "e1", "type": "arrive", "after": None},
                {"id": "e2", "type": "talk", "after": "e1"},
            ],
            "temporal_constraints": [],
        }
        assert check_temporal_predicates(result) is True
    
    def test_temporal_constraints(self):
        """Should detect temporal predicates via constraints."""
        result = {
            "events": [],
            "temporal_constraints": [
                {"type": "previous", "event": "leave"}
            ],
        }
        assert check_temporal_predicates(result) is True
    
    def test_temporal_none(self):
        """Should return False when no temporal predicates."""
        result = {
            "events": [{"id": "e1", "type": "arrive", "after": None}],
            "temporal_constraints": [],
        }
        assert check_temporal_predicates(result) is False
    
    def test_emotional_relationships(self):
        """Should detect emotional predicates via relationships."""
        result = {
            "entities": {
                "relationships": [
                    {"type": "hostile_to", "char1": "a", "char2": "b"}
                ],
                "characters": [],
            },
            "events": [],
        }
        assert check_emotional_predicates(result) is True
    
    def test_emotional_events(self):
        """Should detect emotional predicates via event types."""
        result = {
            "entities": {"relationships": [], "characters": []},
            "events": [{"id": "e1", "type": "hug", "agent": "a", "patient": "b"}],
        }
        assert check_emotional_predicates(result) is True
    
    def test_emotional_character_emotion(self):
        """Should detect emotional predicates via character emotions."""
        result = {
            "entities": {
                "relationships": [],
                "characters": [{"id": "harry", "emotion": "angry"}],
            },
            "events": [],
        }
        assert check_emotional_predicates(result) is True
    
    def test_emotional_none(self):
        """Should return False when no emotional predicates."""
        result = {
            "entities": {
                "relationships": [{"type": "parent_of", "char1": "a", "char2": "b"}],
                "characters": [{"id": "harry", "emotion": "neutral"}],
            },
            "events": [{"id": "e1", "type": "arrive", "agent": "a"}],
        }
        assert check_emotional_predicates(result) is False
    
    def test_appearance_unusual(self):
        """Should detect appearance predicates via unusual appearances."""
        result = {
            "entities": {
                "characters": [{"id": "harry", "appearance": "pale green"}],
            },
        }
        assert check_appearance_predicates(result) is True
    
    def test_appearance_normal(self):
        """Should return False when appearances are normal."""
        result = {
            "entities": {
                "characters": [{"id": "harry", "appearance": "normal"}],
            },
        }
        assert check_appearance_predicates(result) is False
    
    def test_location_extracted(self):
        """Should detect location predicates via locations."""
        result = {
            "entities": {
                "locations": [{"id": "kitchen", "name": "Kitchen"}],
            },
            "events": [],
        }
        assert check_location_predicates(result) is True
    
    def test_location_in_events(self):
        """Should detect location predicates via event locations."""
        result = {
            "entities": {"locations": []},
            "events": [{"id": "e1", "type": "arrive", "location": "kitchen"}],
        }
        assert check_location_predicates(result) is True
    
    def test_location_none(self):
        """Should return False when no location predicates."""
        result = {
            "entities": {"locations": []},
            "events": [{"id": "e1", "type": "arrive", "location": None}],
        }
        assert check_location_predicates(result) is False


class TestEvidenceRecord:
    """Tests for EvidenceRecord dataclass."""
    
    def test_under_extracted_true(self):
        """Should flag under-extraction when detected but not emitted."""
        record = EvidenceRecord(
            evidence_type=EvidenceType.TEMPORAL,
            detected=True,
            matches=[EvidenceMatch(
                evidence_type=EvidenceType.TEMPORAL,
                pattern_matched="before",
                quote="Before leaving...",
                position=0,
            )],
            predicate_emitted=False,
        )
        assert record.under_extracted is True
    
    def test_under_extracted_false_not_detected(self):
        """Should NOT flag under-extraction when not detected."""
        record = EvidenceRecord(
            evidence_type=EvidenceType.TEMPORAL,
            detected=False,
            matches=[],
            predicate_emitted=False,
        )
        assert record.under_extracted is False
    
    def test_under_extracted_false_emitted(self):
        """Should NOT flag under-extraction when predicate emitted."""
        record = EvidenceRecord(
            evidence_type=EvidenceType.TEMPORAL,
            detected=True,
            matches=[],
            predicate_emitted=True,
        )
        assert record.under_extracted is False


class TestChapterDiagnostic:
    """Tests for ChapterDiagnostic dataclass."""
    
    def test_initializes_all_types(self):
        """Should initialize all evidence types."""
        diag = ChapterDiagnostic(chapter_id="ch1")
        for etype in EvidenceType:
            assert etype in diag.evidence_records
    
    def test_get_under_extractions(self):
        """Should return only under-extracted records."""
        diag = ChapterDiagnostic(chapter_id="ch1")
        diag.evidence_records[EvidenceType.TEMPORAL].detected = True
        diag.evidence_records[EvidenceType.TEMPORAL].predicate_emitted = False
        diag.evidence_records[EvidenceType.EMOTIONAL].detected = True
        diag.evidence_records[EvidenceType.EMOTIONAL].predicate_emitted = True
        
        under = diag.get_under_extractions()
        assert len(under) == 1
        assert under[0].evidence_type == EvidenceType.TEMPORAL
    
    def test_has_under_extraction(self):
        """Should return True if any under-extraction exists."""
        diag = ChapterDiagnostic(chapter_id="ch1")
        assert diag.has_under_extraction is False
        
        diag.evidence_records[EvidenceType.APPEARANCE].detected = True
        diag.evidence_records[EvidenceType.APPEARANCE].predicate_emitted = False
        assert diag.has_under_extraction is True


class TestAnalyzeChapterExtraction:
    """Tests for full chapter analysis."""
    
    def test_detects_temporal_under_extraction(self):
        """Should detect temporal under-extraction."""
        chapter_text = "Before Harry could leave, Hagrid arrived."
        extraction_result = {
            "events": [{"id": "e1", "type": "arrive", "after": None}],
            "temporal_constraints": [],
            "entities": {"characters": [], "locations": [], "relationships": []},
        }
        
        diag = analyze_chapter_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warnings=False,
        )
        
        assert diag.evidence_records[EvidenceType.TEMPORAL].detected is True
        assert diag.evidence_records[EvidenceType.TEMPORAL].predicate_emitted is False
        assert diag.evidence_records[EvidenceType.TEMPORAL].under_extracted is True
    
    def test_no_under_extraction_when_emitted(self):
        """Should NOT flag when predicates are properly emitted."""
        chapter_text = "Before Harry could leave, Hagrid arrived."
        extraction_result = {
            "events": [
                {"id": "e1", "type": "leave", "after": None},
                {"id": "e2", "type": "arrive", "after": "e1"},
            ],
            "temporal_constraints": [],
            "entities": {"characters": [], "locations": [], "relationships": []},
        }
        
        diag = analyze_chapter_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warnings=False,
        )
        
        assert diag.evidence_records[EvidenceType.TEMPORAL].detected is True
        assert diag.evidence_records[EvidenceType.TEMPORAL].predicate_emitted is True
        assert diag.evidence_records[EvidenceType.TEMPORAL].under_extracted is False
    
    def test_multiple_evidence_types(self):
        """Should analyze multiple evidence types."""
        chapter_text = "Before leaving, she smiled warmly. Her face was pale. In the kitchen, she waved goodbye."
        extraction_result = {
            "events": [],
            "temporal_constraints": [],
            "entities": {
                "characters": [{"id": "she", "appearance": "normal", "emotion": "neutral"}],
                "locations": [],
                "relationships": [],
            },
        }
        
        diag = analyze_chapter_extraction(
            chapter_id="ch1",
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warnings=False,
        )
        
        # All should be detected but not emitted
        assert diag.evidence_records[EvidenceType.TEMPORAL].under_extracted is True
        assert diag.evidence_records[EvidenceType.EMOTIONAL].under_extracted is True
        assert diag.evidence_records[EvidenceType.APPEARANCE].under_extracted is True
        assert diag.evidence_records[EvidenceType.LOCATION].under_extracted is True


class TestGetExtractionDiagnosticSummary:
    """Tests for summary generation."""
    
    def test_summary_with_under_extractions(self):
        """Should correctly summarize diagnostics."""
        diagnostics = []
        
        # Chapter 1: temporal under-extraction
        diag1 = ChapterDiagnostic(chapter_id="ch1")
        diag1.evidence_records[EvidenceType.TEMPORAL].detected = True
        diag1.evidence_records[EvidenceType.TEMPORAL].predicate_emitted = False
        diagnostics.append(diag1)
        
        # Chapter 2: properly extracted
        diag2 = ChapterDiagnostic(chapter_id="ch2")
        diag2.evidence_records[EvidenceType.TEMPORAL].detected = True
        diag2.evidence_records[EvidenceType.TEMPORAL].predicate_emitted = True
        diagnostics.append(diag2)
        
        # Chapter 3: no temporal evidence
        diag3 = ChapterDiagnostic(chapter_id="ch3")
        diagnostics.append(diag3)
        
        summary = get_extraction_diagnostic_summary(diagnostics)
        
        assert summary["total_chapters"] == 3
        assert summary["by_evidence_type"]["temporal"]["detected"] == 2
        assert summary["by_evidence_type"]["temporal"]["emitted"] == 1
        assert summary["by_evidence_type"]["temporal"]["under_extracted"] == 1
        assert "ch1" in summary["chapters_with_under_extraction"]
    
    def test_empty_diagnostics(self):
        """Should handle empty diagnostics list."""
        summary = get_extraction_diagnostic_summary([])
        
        assert summary["total_chapters"] == 0
        assert summary["chapters_with_under_extraction"] == []


class TestFormatDiagnosticReport:
    """Tests for report formatting."""
    
    def test_formats_report(self):
        """Should format a readable report."""
        summary = {
            "total_chapters": 10,
            "chapters_with_under_extraction": ["ch1", "ch2"],
            "under_extraction_rate": 0.2,
            "by_evidence_type": {
                "temporal": {"detected": 5, "emitted": 3, "under_extracted": 2, "recall_rate": 0.6},
                "emotional": {"detected": 3, "emitted": 3, "under_extracted": 0, "recall_rate": 1.0},
            },
        }
        
        report = format_diagnostic_report(summary)
        
        assert "EXTRACTION DIAGNOSTIC REPORT" in report
        assert "Total chapters analyzed: 10" in report
        assert "TEMPORAL" in report
        assert "60.0%" in report
