"""
Temporal Extraction Diagnostics.

Detects when temporal language exists in chapter text but no temporal
predicates are produced. This helps identify recall failures in temporal
extraction without affecting logic or blocking execution.

Per LOGIC_DESIGN.md:
- Diagnostics are logged for evaluation
- Do NOT affect logic
- Do NOT block execution
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..state.logging import log


# Temporal marker patterns - phrases that indicate temporal relationships
TEMPORAL_MARKERS = [
    # Explicit ordering
    r"\bbefore\b",
    r"\bafter\b",
    r"\bearlier\b",
    r"\blater\b",
    r"\bfirst\b.*\bthen\b",
    r"\bonce\b.*\bthen\b",
    
    # Past references
    r"\bthe day before\b",
    r"\bthe night before\b",
    r"\bthe morning before\b",
    r"\bpreviously\b",
    r"\bprior to\b",
    r"\bfollowing\b",
    r"\bsubsequently\b",
    
    # Past perfect indicators
    r"\bhad already\b",
    r"\bhad just\b",
    r"\bhad been\b",
    r"\bhad\s+\w+ed\b",  # Generic past perfect pattern
    
    # Temporal adverbs
    r"\bmeanwhile\b",
    r"\bafterward[s]?\b",
    r"\bbeforehand\b",
]

# Compile patterns for efficiency
TEMPORAL_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in TEMPORAL_MARKERS]


@dataclass
class TemporalDiagnostic:
    """Diagnostic result for temporal extraction analysis."""
    
    chapter_id: str
    temporal_markers_found: List[str] = field(default_factory=list)
    has_after_links: bool = False
    has_temporal_constraints: bool = False
    warning_emitted: bool = False
    
    @property
    def temporal_language_detected(self) -> bool:
        """True if any temporal markers were found in the text."""
        return len(self.temporal_markers_found) > 0
    
    @property
    def temporal_predicates_extracted(self) -> bool:
        """True if any temporal predicates exist in extraction."""
        return self.has_after_links or self.has_temporal_constraints
    
    @property
    def recall_failure(self) -> bool:
        """True if temporal language exists but no predicates extracted."""
        return self.temporal_language_detected and not self.temporal_predicates_extracted


def scan_for_temporal_markers(text: str) -> List[str]:
    """
    Scan chapter text for temporal marker phrases.
    
    Args:
        text: Chapter text to scan
        
    Returns:
        List of unique temporal markers found (lowercased)
    """
    markers_found = set()
    
    for pattern in TEMPORAL_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            # Normalize and add to set
            marker = match.lower().strip()
            if marker:
                markers_found.add(marker)
    
    return sorted(markers_found)


def check_after_links(events: List[Dict[str, Any]]) -> bool:
    """
    Check if any events have non-null after links.
    
    Args:
        events: List of extracted events
        
    Returns:
        True if any event has a non-null 'after' field
    """
    for event in events:
        after = event.get("after")
        if after is not None and after != "null" and after != "":
            return True
    return False


def check_temporal_constraints(extraction_result: Dict[str, Any]) -> bool:
    """
    Check if temporal_constraints array has entries.
    
    Args:
        extraction_result: Full extraction result dict
        
    Returns:
        True if temporal_constraints exists and is non-empty
    """
    constraints = extraction_result.get("temporal_constraints", [])
    return len(constraints) > 0


def analyze_temporal_extraction(
    chapter_id: str,
    chapter_text: str,
    extraction_result: Dict[str, Any],
    emit_warning: bool = True,
) -> TemporalDiagnostic:
    """
    Analyze temporal extraction and emit diagnostic if needed.
    
    This function:
    1. Scans chapter text for temporal markers
    2. Checks if temporal_constraints or after-links exist
    3. Emits a diagnostic warning if temporal language found but not extracted
    
    Per LOGIC_DESIGN.md requirements:
    - Does NOT affect logic
    - Does NOT block execution
    - Logs for evaluation
    
    Args:
        chapter_id: Chapter identifier for logging
        chapter_text: Full chapter text
        extraction_result: Result from extract_events()
        emit_warning: If True, log warning when recall failure detected
        
    Returns:
        TemporalDiagnostic with analysis results
    """
    diagnostic = TemporalDiagnostic(chapter_id=chapter_id)
    
    # Step 1: Scan for temporal markers
    diagnostic.temporal_markers_found = scan_for_temporal_markers(chapter_text)
    
    # Step 2: Check for after links in events
    events = extraction_result.get("events", [])
    diagnostic.has_after_links = check_after_links(events)
    
    # Step 3: Check for temporal constraints
    diagnostic.has_temporal_constraints = check_temporal_constraints(extraction_result)
    
    # Step 4: Emit warning if recall failure detected
    if diagnostic.recall_failure and emit_warning:
        markers_sample = diagnostic.temporal_markers_found[:5]  # Limit to 5 examples
        markers_str = ", ".join(f"'{m}'" for m in markers_sample)
        if len(diagnostic.temporal_markers_found) > 5:
            markers_str += f", ... (+{len(diagnostic.temporal_markers_found) - 5} more)"
        
        log(
            f"[{chapter_id}] Temporal language detected but not extracted. "
            f"Markers found: {markers_str}",
            "WARN"
        )
        diagnostic.warning_emitted = True
    
    return diagnostic


def get_temporal_diagnostic_summary(diagnostics: List[TemporalDiagnostic]) -> Dict[str, Any]:
    """
    Generate a summary of temporal diagnostics across multiple chapters.
    
    Args:
        diagnostics: List of TemporalDiagnostic objects
        
    Returns:
        Summary dict with statistics
    """
    total = len(diagnostics)
    if total == 0:
        return {
            "total_chapters": 0,
            "chapters_with_temporal_language": 0,
            "chapters_with_temporal_predicates": 0,
            "recall_failures": 0,
            "recall_failure_rate": 0.0,
            "failed_chapters": [],
        }
    
    with_language = sum(1 for d in diagnostics if d.temporal_language_detected)
    with_predicates = sum(1 for d in diagnostics if d.temporal_predicates_extracted)
    failures = sum(1 for d in diagnostics if d.recall_failure)
    failed_chapters = [d.chapter_id for d in diagnostics if d.recall_failure]
    
    return {
        "total_chapters": total,
        "chapters_with_temporal_language": with_language,
        "chapters_with_temporal_predicates": with_predicates,
        "recall_failures": failures,
        "recall_failure_rate": failures / with_language if with_language > 0 else 0.0,
        "failed_chapters": failed_chapters,
    }
