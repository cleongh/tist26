"""
Extraction Diagnostics Layer.

Detects when narrative evidence exists in chapter text but is not promoted
to structured predicates required by logic rules. This helps identify
under-extraction that prevents error detection.

Evidence types checked:
- Emotional language (warmth, hostility, kindness)
- Appearance changes
- Explicit locations
- Temporal markers

Per LOGIC_DESIGN.md:
- Diagnostics are logged for evaluation
- Do NOT affect logic
- Do NOT block execution
- Deterministic behavior
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ..state.logging import log


class EvidenceType(Enum):
    """Types of narrative evidence to detect."""
    TEMPORAL = "temporal"
    EMOTIONAL = "emotional"
    APPEARANCE = "appearance"
    LOCATION = "location"


# =============================================================================
# EVIDENCE PATTERNS
# =============================================================================

# Temporal markers (from temporal_diagnostics.py)
TEMPORAL_PATTERNS = [
    r"\bbefore\b",
    r"\bafter\b",
    r"\bearlier\b",
    r"\blater\b",
    r"\bpreviously\b",
    r"\bprior to\b",
    r"\bhad already\b",
    r"\bhad just\b",
    r"\bmeanwhile\b",
    r"\bafterward[s]?\b",
]

# Emotional language markers - warmth, hostility, kindness
EMOTIONAL_PATTERNS = [
    # Warmth / affection
    r"\bsmiled\s+(warmly|kindly|gently)\b",
    r"\b(hugged|embraced)\b",
    r"\bwaved\s+(goodbye|farewell)\b",
    r"\b(fond|loving|affectionate)\s+(look|glance|smile)\b",
    r"\b(praised|encouraged|comforted)\b",
    r"\bsaid\s+(kindly|warmly|gently|softly)\b",
    r"\b(patted|squeezed)\s+(hand|shoulder|arm)\b",
    
    # Hostility / anger
    r"\b(glared|scowled|snarled)\b",
    r"\b(snapped|shouted|yelled)\s+at\b",
    r"\b(hostile|aggressive|threatening)\s+(tone|voice|manner)\b",
    r"\b(slammed|threw|punched|kicked)\b",
    r"\bspat\s+(out|at)\b",
    r"\bwith\s+(hatred|contempt|disgust)\b",
    
    # Kindness / help
    r"\b(helped|assisted|aided)\b",
    r"\b(offered|gave)\s+(help|assistance|support)\b",
    r"\b(comforting|reassuring|soothing)\b",
    r"\b(gentle|tender|caring)\s+(voice|touch|manner)\b",
    
    # Farewell / departure emotions
    r"\bsaid\s+(goodbye|farewell)\b",
    r"\b(waved|nodded)\s+(goodbye|farewell)\b",
    r"\b(parting|final)\s+(words|gesture|look)\b",
    r"\btears\s+(welled|streamed|fell)\b",
]

# Appearance change markers
APPEARANCE_PATTERNS = [
    # Color changes
    r"\bface\s+(turned|went|became|was|looked)\s+(pale|red|white|green|flushed)\b",
    r"\b(turned|went|became)\s+(pale|red|white|green|flushed)\b",
    r"\b(pale|pallid|ashen|flushed|crimson)\s+(face|cheeks|complexion)\b",
    r"\bface\s+was\s+(pale|red|white|green|flushed)\b",
    r"\bwas\s+(pale|pallid|ashen|flushed)\b",
    r"\blooked\s+(pale|sick|ill|unwell)\b",
    r"\bgreenish\s+(tinge|hue|pallor)\b",
    
    # Physical state
    r"\bcovered\s+(in|with)\s+(mud|blood|dirt|dust|sweat)\b",
    r"\b(muddy|bloody|dirty|dusty|sweaty|disheveled)\b",
    r"\b(dripping|soaked|drenched)\s+(with|in)\b",
    r"\b(bruised|cut|scratched|scarred|wounded)\b",
    
    # Injury indicators
    r"\bblood\s+(dripping|running|streaming|oozing)\b",
    r"\b(limping|hobbling|staggering)\b",
    r"\b(swollen|black)\s+eye\b",
    r"\b(bandaged|wrapped|bleeding)\b",
    
    # Emotional manifestation
    r"\b(trembling|shaking|quivering)\b",
    r"\btears\s+(in|streaming|falling)\b",
    r"\b(tear-stained|tearful)\b",
    r"\b(sweating|perspiring)\s+(heavily|profusely)\b",
]

# Location markers - explicit place references
LOCATION_PATTERNS = [
    # Spatial prepositions with named places
    r"\bin\s+the\s+(\w+)\b",
    r"\bat\s+the\s+(\w+)\b",
    r"\binto\s+the\s+(\w+)\b",
    r"\binside\s+the\s+(\w+)\b",
    r"\bthrough\s+the\s+(\w+)\b",
    
    # Movement to locations
    r"\bwalked\s+into\s+the\s+(\w+)\b",
    r"\bentered\s+the\s+(\w+)\b",
    r"\bleft\s+the\s+(\w+)\b",
    r"\barrived\s+at\s+the\s+(\w+)\b",
    
    # Scene-setting phrases
    r"\bthe\s+(\w+)\s+was\s+(empty|crowded|dark|bright)\b",
    r"\bin\s+(\w+)'s\s+(room|office|house|home)\b",
]

# Compile all patterns
COMPILED_PATTERNS = {
    EvidenceType.TEMPORAL: [re.compile(p, re.IGNORECASE) for p in TEMPORAL_PATTERNS],
    EvidenceType.EMOTIONAL: [re.compile(p, re.IGNORECASE) for p in EMOTIONAL_PATTERNS],
    EvidenceType.APPEARANCE: [re.compile(p, re.IGNORECASE) for p in APPEARANCE_PATTERNS],
    EvidenceType.LOCATION: [re.compile(p, re.IGNORECASE) for p in LOCATION_PATTERNS],
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class EvidenceMatch:
    """A single evidence match from the text."""
    evidence_type: EvidenceType
    pattern_matched: str
    quote: str  # Snippet from text (≤80 chars)
    position: int  # Character position in text


@dataclass
class EvidenceRecord:
    """Evidence detection and predicate emission record for a single type."""
    evidence_type: EvidenceType
    detected: bool = False
    matches: List[EvidenceMatch] = field(default_factory=list)
    predicate_emitted: bool = False
    
    @property
    def under_extracted(self) -> bool:
        """True if evidence detected but no predicate emitted."""
        return self.detected and not self.predicate_emitted
    
    @property
    def example_quote(self) -> Optional[str]:
        """Get first match quote as example."""
        if self.matches:
            return self.matches[0].quote
        return None


@dataclass
class ChapterDiagnostic:
    """Complete diagnostic record for a chapter."""
    chapter_id: str
    evidence_records: Dict[EvidenceType, EvidenceRecord] = field(default_factory=dict)
    warnings_emitted: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Initialize all evidence types
        for etype in EvidenceType:
            if etype not in self.evidence_records:
                self.evidence_records[etype] = EvidenceRecord(evidence_type=etype)
    
    def get_under_extractions(self) -> List[EvidenceRecord]:
        """Get all evidence records where under-extraction occurred."""
        return [r for r in self.evidence_records.values() if r.under_extracted]
    
    @property
    def has_under_extraction(self) -> bool:
        """True if any evidence type was under-extracted."""
        return len(self.get_under_extractions()) > 0


# =============================================================================
# EVIDENCE SCANNING
# =============================================================================

def extract_quote_context(text: str, match_start: int, match_end: int, max_len: int = 80) -> str:
    """
    Extract a quote snippet around a match.
    
    Args:
        text: Full chapter text
        match_start: Start position of match
        match_end: End position of match
        max_len: Maximum length of quote
        
    Returns:
        Quote snippet with ellipsis if truncated
    """
    # Expand to include context
    context_chars = (max_len - (match_end - match_start)) // 2
    start = max(0, match_start - context_chars)
    end = min(len(text), match_end + context_chars)
    
    quote = text[start:end].strip()
    
    # Clean up whitespace
    quote = re.sub(r'\s+', ' ', quote)
    
    # Add ellipsis if truncated
    if start > 0:
        quote = "..." + quote
    if end < len(text):
        quote = quote + "..."
    
    # Final length check
    if len(quote) > max_len:
        quote = quote[:max_len-3] + "..."
    
    return quote


def scan_for_evidence(text: str, evidence_type: EvidenceType) -> List[EvidenceMatch]:
    """
    Scan chapter text for evidence of a specific type.
    
    Args:
        text: Chapter text to scan
        evidence_type: Type of evidence to look for
        
    Returns:
        List of EvidenceMatch objects found
    """
    matches = []
    patterns = COMPILED_PATTERNS.get(evidence_type, [])
    
    for pattern in patterns:
        for match in pattern.finditer(text):
            quote = extract_quote_context(text, match.start(), match.end())
            matches.append(EvidenceMatch(
                evidence_type=evidence_type,
                pattern_matched=pattern.pattern,
                quote=quote,
                position=match.start(),
            ))
    
    # Deduplicate by position (same text span matched by multiple patterns)
    seen_positions = set()
    unique_matches = []
    for m in sorted(matches, key=lambda x: x.position):
        # Group matches within 20 chars as same evidence
        pos_key = m.position // 20
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            unique_matches.append(m)
    
    return unique_matches


def scan_all_evidence(text: str) -> Dict[EvidenceType, List[EvidenceMatch]]:
    """
    Scan chapter text for all evidence types.
    
    Args:
        text: Chapter text to scan
        
    Returns:
        Dict mapping evidence types to their matches
    """
    return {
        etype: scan_for_evidence(text, etype)
        for etype in EvidenceType
    }


# =============================================================================
# PREDICATE EMISSION CHECKING
# =============================================================================

def check_temporal_predicates(extraction_result: Dict[str, Any]) -> bool:
    """Check if temporal predicates were emitted."""
    events = extraction_result.get("events", [])
    
    # Check for after links
    for event in events:
        after = event.get("after")
        if after is not None and after != "null" and after != "":
            return True
    
    # Check for temporal constraints
    constraints = extraction_result.get("temporal_constraints", [])
    if constraints:
        return True
    
    return False


def check_emotional_predicates(extraction_result: Dict[str, Any]) -> bool:
    """Check if emotional predicates were emitted."""
    # Check relationships for emotional types
    relationships = extraction_result.get("entities", {}).get("relationships", [])
    emotional_rel_types = {"loves", "hates", "fears", "trusts", "distrusts", "admires", "hostile_to", "friendly_to"}
    
    for rel in relationships:
        if rel.get("type", "").lower() in emotional_rel_types:
            return True
    
    # Check events for emotional event types
    events = extraction_result.get("events", [])
    emotional_event_types = {"hug", "praise", "farewell", "encourage", "smile", "wave", "attack", "help"}
    
    for event in events:
        if event.get("type", "").lower() in emotional_event_types:
            return True
    
    # Check character emotions
    characters = extraction_result.get("entities", {}).get("characters", [])
    for char in characters:
        emotion = char.get("emotion", "neutral").lower()
        if emotion not in ("neutral", "calm"):
            return True
    
    return False


def check_appearance_predicates(extraction_result: Dict[str, Any]) -> bool:
    """Check if appearance predicates were emitted."""
    characters = extraction_result.get("entities", {}).get("characters", [])
    
    for char in characters:
        appearance = char.get("appearance", "normal").lower()
        if appearance != "normal":
            return True
    
    return False


def check_location_predicates(extraction_result: Dict[str, Any]) -> bool:
    """Check if location predicates were emitted."""
    # Check if locations were extracted
    locations = extraction_result.get("entities", {}).get("locations", [])
    if locations:
        return True
    
    # Check if events have location bindings
    events = extraction_result.get("events", [])
    for event in events:
        loc = event.get("location")
        if loc is not None and loc != "null" and loc != "":
            return True
    
    return False


PREDICATE_CHECKERS = {
    EvidenceType.TEMPORAL: check_temporal_predicates,
    EvidenceType.EMOTIONAL: check_emotional_predicates,
    EvidenceType.APPEARANCE: check_appearance_predicates,
    EvidenceType.LOCATION: check_location_predicates,
}


# =============================================================================
# MAIN DIAGNOSTIC FUNCTIONS
# =============================================================================

def analyze_chapter_extraction(
    chapter_id: str,
    chapter_text: str,
    extraction_result: Dict[str, Any],
    emit_warnings: bool = True,
) -> ChapterDiagnostic:
    """
    Analyze a chapter's extraction for under-extraction.
    
    This function:
    1. Scans chapter text for all evidence types
    2. Checks if predicates were emitted for each type
    3. Logs warnings for under-extraction
    
    Per LOGIC_DESIGN.md:
    - Does NOT affect logic
    - Does NOT block execution
    - Deterministic behavior
    
    Args:
        chapter_id: Chapter identifier for logging
        chapter_text: Full chapter text
        extraction_result: Merged extraction result
        emit_warnings: If True, log warnings for under-extraction
        
    Returns:
        ChapterDiagnostic with complete analysis
    """
    diagnostic = ChapterDiagnostic(chapter_id=chapter_id)
    
    # Step 1: Scan for all evidence types
    all_evidence = scan_all_evidence(chapter_text)
    
    # Step 2: Build evidence records
    for etype, matches in all_evidence.items():
        record = diagnostic.evidence_records[etype]
        record.matches = matches
        record.detected = len(matches) > 0
        
        # Check if predicates were emitted
        checker = PREDICATE_CHECKERS.get(etype)
        if checker:
            record.predicate_emitted = checker(extraction_result)
    
    # Step 3: Emit warnings for under-extraction
    if emit_warnings:
        for record in diagnostic.get_under_extractions():
            warning_msg = (
                f"[{chapter_id}] Under-extraction: {record.evidence_type.value} "
                f"evidence detected but not extracted. "
                f"Example: \"{record.example_quote}\""
            )
            log(warning_msg, "WARN")
            diagnostic.warnings_emitted.append(warning_msg)
    
    return diagnostic


def get_extraction_diagnostic_summary(diagnostics: List[ChapterDiagnostic]) -> Dict[str, Any]:
    """
    Generate a summary of extraction diagnostics across multiple chapters.
    
    Args:
        diagnostics: List of ChapterDiagnostic objects
        
    Returns:
        Summary dict with statistics per evidence type
    """
    total = len(diagnostics)
    if total == 0:
        return {
            "total_chapters": 0,
            "by_evidence_type": {},
            "chapters_with_under_extraction": [],
        }
    
    # Aggregate by evidence type
    by_type = {}
    for etype in EvidenceType:
        detected_count = sum(
            1 for d in diagnostics 
            if d.evidence_records[etype].detected
        )
        emitted_count = sum(
            1 for d in diagnostics 
            if d.evidence_records[etype].predicate_emitted
        )
        under_extracted = sum(
            1 for d in diagnostics 
            if d.evidence_records[etype].under_extracted
        )
        
        by_type[etype.value] = {
            "detected": detected_count,
            "emitted": emitted_count,
            "under_extracted": under_extracted,
            "recall_rate": emitted_count / detected_count if detected_count > 0 else 1.0,
        }
    
    # Chapters with any under-extraction
    chapters_with_issues = [
        d.chapter_id for d in diagnostics if d.has_under_extraction
    ]
    
    return {
        "total_chapters": total,
        "by_evidence_type": by_type,
        "chapters_with_under_extraction": chapters_with_issues,
        "under_extraction_rate": len(chapters_with_issues) / total if total > 0 else 0.0,
    }


def format_diagnostic_report(summary: Dict[str, Any]) -> str:
    """
    Format a diagnostic summary as a human-readable report.
    
    Args:
        summary: Output from get_extraction_diagnostic_summary()
        
    Returns:
        Formatted string report
    """
    lines = [
        "=" * 60,
        "EXTRACTION DIAGNOSTIC REPORT",
        "=" * 60,
        f"Total chapters analyzed: {summary['total_chapters']}",
        f"Chapters with under-extraction: {len(summary['chapters_with_under_extraction'])}",
        f"Under-extraction rate: {summary['under_extraction_rate']:.1%}",
        "",
        "BY EVIDENCE TYPE:",
        "-" * 40,
    ]
    
    for etype, stats in summary.get("by_evidence_type", {}).items():
        lines.append(f"  {etype.upper()}:")
        lines.append(f"    Detected in: {stats['detected']} chapters")
        lines.append(f"    Extracted in: {stats['emitted']} chapters")
        lines.append(f"    Under-extracted: {stats['under_extracted']} chapters")
        lines.append(f"    Recall rate: {stats['recall_rate']:.1%}")
        lines.append("")
    
    if summary["chapters_with_under_extraction"]:
        lines.append("CHAPTERS WITH UNDER-EXTRACTION:")
        lines.append("-" * 40)
        for ch in summary["chapters_with_under_extraction"][:10]:
            lines.append(f"  - {ch}")
        if len(summary["chapters_with_under_extraction"]) > 10:
            lines.append(f"  ... and {len(summary['chapters_with_under_extraction']) - 10} more")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)
