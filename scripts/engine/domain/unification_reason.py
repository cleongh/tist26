"""
Unification Reason - Enum for Canonical ID Unification Reasons

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
"""

from enum import Enum


class UnificationReason(Enum):
    """Reason why two canonical IDs were unified."""
    FIRST_SEEN_WINS = "first_seen_wins"
    SHARED_ALIAS = "shared_alias"
    EXPLICIT_MERGE = "explicit_merge"
