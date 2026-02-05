"""
Promotion Reason - Enum for Canonical ID Promotion Reasons

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
"""

from enum import Enum


class PromotionReason(Enum):
    """Reason why a canonical ID was promoted."""
    LONGER_DESCRIPTIVE_ID = "longer_descriptive_id"
    FULL_NAME_VS_PARTIAL = "full_name_vs_partial"
    SNAKE_CASE_VS_GENERIC = "snake_case_vs_generic"
