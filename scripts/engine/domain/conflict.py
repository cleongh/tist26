"""
Conflict - Record of a conflict between story and universal rules.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class Conflict:
    """
    Record of a conflict between story and universal rules.
    """
    id: str
    universal_rule_id: str
    story_rule_id: str
    violation_type: str
    entities_involved: List[str]
    event_id: str
    timestamp: str
    resolved: bool = False
    resolution: str = ""  # 'override', 'exception', 'retain'
    provenance: Dict[str, Any] = field(default_factory=dict)
