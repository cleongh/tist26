"""
Derived Transition - Represents an implicit location transition.

These are NOT extracted from text - they are inferred from location changes
between consecutive events for the same agent.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..preprocessors import AspConverter


@dataclass
class DerivedTransition:
    """
    Represents an implicit location transition derived from event sequence.
    
    These are NOT extracted from text - they are inferred from location changes
    between consecutive events for the same agent.
    """
    agent: str
    from_location: str
    to_location: str
    after_event_id: str  # Event ID after which this transition occurs
    before_event_id: str  # Event ID before which this transition occurs
    chapter: int
    derived_event_id: str  # Synthetic event ID for the implicit leave
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "from_location": self.from_location,
            "to_location": self.to_location,
            "after_event_id": self.after_event_id,
            "before_event_id": self.before_event_id,
            "chapter": self.chapter,
            "derived_event_id": self.derived_event_id,
            "is_derived": True,
        }
    
    def to_asp_facts(self, asp_converter: 'AspConverter' = None) -> List[str]:
        """
        Generate ASP facts for this derived transition.
        
        Args:
            asp_converter: Optional AspConverter instance (creates one if not provided)
            
        Returns:
            List of ASP fact strings
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.derived_transition_to_asp(self)
