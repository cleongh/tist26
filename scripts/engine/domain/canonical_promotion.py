"""
Canonical Promotion - Records when a canonical ID is promoted to a better one

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
"""

from dataclasses import dataclass
from typing import Dict, Any

from .promotion_reason import PromotionReason


@dataclass
class CanonicalPromotion:
    """Records when a canonical ID is promoted to a better one."""
    old_canonical: str
    new_canonical: str
    full_name: str
    chapter: int
    reason: PromotionReason
    entity_type: str  # "character" or "location"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_canonical": self.old_canonical,
            "new_canonical": self.new_canonical,
            "full_name": self.full_name,
            "chapter": self.chapter,
            "reason": self.reason.value,
            "entity_type": self.entity_type,
        }
