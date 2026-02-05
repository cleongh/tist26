"""
Registered Entity - A registered entity with cross-chapter metadata.

Per LOGIC_DESIGN.md Section 3.2:
    Entities: character(X), location(X), item(X)
    Each entity has exactly one canonical ID.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Any, TYPE_CHECKING

from .entity_type import EntityType
from .lifecycle_state import LifecycleState
from ..config import ACTIVE_THRESHOLD, LATENT_THRESHOLD

if TYPE_CHECKING:
    from ..preprocessors import AspConverter


@dataclass
class RegisteredEntity:
    """
    A registered entity with cross-chapter metadata.
    
    Tracks:
        - canonical_id: The unique identifier (immutable once set)
        - entity_type: character, location, or item
        - aliases: Set of known aliases (accumulated across chapters)
        - first_seen_chapter: Chapter where entity was first introduced
        - last_seen_chapter: Most recent chapter where entity appeared
        - last_acted_chapter: Most recent chapter where entity was an agent
        - lifecycle_state: Current lifecycle state (ACTIVE, LATENT, FROZEN)
        - state: Current entity state (alive, dead, etc.)
        - traits: Set of accumulated traits
        - relevance: Item relevance (causal, latent) for Chekhov tracking
    """
    canonical_id: str
    entity_type: EntityType
    aliases: Set[str] = field(default_factory=set)
    first_seen_chapter: int = 0
    last_seen_chapter: int = 0
    last_acted_chapter: Optional[int] = None
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    state: str = "alive"  # alive, dead, etc.
    traits: Set[str] = field(default_factory=set)
    emotion: Optional[str] = None
    relevance: Optional[str] = None  # For items: causal, latent
    
    def update_seen(self, chapter: int) -> None:
        """Update last_seen_chapter if later than current."""
        if chapter > self.last_seen_chapter:
            self.last_seen_chapter = chapter
    
    def update_acted(self, chapter: int) -> None:
        """Update last_acted_chapter if later than current."""
        if self.last_acted_chapter is None or chapter > self.last_acted_chapter:
            self.last_acted_chapter = chapter
    
    def compute_lifecycle_state(self, current_chapter: int) -> LifecycleState:
        """
        Compute lifecycle state based on chapter history.
        
        Rules (deterministic):
            - If entity acted in last 3 chapters → ACTIVE
            - If inactive for 3-9 chapters → LATENT
            - If inactive for ≥10 chapters → FROZEN
            
        Uses last_acted_chapter if available, otherwise last_seen_chapter.
        """
        # Use last_acted if available, otherwise last_seen
        reference_chapter = self.last_acted_chapter
        if reference_chapter is None:
            reference_chapter = self.last_seen_chapter
        
        chapters_inactive = current_chapter - reference_chapter
        
        if chapters_inactive < ACTIVE_THRESHOLD:
            return LifecycleState.ACTIVE
        elif chapters_inactive < LATENT_THRESHOLD:
            return LifecycleState.LATENT
        else:
            return LifecycleState.FROZEN
    
    def update_lifecycle(self, current_chapter: int) -> LifecycleState:
        """Update lifecycle_state based on current chapter. Returns new state."""
        self.lifecycle_state = self.compute_lifecycle_state(current_chapter)
        return self.lifecycle_state
    
    @property
    def is_active(self) -> bool:
        """Check if entity is in ACTIVE lifecycle state."""
        return self.lifecycle_state == LifecycleState.ACTIVE
    
    def add_aliases(self, new_aliases: List[str]) -> None:
        """Accumulate new aliases."""
        for alias in new_aliases:
            if alias and alias != self.canonical_id:
                self.aliases.add(alias)
    
    def add_traits(self, new_traits: Set[str]) -> None:
        """Accumulate new traits."""
        self.traits.update(new_traits)
    
    def to_asp_fact(self, asp_converter: 'AspConverter' = None) -> str:
        """
        Generate ASP entity declaration fact.
        
        Args:
            asp_converter: Optional AspConverter instance (creates one if not provided)
            
        Returns:
            ASP fact string like "character(harry)."
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.entity_to_asp(self)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export to dict for serialization."""
        return {
            "canonical_id": self.canonical_id,
            "entity_type": self.entity_type.value,
            "aliases": list(self.aliases),
            "first_seen_chapter": self.first_seen_chapter,
            "last_seen_chapter": self.last_seen_chapter,
            "last_acted_chapter": self.last_acted_chapter,
            "lifecycle_state": self.lifecycle_state.value,
            "state": self.state,
            "traits": list(self.traits),
            "emotion": self.emotion,
            "relevance": self.relevance,
        }
