"""
WorldState - Snapshot of the world state at a specific timestep.

Part of the domain model for state management.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .entity import Entity
from .relation import Relation
from .story_rule import StoryRule


@dataclass
class WorldState:
    """
    Snapshot of the world state at a specific timestep.
    
    Contains all entities, relations, and derived facts valid at time T.
    
    Per LOGIC_DESIGN.md Section 3.3 (Global Constraints):
        - Non-ubiquity: entity cannot be in multiple locations at same time
        - Linear time: discrete, monotonic, strictly ordered
        - No branching timelines
    
    Note: ASP fact generation is handled by ToAspConverter, not this class.
    
    Attributes:
        time: The time index for this snapshot
        entities: Dict of entity ID to Entity objects
        relations: List of relations valid in this state
        derived_facts: List of derived fact strings
        story_rules: List of story-specific rules
    """
    time: int
    entities: Dict[str, Entity] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
    story_rules: List[StoryRule] = field(default_factory=list)
    
    def update_time(self, new_time: int) -> None:
        """
        Update the time index without cloning.
        
        Args:
            new_time: The new time index
        """
        self.time = new_time
