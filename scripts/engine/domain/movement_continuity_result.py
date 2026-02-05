"""
Movement Continuity Result - Result of movement continuity analysis.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .derived_transition import DerivedTransition


@dataclass
class MovementContinuityResult:
    """Result of movement continuity analysis."""
    original_events: List[Dict[str, Any]]
    derived_transitions: List['DerivedTransition'] = field(default_factory=list)
    agents_analyzed: int = 0
    gaps_detected: int = 0
    gaps_bridged: int = 0
    gaps_with_explicit_movement: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agents_analyzed": self.agents_analyzed,
            "gaps_detected": self.gaps_detected,
            "gaps_bridged": self.gaps_bridged,
            "gaps_with_explicit_movement": self.gaps_with_explicit_movement,
            "derived_transitions": [t.to_dict() for t in self.derived_transitions],
        }
