"""
Rule Projection Result - Result of rule projection by active universe.

Phase 8.11: Tracks which rules were projected and filtered.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .projected_rule import ProjectedRule
    from ..preprocessors import AspConverter


@dataclass
class RuleProjectionResult:
    """
    Result of rule projection.
    
    Attributes:
        projected_rules: Rules that passed the active universe filter
        filtered_rules: Rules that were filtered out
        total_story_rules: Total story rules in registry
        total_learned_rules: Total learned rules in registry (Phase 8.11.1)
    """
    projected_rules: List['ProjectedRule'] = field(default_factory=list)
    filtered_rules: List['ProjectedRule'] = field(default_factory=list)
    total_story_rules: int = 0
    total_learned_rules: int = 0  # Phase 8.11.1: Learned rule tracking
    
    @property
    def projected_count(self) -> int:
        return len(self.projected_rules)
    
    @property
    def filtered_count(self) -> int:
        return len(self.filtered_rules)
    
    def get_projected_content(
        self,
        layer_filter: Optional[str] = None,
        asp_converter: 'AspConverter' = None,
    ) -> str:
        """
        Get combined content of all projected rules.
        
        Args:
            layer_filter: Optional layer to filter by ('STORY', 'LEARNED', None for all)
            asp_converter: Optional AspConverter instance
        
        Returns ASP rules ready for Clingo.
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        
        if layer_filter:
            rules = [r for r in self.projected_rules if r.layer == layer_filter]
            header = f"PROJECTED {layer_filter} RULES"
        else:
            rules = self.projected_rules
            header = "PROJECTED RULES"
        
        return asp_converter.projected_rules_to_asp(rules, header)
    
    def to_dict(self) -> Dict:
        """Serialize for diagnostics."""
        return {
            "total_story_rules": self.total_story_rules,
            "total_learned_rules": self.total_learned_rules,
            "projected_count": self.projected_count,
            "filtered_count": self.filtered_count,
            "projected": [r.to_dict() for r in self.projected_rules],
            "filtered": [r.to_dict() for r in self.filtered_rules],
        }
