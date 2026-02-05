"""
Rule Override Dataclass.

Record of a rule being overridden.
"""

from dataclasses import dataclass


@dataclass
class RuleOverride:
    """
    Record of a rule being overridden.
    
    Per LOGIC_DESIGN.md: Contradicted rules are deactivated but retained.
    """
    overridden_rule_id: str
    overriding_rule_id: str
    reason: str
    timestamp: str = ""
