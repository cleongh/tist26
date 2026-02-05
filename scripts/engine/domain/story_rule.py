"""
StoryRule - A story-specific rule that can modify/override universal rules.

Part of the domain model for state management.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StoryRule:
    """
    A story-specific rule that can modify/override universal rules.
    
    Story rules encode story-specific logic that overrides or extends
    the universal narrative rules. They are established by events and
    can be invalidated when relationships change.
    
    Rule Types:
        - relationship: Rules about character relationships
        - trait: Rules about character traits
        - location: Rules about location assignments
        - possession: Rules about item possession
        - temporal: Rules about temporal ordering
    
    Attributes:
        rule_type: Type of rule ('relationship', 'trait', 'location', 'possession', 'temporal')
        subject: The subject of the rule (character/item/location ID)
        predicate: The predicate or property being established
        object: Optional object of the rule (e.g., related character, location)
        established_by: Event ID that established this rule
        valid: Whether the rule is currently valid
    """
    rule_type: str  # 'relationship', 'trait', 'location', 'possession', 'temporal'
    subject: str
    predicate: str
    object: Optional[str] = None
    established_by: str = "e0"  # Event ID that established this rule
    valid: bool = True
