"""
Entity Registry - Canonical Entity Storage Across Chapters

Responsibilities:
    - Store entities keyed by canonical ID (set-like behavior)
    - Track entity metadata: entity_type, aliases, chapter history
    - Deduplicate entities across chapters (add once, update on re-encounter)

Per LOGIC_DESIGN.md Section 3.2:
    Entities: character(X), location(X), item(X)
    Each entity has exactly one canonical ID

Memory Optimization (Phase 8.2):
    - Set-like behavior: entities added once, metadata updated on re-encounter
    - No duplicate entities across chapters

Integration:
    - StateManager delegates entity storage to EntityRegistry
    - EventExecutor calls register_entity() instead of add_entity()
    - Lifecycle management delegated to LifecycleRegistry
    - ASP fact generation delegated to ToAspConverter
"""

from typing import Dict, List, Set, Optional, Any, TYPE_CHECKING

from ..domain import EntityType, LifecycleState, RegisteredEntity
from ..utils.sanitation import sanitize_id

if TYPE_CHECKING:
    from ..managers import CharacterAliasManager, LocationAliasManager


class EntityRegistry:
    """
    Canonical entity storage across chapters.
    
    Provides:
        - Set-like entity storage (add once, update on re-encounter)
        - Cross-chapter deduplication
        - Chapter history tracking
    
    Does NOT:
        - Invent new entity IDs
        - Make reasoning decisions
        - Encode story logic
        - Generate ASP facts (delegated to ToAspConverter)
        - Manage lifecycle states (delegated to LifecycleRegistry)
    
    Usage:
        registry = EntityRegistry()
        
        # Register entities as they are extracted
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0)
        registry.register_entity("harry", EntityType.CHARACTER, chapter=5)  # Updates metadata only
    """
    
    def __init__(
        self,
        character_alias_manager: Optional['CharacterAliasManager'] = None,
        location_alias_manager: Optional['LocationAliasManager'] = None,
    ):
        """
        Initialize the EntityRegistry.
        
        Args:
            character_alias_manager: Optional manager for character aliases
            location_alias_manager: Optional manager for location aliases
        """
        # canonical_id -> RegisteredEntity
        self._entities: Dict[str, RegisteredEntity] = {}
        
        # Alias managers for resolution
        self._character_alias_manager = character_alias_manager
        self._location_alias_manager = location_alias_manager
        
        # Statistics
        self._registrations: int = 0
        self._updates: int = 0
    
    def set_alias_managers(
        self,
        character_alias_manager: 'CharacterAliasManager',
        location_alias_manager: 'LocationAliasManager',
    ) -> None:
        """Set the alias managers after initialization."""
        self._character_alias_manager = character_alias_manager
        self._location_alias_manager = location_alias_manager
    
    def _resolve_identifier(self, identifier: str, entity_type: EntityType) -> str:
        """
        Resolve an identifier to its canonical ID using alias managers.
        
        Args:
            identifier: The identifier to resolve
            entity_type: The type of entity (determines which manager to use)
            
        Returns:
            The canonical ID, or the sanitized identifier if no manager available
        """
        sanitized = sanitize_id(identifier)
        
        if entity_type == EntityType.CHARACTER and self._character_alias_manager:
            return self._character_alias_manager.resolve(sanitized)
        elif entity_type == EntityType.LOCATION and self._location_alias_manager:
            return self._location_alias_manager.resolve_location(sanitized)
        
        return sanitized
    
    def register_entity(
        self,
        canonical_id: str,
        entity_type: EntityType,
        chapter: int = 0,
        aliases: List[str] = None,
        traits: Set[str] = None,
        state: str = None,
        emotion: str = None,
        relevance: str = None,
        is_agent: bool = False,
    ) -> RegisteredEntity:
        """
        Register an entity or update existing entity's metadata.
        
        If canonical_id exists: update metadata only (last_seen, aliases, etc.)
        If not: create new entry with first_seen_chapter = chapter
        
        Args:
            canonical_id: The canonical ID (will be sanitized)
            entity_type: CHARACTER, LOCATION, or ITEM
            chapter: Current chapter number
            aliases: Optional list of aliases to add
            traits: Optional set of traits to add
            state: Optional state override (e.g., "dead")
            emotion: Optional emotion state
            relevance: Optional relevance for items (causal, latent)
            is_agent: If True, update last_acted_chapter
            
        Returns:
            The RegisteredEntity (new or updated)
        """
        canonical_id = sanitize_id(canonical_id)
        if not canonical_id or canonical_id == "unknown":
            raise ValueError("Cannot register entity with empty canonical_id")
        
        if canonical_id in self._entities:
            return self._update_existing_entity(
                canonical_id, chapter, aliases, traits, state, emotion, relevance, is_agent
            )
        else:
            return self._create_new_entity(
                canonical_id, entity_type, chapter, aliases, traits, state, emotion, relevance, is_agent
            )
    
    def _update_existing_entity(
        self,
        canonical_id: str,
        chapter: int,
        aliases: List[str],
        traits: Set[str],
        state: str,
        emotion: str,
        relevance: str,
        is_agent: bool,
    ) -> RegisteredEntity:
        """Update an existing entity's metadata."""
        entity = self._entities[canonical_id]
        entity.update_seen(chapter)
        
        if aliases:
            normalized_aliases = [sanitize_id(a) for a in aliases if a]
            entity.add_aliases(normalized_aliases)
        if traits:
            entity.add_traits(traits)
        if state:
            entity.state = state
        if emotion:
            entity.emotion = sanitize_id(emotion)
        if relevance:
            entity.relevance = relevance
        if is_agent:
            entity.update_acted(chapter)
        
        self._updates += 1
        return entity
    
    def _create_new_entity(
        self,
        canonical_id: str,
        entity_type: EntityType,
        chapter: int,
        aliases: List[str],
        traits: Set[str],
        state: str,
        emotion: str,
        relevance: str,
        is_agent: bool,
    ) -> RegisteredEntity:
        """Create a new entity in the registry."""
        normalized_aliases = set()
        if aliases:
            normalized_aliases = {sanitize_id(a) for a in aliases if a}
            normalized_aliases.discard("unknown")
            normalized_aliases.discard(canonical_id)
        
        entity = RegisteredEntity(
            canonical_id=canonical_id,
            entity_type=entity_type,
            aliases=normalized_aliases,
            first_seen_chapter=chapter,
            last_seen_chapter=chapter,
            last_acted_chapter=chapter if is_agent else None,
            state=state or "alive",
            traits=traits or set(),
            emotion=sanitize_id(emotion) if emotion else None,
            relevance=relevance,
        )
        
        self._entities[canonical_id] = entity
        self._registrations += 1
        return entity
    
    def get_entity(self, identifier: str, entity_type: EntityType = None) -> Optional[RegisteredEntity]:
        """
        Get entity by canonical ID or alias.
        
        Args:
            identifier: The identifier to look up
            entity_type: Optional type hint for alias resolution
            
        Returns:
            The RegisteredEntity or None if not found
        """
        sanitized = sanitize_id(identifier)
        
        # Direct lookup first
        if sanitized in self._entities:
            return self._entities[sanitized]
        
        # Try alias resolution if managers available
        if entity_type and entity_type == EntityType.CHARACTER and self._character_alias_manager:
            canonical = self._character_alias_manager.get_canonical_id(sanitized)
            if canonical and canonical in self._entities:
                return self._entities[canonical]
        elif entity_type and entity_type == EntityType.LOCATION and self._location_alias_manager:
            canonical = self._location_alias_manager.get_location_canonical_id(sanitized)
            if canonical and canonical in self._entities:
                return self._entities[canonical]
        
        # Try both managers if no type specified
        if self._character_alias_manager:
            canonical = self._character_alias_manager.get_canonical_id(sanitized)
            if canonical and canonical in self._entities:
                return self._entities[canonical]
        if self._location_alias_manager:
            canonical = self._location_alias_manager.get_location_canonical_id(sanitized)
            if canonical and canonical in self._entities:
                return self._entities[canonical]
        
        return None
    
    def has_entity(self, identifier: str) -> bool:
        """Check if entity exists."""
        return self.get_entity(identifier) is not None
    
    def mark_dead(self, identifier: str, chapter: int = None) -> bool:
        """Mark a character as dead."""
        entity = self.get_entity(identifier, EntityType.CHARACTER)
        if entity and entity.entity_type == EntityType.CHARACTER:
            entity.state = "dead"
            if chapter is not None:
                entity.update_seen(chapter)
            return True
        return False
    
    def is_dead(self, identifier: str) -> bool:
        """Check if a character is dead."""
        entity = self.get_entity(identifier, EntityType.CHARACTER)
        return entity is not None and entity.state == "dead"
    
    def set_emotion(self, identifier: str, emotion: str, chapter: int = None) -> bool:
        """Set a character's emotion."""
        entity = self.get_entity(identifier, EntityType.CHARACTER)
        if entity and entity.entity_type == EntityType.CHARACTER:
            entity.emotion = sanitize_id(emotion)
            if chapter is not None:
                entity.update_seen(chapter)
            return True
        return False
    
    def add_trait(self, identifier: str, trait: str, chapter: int = None) -> bool:
        """Add a trait to an entity."""
        entity = self.get_entity(identifier)
        if entity:
            entity.traits.add(sanitize_id(trait))
            if chapter is not None:
                entity.update_seen(chapter)
            return True
        return False
    
    def update_acted(self, identifier: str, chapter: int) -> bool:
        """Mark entity as having acted in this chapter."""
        entity = self.get_entity(identifier)
        if entity:
            entity.update_acted(chapter)
            return True
        return False
    
    # =========================================================================
    # Queries by entity type
    # =========================================================================
    
    def get_all_characters(self) -> List[RegisteredEntity]:
        """Get all registered characters."""
        return [e for e in self._entities.values() if e.entity_type == EntityType.CHARACTER]
    
    def get_all_locations(self) -> List[RegisteredEntity]:
        """Get all registered locations."""
        return [e for e in self._entities.values() if e.entity_type == EntityType.LOCATION]
    
    def get_all_items(self) -> List[RegisteredEntity]:
        """Get all registered items."""
        return [e for e in self._entities.values() if e.entity_type == EntityType.ITEM]
    
    def get_dead_characters(self) -> List[RegisteredEntity]:
        """Get all dead characters."""
        return [e for e in self.get_all_characters() if e.state == "dead"]
    
    def get_canonical_ids(self, entity_type: EntityType = None) -> Set[str]:
        """Get all canonical IDs, optionally filtered by type."""
        if entity_type:
            return {e.canonical_id for e in self._entities.values() if e.entity_type == entity_type}
        return set(self._entities.keys())
    
    def get_all_entities(self) -> Dict[str, RegisteredEntity]:
        """Get all entities (read-only view)."""
        return dict(self._entities)
    
    def get_entities_by_lifecycle(self, lifecycle_state: LifecycleState) -> List[RegisteredEntity]:
        """Get all entities with a specific lifecycle state."""
        return [e for e in self._entities.values() if e.lifecycle_state == lifecycle_state]
    
    # =========================================================================
    # Statistics and Serialization
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_entities": len(self._entities),
            "characters": len(self.get_all_characters()),
            "locations": len(self.get_all_locations()),
            "items": len(self.get_all_items()),
            "dead_characters": len(self.get_dead_characters()),
            "registrations": self._registrations,
            "updates": self._updates,
        }
    
    def reset(self) -> None:
        """Reset registry to initial state."""
        self._entities.clear()
        self._registrations = 0
        self._updates = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry state for serialization."""
        return {
            "entities": {eid: e.to_dict() for eid, e in self._entities.items()},
            "statistics": self.get_statistics(),
        }
    
    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Load registry state from dict."""
        self.reset()
        for eid, edata in data.get("entities", {}).items():
            # Parse lifecycle_state, default to ACTIVE for backward compatibility
            lifecycle_str = edata.get("lifecycle_state", "active")
            try:
                lifecycle = LifecycleState(lifecycle_str)
            except ValueError:
                lifecycle = LifecycleState.ACTIVE
            
            entity = RegisteredEntity(
                canonical_id=edata["canonical_id"],
                entity_type=EntityType(edata["entity_type"]),
                aliases=set(edata.get("aliases", [])),
                first_seen_chapter=edata.get("first_seen_chapter", 0),
                last_seen_chapter=edata.get("last_seen_chapter", 0),
                last_acted_chapter=edata.get("last_acted_chapter"),
                lifecycle_state=lifecycle,
                state=edata.get("state", "alive"),
                traits=set(edata.get("traits", [])),
                emotion=edata.get("emotion"),
                relevance=edata.get("relevance"),
            )
            self._entities[eid] = entity
    
    def __repr__(self) -> str:
        return (
            f"EntityRegistry(entities={len(self._entities)}, "
            f"registrations={self._registrations}, updates={self._updates})"
        )
