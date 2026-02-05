"""
ChapterEvaluationResult - Structured result of evaluating a chapter.

Per LOGIC_DESIGN.md Section 5.5: Output is structured JSON only.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .structured_violation import StructuredViolation


@dataclass
class ChapterEvaluationResult:
    """
    Structured result of evaluating a chapter.
    
    Per LOGIC_DESIGN.md Section 5.5: Output is structured JSON only.
    
    Contains:
        - List of violations with full metadata
        - State changes applied during evaluation
        - Chapter summary statistics
        - Provenance tracking (Phase 5)
    
    Does NOT contain:
        - Natural language descriptions
        - LLM interpretations
        - Suggested fixes
    """
    chapter_num: int
    event_count: int
    violations: List[StructuredViolation] = field(default_factory=list)
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    asp_facts: str = ""
    evaluation_mode: str = "batch"  # "batch" or "sequential"
    rules_applied: List[str] = field(default_factory=list)  # Rule IDs used (Phase 5)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "chapter_num": self.chapter_num,
            "event_count": self.event_count,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "state_changes": self.state_changes,
            "evaluation_mode": self.evaluation_mode,
            "rules_applied": self.rules_applied,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
