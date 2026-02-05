"""
Severity classification for violations.

Per LOGIC_DESIGN.md Section 5.5:
    - Hard contradiction: impossible in story world
    - Soft inconsistency: unusual but possible
    - Warning: potential issue
"""

from ..domain.violation_severity import ViolationSeverity


# Hard contradiction types (impossible regardless of story type)
HARD_VIOLATION_TYPES = {
    "dead_agent",           # Dead characters can't act
    "dead_patient",         # Dead characters can't be acted upon
    "invalid_time_order",   # Temporal impossibility
    "circular_dependency",  # Logical impossibility
    "self_contradiction",   # Direct contradiction
}

# Categories that indicate soft inconsistencies
SOFT_VIOLATION_CATEGORIES = {"emotional", "coherence"}


def classify_severity(category: str, violation_type: str) -> ViolationSeverity:
    """
    Classify violation severity based on category and type.
    
    Per LOGIC_DESIGN.md Section 5.5:
        - Hard contradiction: impossible in story world
        - Soft inconsistency: unusual but possible
        - Warning: potential issue
    
    ALL classification is based on structural rules, NOT Python heuristics
    about story content (e.g., no "if fantasy world then..." logic).
    
    Args:
        category: The violation category (e.g., "coherence", "temporal", "system")
        violation_type: The specific violation type (e.g., "dead_agent")
        
    Returns:
        ViolationSeverity enum value
    """
    # Hard contradictions (impossible regardless of story type)
    if violation_type in HARD_VIOLATION_TYPES:
        return ViolationSeverity.HARD
    
    # System errors are hard
    if category == "system":
        return ViolationSeverity.HARD
    
    # Soft inconsistencies (unusual but story might explain)
    if category in SOFT_VIOLATION_CATEGORIES:
        return ViolationSeverity.SOFT
    
    # Default to warning for unknown types
    return ViolationSeverity.WARNING
