"""
Provenance - Tracks how conclusions were reached.

Phase 5, Step 5.1: Provenance tracking for full auditability.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Provenance:
    """
    Provenance tracking for conclusions (Phase 5, Step 5.1).
    
    Tracks how a conclusion was reached for full auditability.
    """
    rule_id: str                        # ID of the rule that produced this conclusion
    rule_layer: str                     # "universal", "learned", or "story"
    chapter: int                        # Chapter where this was concluded
    event_id: Optional[str] = None      # Event that triggered this (if applicable)
    derived_from: List[str] = field(default_factory=list)  # IDs of facts used to derive this
    timestamp: str = ""                 # When this was concluded
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "rule_id": self.rule_id,
            "rule_layer": self.rule_layer,
            "chapter": self.chapter,
            "event_id": self.event_id,
            "derived_from": self.derived_from,
            "timestamp": self.timestamp,
        }
