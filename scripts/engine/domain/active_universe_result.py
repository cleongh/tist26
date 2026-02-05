"""
Active Universe Result Dataclass.

Contains the result of active universe computation - sets of entity IDs
visible to ASP.
"""

from dataclasses import dataclass
from typing import Dict, Set, Any


@dataclass
class ActiveUniverseResult:
    """
    Result of active universe computation.
    
    Contains sets of canonical entity IDs that should be visible to ASP.
    """
    characters: Set[str]
    items: Set[str]
    locations: Set[str]
    
    # Statistics for debugging/logging
    current_chapter_actors: int = 0
    previous_chapter_actors: int = 0
    relationship_expansions: int = 0
    item_expansions: int = 0
    
    @property
    def all_entities(self) -> Set[str]:
        """Get all entity IDs (characters + items + locations)."""
        return self.characters | self.items | self.locations
    
    @property
    def total_count(self) -> int:
        """Total number of entities in the active universe."""
        return len(self.characters) + len(self.items) + len(self.locations)
    
    def contains(self, entity_id: str) -> bool:
        """Check if an entity is in the active universe."""
        return entity_id in self.all_entities
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "characters": sorted(self.characters),
            "items": sorted(self.items),
            "locations": sorted(self.locations),
            "statistics": {
                "total": self.total_count,
                "characters": len(self.characters),
                "items": len(self.items),
                "locations": len(self.locations),
                "current_chapter_actors": self.current_chapter_actors,
                "previous_chapter_actors": self.previous_chapter_actors,
                "relationship_expansions": self.relationship_expansions,
                "item_expansions": self.item_expansions,
            }
        }
