"""
Lifecycle Registry - Manages Entity Lifecycle States

Responsibilities:
    - Track and update entity lifecycle states (ACTIVE, LATENT, FROZEN)
    - Provide queries for entities by lifecycle state
    - Reactivate dormant entities when they re-appear

Per LOGIC_DESIGN.md:
    - Only ACTIVE entities participate in logic (WorldState/ASP)
    - LATENT and FROZEN entities remain for future reactivation

Lifecycle Tracking (Phase 8.3):
    - ACTIVE: Entity acted within last 3 chapters
    - LATENT: Inactive for 3-9 chapters
    - FROZEN: Inactive for ≥10 chapters
    - Lifecycle updates at end of each chapter (deterministic)
"""

from typing import Dict, List, Set, Any, TYPE_CHECKING

from ..domain import LifecycleState, RegisteredEntity, EntityType

if TYPE_CHECKING:
    from .entity_registry import EntityRegistry


class LifecycleRegistry:
    """
    Manages entity lifecycle states.
    
    Works with EntityRegistry to track and update lifecycle states
    for all registered entities. Provides queries for entities
    by lifecycle state.
    
    Does NOT:
        - Store entities (delegated to EntityRegistry)
        - Make reasoning decisions
        - Generate ASP facts (delegated to ToAspConverter)
    
    Usage:
        lifecycle_registry = LifecycleRegistry(entity_registry)
        
        # Update lifecycle states at end of chapter
        counts = lifecycle_registry.update_lifecycle_states(current_chapter)
        
        # Get active entities for logic processing
        active = lifecycle_registry.get_active_entities()
    """
    
    def __init__(self, entity_registry: 'EntityRegistry'):
        """
        Initialize the LifecycleRegistry.
        
        Args:
            entity_registry: The EntityRegistry to manage lifecycles for
        """
        self._entity_registry = entity_registry
        
        # Statistics
        self._lifecycle_updates: int = 0
        self._reactivations: int = 0
    
    # =========================================================================
    # Lifecycle Management
    # =========================================================================
    
    def update_lifecycle_states(self, current_chapter: int) -> Dict[str, int]:
        """
        Update lifecycle states for all entities at end of chapter.
        
        This is the authoritative lifecycle update point. Must be called
        at the end of each chapter to transition entities between states.
        
        Args:
            current_chapter: The chapter number that just completed
            
        Returns:
            Dict with counts: {"active": N, "latent": N, "frozen": N}
        """
        counts = {"active": 0, "latent": 0, "frozen": 0}
        
        for entity in self._entity_registry.get_all_entities().values():
            new_state = entity.update_lifecycle(current_chapter)
            counts[new_state.value] += 1
        
        self._lifecycle_updates += 1
        return counts
    
    def get_active_entities(self) -> List[RegisteredEntity]:
        """Get all entities with ACTIVE lifecycle state."""
        return self._entity_registry.get_entities_by_lifecycle(LifecycleState.ACTIVE)
    
    def get_latent_entities(self) -> List[RegisteredEntity]:
        """Get all entities with LATENT lifecycle state."""
        return self._entity_registry.get_entities_by_lifecycle(LifecycleState.LATENT)
    
    def get_frozen_entities(self) -> List[RegisteredEntity]:
        """Get all entities with FROZEN lifecycle state."""
        return self._entity_registry.get_entities_by_lifecycle(LifecycleState.FROZEN)
    
    def get_active_canonical_ids(self, entity_type: EntityType = None) -> Set[str]:
        """
        Get canonical IDs of ACTIVE entities only.
        
        Args:
            entity_type: Optional filter by entity type
        """
        active = self.get_active_entities()
        if entity_type:
            return {e.canonical_id for e in active if e.entity_type == entity_type}
        return {e.canonical_id for e in active}
    
    def reactivate_entity(self, identifier: str, chapter: int) -> bool:
        """
        Reactivate a LATENT or FROZEN entity by marking it as acted.
        
        Use this when an entity re-appears in the narrative.
        
        Args:
            identifier: The entity identifier to reactivate
            chapter: The chapter where entity re-appeared
            
        Returns:
            True if entity was found and reactivated, False otherwise
        """
        entity = self._entity_registry.get_entity(identifier)
        if entity:
            entity.update_acted(chapter)
            entity.update_seen(chapter)
            entity.lifecycle_state = LifecycleState.ACTIVE
            self._reactivations += 1
            return True
        return False
    
    def get_lifecycle_breakdown(self) -> Dict[str, int]:
        """Get count of entities by lifecycle state."""
        return {
            "active": len(self.get_active_entities()),
            "latent": len(self.get_latent_entities()),
            "frozen": len(self.get_frozen_entities()),
        }
    
    # =========================================================================
    # Statistics and Serialization
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get lifecycle registry statistics."""
        breakdown = self.get_lifecycle_breakdown()
        return {
            "active": breakdown["active"],
            "latent": breakdown["latent"],
            "frozen": breakdown["frozen"],
            "lifecycle_updates": self._lifecycle_updates,
            "reactivations": self._reactivations,
        }
    
    def reset(self) -> None:
        """Reset lifecycle statistics (does not reset entities)."""
        self._lifecycle_updates = 0
        self._reactivations = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Export lifecycle state for serialization."""
        return {
            "statistics": self.get_statistics(),
            "lifecycle_breakdown": self.get_lifecycle_breakdown(),
        }
    
    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Load lifecycle state from dict.
        
        Note: Entity lifecycle states are stored in EntityRegistry.
        This only restores lifecycle registry statistics.
        """
        stats = data.get("statistics", {})
        self._lifecycle_updates = stats.get("lifecycle_updates", 0)
        self._reactivations = stats.get("reactivations", 0)
    
    def __repr__(self) -> str:
        breakdown = self.get_lifecycle_breakdown()
        return (
            f"LifecycleRegistry(active={breakdown['active']}, "
            f"latent={breakdown['latent']}, frozen={breakdown['frozen']})"
        )
