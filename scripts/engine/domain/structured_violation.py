"""
StructuredViolation - Structured violation output.

Per LOGIC_DESIGN.md Section 5.5: Output is structured JSON only.
Phase 7: Enhanced with canonical IDs, aliases, item lifecycle.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .violation_severity import ViolationSeverity
from .provenance import Provenance
from .entity_diagnostic_info import EntityDiagnosticInfo


@dataclass
class StructuredViolation:
    """
    Structured violation output per LOGIC_DESIGN.md Section 5.5.
    
    Each issue includes:
        - Violated rule
        - Entities involved (Phase 7: with canonical IDs and aliases)
        - Event index / time
        - Severity
        - Provenance (Phase 5)
    
    NO natural language interpretation - pure structured data.
    
    Phase 7: All entity references use canonical IDs. Entity info includes
    aliases and item lifecycle/relevance when applicable.
    """
    rule: str                           # The rule that was violated
    category: str                       # coherence, causality, temporal, location, emotional
    violation_type: str                 # Specific type (dead_agent, impossible_location, etc.)
    event_id: str                       # Event that triggered the violation
    event_time: int                     # Timestep of the event
    entities: List[str]                 # Canonical entity IDs involved in the violation
    severity: ViolationSeverity = ViolationSeverity.SOFT
    source_text: Optional[str] = None   # Original text that was evaluated
    provenance: Optional[Provenance] = None  # How this was concluded (Phase 5)
    # Phase 7: Enhanced entity diagnostics
    entity_info: List[EntityDiagnosticInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "rule": self.rule,
            "category": self.category,
            "type": self.violation_type,
            "event_id": self.event_id,
            "event_time": self.event_time,
            "entities": self.entities,
            "severity": self.severity.value,
            "source_text": self.source_text,
        }
        if self.provenance:
            result["provenance"] = self.provenance.to_dict()
        # Phase 7: Include entity diagnostic info
        if self.entity_info:
            result["entity_info"] = [e.to_dict() for e in self.entity_info]
        return result
