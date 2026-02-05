"""
StateDelta - Represents changes between two world states.

Part of the domain model for state management.
"""

from dataclasses import dataclass, field
from typing import List

from .entity import Entity
from .relation import Relation
from .story_rule import StoryRule


@dataclass
class StateDelta:
    """
    Represents changes between two world states.
    
    Used for tracking what changed due to an event. The delta captures
    all additions and removals of entities, relations, derived facts,
    and story rules between two time points.
    
    Attributes:
        from_time: Starting time index
        to_time: Ending time index
        added_entities: List of newly added entities
        removed_entities: List of removed entity IDs
        added_relations: List of newly added relations
        removed_relations: List of removed relations
        added_derived: List of newly derived facts
        removed_derived: List of removed derived facts
        added_rules: List of newly added story rules
        invalidated_rules: List of invalidated story rules
    """
    from_time: int
    to_time: int
    added_entities: List[Entity] = field(default_factory=list)
    removed_entities: List[str] = field(default_factory=list)  # entity IDs
    added_relations: List[Relation] = field(default_factory=list)
    removed_relations: List[Relation] = field(default_factory=list)
    added_derived: List[str] = field(default_factory=list)
    removed_derived: List[str] = field(default_factory=list)
    added_rules: List[StoryRule] = field(default_factory=list)
    invalidated_rules: List[StoryRule] = field(default_factory=list)
