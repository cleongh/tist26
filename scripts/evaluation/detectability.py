"""
Detectability Classification for Implanted Errors.

Classifies each implanted or expected error based on whether the logic engine
could detect it, providing clear separation between engine failures and
design limitations.

Classifications:
- detected: ASP violation corresponds to the implanted inconsistency
- detectable_but_missed: Required predicates exist but no ASP rule fired
- undetectable_by_design: Required predicates do NOT exist (extraction gap)

Per LOGIC_DESIGN.md:
- Deterministic behavior
- Does NOT affect runtime logic
- Lives in evaluation/reporting code only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..extraction.extraction_diagnostics import (
    ChapterDiagnostic,
    EvidenceType,
)
from .evidence_checklist import (
    ChecklistEvaluation,
    evaluate_checklist,
    get_checklist_for_category,
    ERROR_CATEGORY_CHECKLISTS,
)


class DetectabilityStatus(Enum):
    """Classification of error detectability."""
    
    DETECTED = "detected"
    # At least one ASP violation corresponds to the implanted inconsistency
    
    DETECTABLE_BUT_MISSED = "detectable_but_missed"
    # Required structured predicates exist BUT no ASP rule fired
    # Indicates a logic, normalization, or integration bug
    
    UNDETECTABLE_BY_DESIGN = "undetectable_by_design"
    # Required predicates do NOT exist (extraction did not encode the inconsistency)


@dataclass
class ImplantedError:
    """Description of an implanted error for evaluation."""
    
    chapter_id: str
    error_type: str  # e.g., "emotional_inconsistency", "location_violation", etc.
    description: str  # Human-readable description of what was implanted
    required_evidence_types: List[EvidenceType] = field(default_factory=list)
    # Which evidence types are needed to detect this error
    
    expected_violation_rule: Optional[str] = None
    # The ASP rule that should fire if detected (e.g., "emotional_mismatch")


@dataclass
class DetectabilityResult:
    """Result of detectability classification for a single chapter."""
    
    chapter_id: str
    implanted_error: Optional[ImplantedError]
    
    # Classification
    status: DetectabilityStatus = DetectabilityStatus.UNDETECTABLE_BY_DESIGN
    
    # Evidence analysis
    missing_evidence_types: List[EvidenceType] = field(default_factory=list)
    present_evidence_types: List[EvidenceType] = field(default_factory=list)
    under_extracted_types: List[EvidenceType] = field(default_factory=list)
    
    # Evidence checklist evaluation (new)
    checklist_evaluation: Optional[ChecklistEvaluation] = None
    
    # ASP analysis
    asp_violations_found: List[str] = field(default_factory=list)
    expected_violation_matched: bool = False
    
    # Diagnostic notes
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chapter_id": self.chapter_id,
            "detectability_status": self.status.value,
            "implanted_error": {
                "type": self.implanted_error.error_type,
                "description": self.implanted_error.description,
            } if self.implanted_error else None,
            "missing_evidence_types": [e.value for e in self.missing_evidence_types],
            "present_evidence_types": [e.value for e in self.present_evidence_types],
            "under_extracted_types": [e.value for e in self.under_extracted_types],
            "checklist_evaluation": self.checklist_evaluation.to_dict() if self.checklist_evaluation else None,
            "asp_violations_found": self.asp_violations_found,
            "expected_violation_matched": self.expected_violation_matched,
            "notes": self.notes,
        }


def classify_detectability(
    chapter_id: str,
    implanted_error: Optional[ImplantedError],
    extraction_diagnostic: Optional[ChapterDiagnostic],
    asp_violations: List[Dict[str, Any]],
    extraction_result: Optional[Dict[str, Any]] = None,
) -> DetectabilityResult:
    """
    Classify the detectability of an implanted error.
    
    This function determines whether an error was:
    - Detected by the ASP engine
    - Detectable but missed (predicates exist, no rule fired)
    - Undetectable by design (predicates don't exist)
    
    Uses evidence checklist to provide transparent, auditable reasoning.
    
    Args:
        chapter_id: Chapter identifier
        implanted_error: Description of the implanted error (None if no error implanted)
        extraction_diagnostic: ChapterDiagnostic from extraction phase
        asp_violations: List of ASP violations found for this chapter
        extraction_result: Optional merged extraction result for checklist evaluation
        
    Returns:
        DetectabilityResult with classification, checklist evaluation, and analysis
    """
    result = DetectabilityResult(
        chapter_id=chapter_id,
        implanted_error=implanted_error,
    )
    
    # If no error was implanted, mark as N/A
    if implanted_error is None:
        result.status = DetectabilityStatus.DETECTED  # No error to detect = success
        result.notes.append("No implanted error in this chapter")
        return result
    
    # Evaluate evidence checklist if extraction result is available
    if extraction_result and implanted_error.error_type in ERROR_CATEGORY_CHECKLISTS:
        result.checklist_evaluation = evaluate_checklist(
            error_category=implanted_error.error_type,
            chapter_id=chapter_id,
            extraction_result=extraction_result,
        )
    
    # Extract ASP violation rule names
    violation_rules = set()
    for violation in asp_violations:
        rule = violation.get("rule", violation.get("type", "unknown"))
        violation_rules.add(rule)
        result.asp_violations_found.append(rule)
    
    # Check if expected violation was found
    if implanted_error.expected_violation_rule:
        if implanted_error.expected_violation_rule in violation_rules:
            result.expected_violation_matched = True
    
    # Check if ANY violation corresponds to the implanted error type
    error_related_violations = _find_related_violations(
        implanted_error.error_type,
        violation_rules,
    )
    
    if error_related_violations:
        result.status = DetectabilityStatus.DETECTED
        result.notes.append(
            f"Detected via violations: {', '.join(error_related_violations)}"
        )
        if result.checklist_evaluation:
            result.notes.append(f"Checklist: {result.checklist_evaluation.justification}")
        return result
    
    # No detection - use checklist evaluation if available
    if result.checklist_evaluation:
        if result.checklist_evaluation.overall_satisfied:
            # Evidence was sufficient but no ASP rule fired
            result.status = DetectabilityStatus.DETECTABLE_BUT_MISSED
            result.notes.append(
                f"Checklist satisfied: {result.checklist_evaluation.justification}"
            )
            result.notes.append(
                "No ASP violation fired - possible logic/normalization/integration bug"
            )
            return result
        else:
            # Evidence was insufficient
            result.status = DetectabilityStatus.UNDETECTABLE_BY_DESIGN
            result.notes.append(
                f"Checklist not satisfied: {result.checklist_evaluation.justification}"
            )
            return result
    
    # Fallback: Analyze extraction diagnostics (legacy path)
    if extraction_diagnostic:
        for etype in EvidenceType:
            record = extraction_diagnostic.evidence_records.get(etype)
            if record:
                if record.predicate_emitted:
                    result.present_evidence_types.append(etype)
                elif record.detected and not record.predicate_emitted:
                    result.under_extracted_types.append(etype)
                elif etype in implanted_error.required_evidence_types and not record.detected:
                    result.missing_evidence_types.append(etype)
    
    # Check required evidence types
    required = set(implanted_error.required_evidence_types)
    present = set(result.present_evidence_types)
    under_extracted = set(result.under_extracted_types)
    
    # If required evidence was present (extracted as predicates)
    # but no ASP rule fired → detectable but missed
    if required and required.issubset(present):
        result.status = DetectabilityStatus.DETECTABLE_BUT_MISSED
        result.notes.append(
            f"All required evidence types extracted: {[e.value for e in required]}"
        )
        result.notes.append(
            "No ASP violation fired - possible logic/normalization/integration bug"
        )
        return result
    
    # If some required evidence was detected but under-extracted
    if required & under_extracted:
        result.status = DetectabilityStatus.UNDETECTABLE_BY_DESIGN
        under_names = [e.value for e in required & under_extracted]
        result.notes.append(
            f"Evidence detected but not extracted: {under_names}"
        )
        result.notes.append("Under-extraction prevented detection")
        return result
    
    # If required evidence not even detected in text
    if required - present - under_extracted:
        result.status = DetectabilityStatus.UNDETECTABLE_BY_DESIGN
        missing_names = [e.value for e in required - present - under_extracted]
        result.notes.append(
            f"Required evidence types not found in text: {missing_names}"
        )
        return result
    
    # Default: undetectable by design
    result.status = DetectabilityStatus.UNDETECTABLE_BY_DESIGN
    result.notes.append("Insufficient evidence for detection")
    
    return result


def _find_related_violations(
    error_type: str,
    violation_rules: Set[str],
) -> Set[str]:
    """
    Find violations that correspond to the implanted error type.
    
    Maps error types to potential ASP rule names.
    """
    # Mapping of error types to related ASP rules
    ERROR_TYPE_TO_RULES = {
        "emotional_inconsistency": {
            "emotional_mismatch",
            "relationship_behavior_conflict",
            "hostile_kindness_violation",
            "emotional_contradiction",
        },
        "location_violation": {
            "non_ubiquity",
            "ubiquity_violation",
            "location_conflict",
            "presence_contradiction",
        },
        "temporal_violation": {
            "temporal_conflict",
            "timeline_violation",
            "causality_error",
            "temporal_ordering_error",
        },
        "appearance_inconsistency": {
            "appearance_mismatch",
            "appearance_contradiction",
            "physical_state_conflict",
        },
        "relationship_violation": {
            "relationship_contradiction",
            "relationship_mismatch",
            "social_conflict",
        },
        "item_violation": {
            "item_presence_error",
            "item_state_conflict",
            "carrying_contradiction",
        },
        "state_violation": {
            "character_state_conflict",
            "state_contradiction",
            "dead_character_acting",
        },
    }
    
    related_rules = ERROR_TYPE_TO_RULES.get(error_type, set())
    return violation_rules & related_rules


def classify_all_chapters(
    implanted_errors: Dict[str, ImplantedError],
    extraction_diagnostics: Dict[str, ChapterDiagnostic],
    asp_results: Dict[str, List[Dict[str, Any]]],
) -> List[DetectabilityResult]:
    """
    Classify detectability for all chapters.
    
    Args:
        implanted_errors: Map of chapter_id → ImplantedError
        extraction_diagnostics: Map of chapter_id → ChapterDiagnostic
        asp_results: Map of chapter_id → list of ASP violations
        
    Returns:
        List of DetectabilityResult for all chapters
    """
    results = []
    
    # Get all chapter IDs
    all_chapters = set(implanted_errors.keys()) | set(extraction_diagnostics.keys())
    
    for chapter_id in sorted(all_chapters):
        result = classify_detectability(
            chapter_id=chapter_id,
            implanted_error=implanted_errors.get(chapter_id),
            extraction_diagnostic=extraction_diagnostics.get(chapter_id),
            asp_violations=asp_results.get(chapter_id, []),
        )
        results.append(result)
    
    return results


def get_detectability_summary(results: List[DetectabilityResult]) -> Dict[str, Any]:
    """
    Generate a summary of detectability classifications.
    
    Args:
        results: List of DetectabilityResult objects
        
    Returns:
        Summary dict with statistics
    """
    total = len(results)
    if total == 0:
        return {
            "total_chapters": 0,
            "with_implanted_errors": 0,
            "detected": 0,
            "detectable_but_missed": 0,
            "undetectable_by_design": 0,
            "detection_rate": 0.0,
            "potential_detection_rate": 0.0,
        }
    
    with_errors = [r for r in results if r.implanted_error is not None]
    detected = [r for r in with_errors if r.status == DetectabilityStatus.DETECTED]
    missed = [r for r in with_errors if r.status == DetectabilityStatus.DETECTABLE_BUT_MISSED]
    undetectable = [r for r in with_errors if r.status == DetectabilityStatus.UNDETECTABLE_BY_DESIGN]
    
    error_count = len(with_errors)
    
    return {
        "total_chapters": total,
        "with_implanted_errors": error_count,
        "detected": len(detected),
        "detectable_but_missed": len(missed),
        "undetectable_by_design": len(undetectable),
        # Actual detection rate
        "detection_rate": len(detected) / error_count if error_count > 0 else 0.0,
        # Potential detection rate (if all bugs were fixed)
        "potential_detection_rate": (len(detected) + len(missed)) / error_count if error_count > 0 else 0.0,
        # Chapters by status
        "detected_chapters": [r.chapter_id for r in detected],
        "missed_chapters": [r.chapter_id for r in missed],
        "undetectable_chapters": [r.chapter_id for r in undetectable],
    }


def format_detectability_report(summary: Dict[str, Any]) -> str:
    """
    Format a detectability summary as a human-readable report.
    
    Args:
        summary: Output from get_detectability_summary()
        
    Returns:
        Formatted string report
    """
    lines = [
        "=" * 60,
        "DETECTABILITY CLASSIFICATION REPORT",
        "=" * 60,
        f"Total chapters analyzed: {summary['total_chapters']}",
        f"Chapters with implanted errors: {summary['with_implanted_errors']}",
        "",
        "CLASSIFICATION BREAKDOWN:",
        "-" * 40,
        f"  ✓ DETECTED:                 {summary['detected']}",
        f"  ⚠ DETECTABLE_BUT_MISSED:   {summary['detectable_but_missed']}",
        f"  ✗ UNDETECTABLE_BY_DESIGN:  {summary['undetectable_by_design']}",
        "",
        "RATES:",
        "-" * 40,
        f"  Current detection rate:   {summary['detection_rate']:.1%}",
        f"  Potential detection rate: {summary['potential_detection_rate']:.1%}",
        f"  (if logic bugs were fixed)",
        "",
    ]
    
    if summary.get("detected_chapters"):
        lines.append("DETECTED CHAPTERS:")
        for ch in summary["detected_chapters"][:5]:
            lines.append(f"  ✓ {ch}")
        if len(summary["detected_chapters"]) > 5:
            lines.append(f"  ... and {len(summary['detected_chapters']) - 5} more")
        lines.append("")
    
    if summary.get("missed_chapters"):
        lines.append("DETECTABLE BUT MISSED (engine bugs):")
        for ch in summary["missed_chapters"]:
            lines.append(f"  ⚠ {ch}")
        lines.append("")
    
    if summary.get("undetectable_chapters"):
        lines.append("UNDETECTABLE BY DESIGN (extraction gaps):")
        for ch in summary["undetectable_chapters"][:10]:
            lines.append(f"  ✗ {ch}")
        if len(summary["undetectable_chapters"]) > 10:
            lines.append(f"  ... and {len(summary['undetectable_chapters']) - 10} more")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)
