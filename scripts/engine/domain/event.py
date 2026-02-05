"""
Event - Represents a story event as a state transition.

Events are not static facts - they cause changes to the world state.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Event:
    """
    Represents a story event as a state transition.
    
    Events are not static facts - they cause changes to the world state.
    """
    id: str
    event_type: str
    time: int
    agent: Optional[str] = None
    patient: Optional[str] = None
    location: Optional[str] = None
    destination: Optional[str] = None  # For travel events
    source_text: Optional[str] = None
    emotion: Optional[str] = None  # Emotion associated with event
    metadata: Dict[str, Any] = field(default_factory=dict)
