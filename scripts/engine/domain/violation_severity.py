"""
ViolationSeverity - Severity levels for violations.

Per LOGIC_DESIGN.md Section 5.5.
"""

from enum import Enum


class ViolationSeverity(Enum):
    """Severity of a violation per LOGIC_DESIGN.md."""
    HARD = "hard"           # Hard contradiction (impossible in story world)
    SOFT = "soft"           # Soft inconsistency (unusual but possible)
    WARNING = "warning"     # Potential issue (may be intentional)
