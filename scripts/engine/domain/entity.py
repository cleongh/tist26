"""
Entity - Represents an entity in the Logic Knowledge Graph.

Part of the domain model for state management.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class Entity:
    """
    Represents an entity in the Logic Knowledge Graph.
    
    Entities can be characters, locations, or items.
    
    Attributes:
        id: Unique identifier for the entity
        entity_type: Type of entity ('character', 'location', 'item')
        traits: Set of trait identifiers
        state: Current state ('alive', 'dead', etc.)
        emotion: Current emotional state (for characters)
        aliases: Alternative names for this entity
        relevance: Item relevance classification ('causal', 'latent')
    """
    id: str
    entity_type: str  # 'character', 'location', 'item'
    traits: Set[str] = field(default_factory=set)
    state: str = "alive"  # 'alive', 'dead', etc.
    emotion: Optional[str] = None
    # Phase 1: New optional fields for enhanced extraction
    aliases: List[str] = field(default_factory=list)
    relevance: Optional[str] = None  # Item relevance: "causal" | "latent"
