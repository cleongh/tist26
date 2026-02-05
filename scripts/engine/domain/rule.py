"""
Rule Dataclass.

Represents a single ASP rule with metadata.
"""

from dataclasses import dataclass
from typing import Optional

from .rule_layer import RuleLayer


@dataclass
class Rule:
    """
    Represents a single rule with metadata.
    
    Rules can be individual ASP rules or entire rule files.
    """
    id: str
    layer: RuleLayer
    content: str  # ASP rule content or file path
    is_file: bool = False
    active: bool = True
    overridden_by: Optional[str] = None  # ID of rule that overrides this
    source: str = ""  # Where this rule came from
    description: str = ""  # Human-readable description
    
    def get_priority(self) -> int:
        """Get numeric priority (higher = more important)."""
        return self.layer.value
