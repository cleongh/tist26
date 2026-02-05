"""
Projected Rule - A story-specific rule projected into the current ASP context.

Phase 8.11: Rule projection for active universe filtering.
"""

from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class ProjectedRule:
    """
    A story-specific rule projected into the current ASP context.
    
    Attributes:
        rule_id: Unique rule identifier (from RuleRegistry)
        content: ASP rule content
        layer: Rule layer (STORY, LEARNED, UNIVERSAL)
        entities_referenced: Set of entities found in the rule
        is_active: Whether the rule passed the universe filter
        filtered_reason: Why the rule was filtered (if applicable)
    """
    rule_id: str
    content: str
    layer: str  # Store as string to avoid circular imports
    entities_referenced: Set[str] = field(default_factory=set)
    is_active: bool = True
    filtered_reason: str = ""
    
    def to_dict(self) -> Dict:
        """Serialize for diagnostics."""
        return {
            "rule_id": self.rule_id,
            "layer": self.layer,
            "entities_referenced": sorted(self.entities_referenced),
            "is_active": self.is_active,
            "filtered_reason": self.filtered_reason,
        }
