"""
Time Scope Dataclass.

Defines the valid time window for ASP fact generation.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..preprocessors import AspConverter


@dataclass
class TimeScope:
    """
    Defines the valid time window for ASP fact generation.
    
    Per LOGIC_DESIGN.md Section 4: Events are state transitions at specific timesteps.
    To limit ASP grounding, we only include facts for:
    - current_time: The time window for the current chapter
    - previous_time: The time window for the previous chapter (for continuity)
    
    All other timesteps are excluded from ASP facts.
    """
    current_chapter: int
    current_time_start: int  # First event time in current chapter
    current_time_end: int    # Last event time in current chapter
    previous_time_start: Optional[int] = None  # First event time in previous chapter
    previous_time_end: Optional[int] = None    # Last event time in previous chapter
    
    def is_time_in_scope(self, time: int) -> bool:
        """Check if a time value is within the valid scope."""
        # Current chapter times
        if self.current_time_start <= time <= self.current_time_end:
            return True
        # Previous chapter times
        if self.previous_time_start is not None and self.previous_time_end is not None:
            if self.previous_time_start <= time <= self.previous_time_end:
                return True
        return False
    
    def get_time_facts(self, asp_converter: 'AspConverter' = None) -> List[str]:
        """
        Generate explicit time scope facts for ASP.
        
        Instead of emitting time(N) for all N, we emit:
        - current_chapter(C)
        - current_time_window(Start, End)
        - previous_time_window(Start, End)  [if applicable]
        - time(N) for only N in the valid windows
        
        Args:
            asp_converter: Optional AspConverter instance
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.time_scope_to_asp(self)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "current_chapter": self.current_chapter,
            "current_time_start": self.current_time_start,
            "current_time_end": self.current_time_end,
            "previous_time_start": self.previous_time_start,
            "previous_time_end": self.previous_time_end,
        }
