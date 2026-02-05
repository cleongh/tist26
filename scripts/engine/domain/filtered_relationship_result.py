"""
Filtered Relationship Result - Result of relationship filtering by active universe.

Phase 8.10: Tracks which relationships were projected and filtered.
"""

from dataclasses import dataclass, field
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .relationship import Relationship


@dataclass
class FilteredRelationshipResult:
    """
    Result of relationship filtering.
    
    Attributes:
        projected: Relationships that passed the active universe filter
        filtered_count: Number of relationships filtered out
        total_in_registry: Total relationships in the persistent registry
    """
    projected: List['Relationship'] = field(default_factory=list)
    filtered_count: int = 0
    total_in_registry: int = 0
    
    @property
    def projected_count(self) -> int:
        return len(self.projected)
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for diagnostics."""
        return {
            "total_in_registry": self.total_in_registry,
            "projected_count": self.projected_count,
            "filtered_count": self.filtered_count,
            "projected": [
                {"source": r.source, "target": r.target, "type": r.rel_type}
                for r in self.projected
            ],
        }
