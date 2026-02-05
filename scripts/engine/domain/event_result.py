"""
EventResult - Result of executing a single event.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EventResult:
    """Result of executing a single event."""
    event_id: str
    time: int
    violations: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: List[str] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
