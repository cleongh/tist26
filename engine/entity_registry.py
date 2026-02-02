"""
Entity Registry - Canonical Entity Storage Across Chapters

Responsibilities:
    - Store entities keyed by canonical ID (set-like behavior)
    - Track entity metadata: entity_type, aliases, chapter history
    - Deduplicate entities across chapters (add once, update on re-encounter)
    - Generate static ASP facts for Clingo
    - Manage entity lifecycle states (ACTIVE, LATENT, FROZEN)

Per LOGIC_DESIGN.md Section 3.2:
    Entities: character(X), location(X), item(X)
    Each entity has exactly one canonical ID
    
Memory Optimization (Phase 8.2):
    - Replaces persistent_entities dict in StateManager
    - Set-like behavior: entities added once, metadata updated on re-encounter
    - No duplicate entities across chapters

Lifecycle Tracking (Phase 8.3):
    - ACTIVE: Entity acted within last 3 chapters
    - LATENT: Inactive for 3-9 chapters
    - FROZEN: Inactive for ≥10 chapters
    - Only ACTIVE entities are included in WorldState/ASP
    - Lifecycle updates at end of each chapter (deterministic)

Integration:
    - StateManager delegates entity storage to EntityRegistry
    - EventExecutor calls register_entity() instead of add_entity()
    - ASP facts derived from registry on demand (ACTIVE only)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple, TYPE_CHECKING
from enum import Enum
import re

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult


class EntityType(Enum):
    """Valid entity types per LOGIC_DESIGN.md Section 3.2."""
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"


class LifecycleState(Enum):
    """
    Entity lifecycle states for memory optimization.
    
    Lifecycle rules (deterministic):
        - ACTIVE: Entity acted within last 3 chapters
        - LATENT: Inactive for 3-9 chapters  
        - FROZEN: Inactive for ≥10 chapters
    
    Only ACTIVE entities participate in logic (WorldState/ASP).
    LATENT and FROZEN entities remain in registry for future reactivation.
    """
    ACTIVE = "active"
    LATENT = "latent"
    FROZEN = "frozen"


# Lifecycle threshold constants
ACTIVE_THRESHOLD = 3    # Entity is ACTIVE if acted within last N chapters
LATENT_THRESHOLD = 10   # Entity is LATENT if inactive for N to (FROZEN-1) chapters


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
    
    def to_asp_fact(self) -> str:
        """Generate ASP entity declaration fact."""
        return f"{self.entity_type.value}({self.canonical_id})."
    
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


class EntityRegistry:
    """
    Canonical entity storage across chapters.
    
    Provides:
        - Set-like entity storage (add once, update on re-encounter)
        - Cross-chapter deduplication
        - Chapter history tracking
        - ASP fact generation
    
    Does NOT:
        - Invent new entity IDs
        - Make reasoning decisions
        - Encode story logic
    
    Usage:
        registry = EntityRegistry()
        
        # Register entities as they are extracted
        registry.register_entity("harry", EntityType.CHARACTER, chapter=0)
        registry.register_entity("harry", EntityType.CHARACTER, chapter=5)  # Updates metadata only
        
        # Get ASP facts
        facts = registry.get_asp_facts()
    """
    
    def __init__(self):
        # canonical_id -> RegisteredEntity
        self._entities: Dict[str, RegisteredEntity] = {}
        
        # Alias resolution: alias -> canonical_id
        self._alias_to_canonical: Dict[str, str] = {}
        
        # Statistics
        self._registrations: int = 0
        self._updates: int = 0
    
    @staticmethod
    def _normalize_id(value: Any) -> str:
        """Normalize an identifier to canonical snake_case form."""
        if not value:
            return ""
        s = str(value).lower().strip()
        s = re.sub(r'[\s\-]+', '_', s)
        s = re.sub(r'[^a-z0-9_]', '', s)
        s = re.sub(r'_+', '_', s)
        s = s.strip('_')
        if s and s[0].isdigit():
            s = 'n' + s
        return s
    
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
            canonical_id: The canonical ID (will be normalized)
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
        canonical_id = self._normalize_id(canonical_id)
        if not canonical_id:
            raise ValueError("Cannot register entity with empty canonical_id")
        
        if canonical_id in self._entities:
            # Update existing entity
            entity = self._entities[canonical_id]
            entity.update_seen(chapter)
            
            if aliases:
                entity.add_aliases([self._normalize_id(a) for a in aliases])
            if traits:
                entity.add_traits(traits)
            if state:
                entity.state = state
            if emotion:
                entity.emotion = emotion
            if relevance:
                entity.relevance = relevance
            if is_agent:
                entity.update_acted(chapter)
            
            # Update alias mappings
            self._register_aliases(canonical_id, aliases)
            
            self._updates += 1
            return entity
        else:
            # Create new entity
            normalized_aliases = set()
            if aliases:
                normalized_aliases = {self._normalize_id(a) for a in aliases if a}
                normalized_aliases.discard("")
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
                emotion=emotion,
                relevance=relevance,
            )
            
            self._entities[canonical_id] = entity
            
            # Register alias mappings
            self._alias_to_canonical[canonical_id] = canonical_id
            self._register_aliases(canonical_id, aliases)
            
            self._registrations += 1
            return entity
    
    def _register_aliases(self, canonical_id: str, aliases: List[str] = None) -> None:
        """Register alias mappings."""
        if not aliases:
            return
        for alias in aliases:
            normalized = self._normalize_id(alias)
            if normalized and normalized != canonical_id:
                # Only register if not already mapped to a different canonical
                existing = self._alias_to_canonical.get(normalized)
                if existing is None or existing == canonical_id:
                    self._alias_to_canonical[normalized] = canonical_id
    
    def resolve(self, identifier: str) -> Optional[str]:
        """
        Resolve an identifier to its canonical ID.
        
        Returns None if not found.
        """
        normalized = self._normalize_id(identifier)
        return self._alias_to_canonical.get(normalized)
    
    def get_entity(self, identifier: str) -> Optional[RegisteredEntity]:
        """Get entity by canonical ID or alias."""
        canonical = self.resolve(identifier)
        if canonical:
            return self._entities.get(canonical)
        return None
    
    def has_entity(self, identifier: str) -> bool:
        """Check if entity exists."""
        return self.resolve(identifier) is not None
    
    def mark_dead(self, identifier: str, chapter: int = None) -> bool:
        """Mark a character as dead."""
        entity = self.get_entity(identifier)
        if entity and entity.entity_type == EntityType.CHARACTER:
            entity.state = "dead"
            if chapter is not None:
                entity.update_seen(chapter)
            return True
        return False
    
    def is_dead(self, identifier: str) -> bool:
        """Check if a character is dead."""
        entity = self.get_entity(identifier)
        return entity is not None and entity.state == "dead"
    
    def set_emotion(self, identifier: str, emotion: str, chapter: int = None) -> bool:
        """Set a character's emotion."""
        entity = self.get_entity(identifier)
        if entity and entity.entity_type == EntityType.CHARACTER:
            entity.emotion = self._normalize_id(emotion)
            if chapter is not None:
                entity.update_seen(chapter)
            return True
        return False
    
    def add_trait(self, identifier: str, trait: str, chapter: int = None) -> bool:
        """Add a trait to an entity."""
        entity = self.get_entity(identifier)
        if entity:
            entity.traits.add(self._normalize_id(trait))
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
        
        for entity in self._entities.values():
            new_state = entity.update_lifecycle(current_chapter)
            counts[new_state.value] += 1
        
        return counts
    
    def get_active_entities(self) -> List[RegisteredEntity]:
        """Get all entities with ACTIVE lifecycle state."""
        return [e for e in self._entities.values() if e.is_active]
    
    def get_latent_entities(self) -> List[RegisteredEntity]:
        """Get all entities with LATENT lifecycle state."""
        return [e for e in self._entities.values() 
                if e.lifecycle_state == LifecycleState.LATENT]
    
    def get_frozen_entities(self) -> List[RegisteredEntity]:
        """Get all entities with FROZEN lifecycle state."""
        return [e for e in self._entities.values() 
                if e.lifecycle_state == LifecycleState.FROZEN]
    
    def reactivate_entity(self, identifier: str, chapter: int) -> bool:
        """
        Reactivate a LATENT or FROZEN entity by marking it as acted.
        
        Use this when an entity re-appears in the narrative.
        """
        entity = self.get_entity(identifier)
        if entity:
            entity.update_acted(chapter)
            entity.update_seen(chapter)
            entity.lifecycle_state = LifecycleState.ACTIVE
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
    
    # =========================================================================
    # ASP Fact Generation
    # =========================================================================
    
    def get_asp_facts(
        self, 
        active_only: bool = True,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get ASP entity declaration facts.
        
        Args:
            active_only: If True, only include ACTIVE entities (default).
                        LATENT and FROZEN entities are excluded from logic.
            active_universe: If provided, only include entities in this universe.
                           Phase 8.6: ASP grounding optimization.
        
        Returns facts like:
            character(harry).
            location(hogwarts).
            item(wand).
        """
        facts = []
        for entity in self._entities.values():
            # Skip inactive entities if active_only
            if active_only and not entity.is_active:
                continue
            # Skip entities not in active universe (Phase 8.6)
            if active_universe and entity.canonical_id not in active_universe.all_entities:
                continue
            facts.append(entity.to_asp_fact())
        return facts
    
    def get_dead_character_facts(
        self, 
        active_only: bool = True,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get ASP facts for dead characters.
        
        Args:
            active_only: If True, only include ACTIVE dead characters.
            active_universe: If provided, only include entities in this universe.
        """
        dead_chars = self.get_dead_characters()
        facts = []
        for e in dead_chars:
            if active_only and not e.is_active:
                continue
            if active_universe and e.canonical_id not in active_universe.all_entities:
                continue
            facts.append(f"is_dead({e.canonical_id}).")
        return facts
    
    def get_trait_facts(
        self, 
        active_only: bool = True,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get ASP trait facts for entities.
        
        Args:
            active_only: If True, only include ACTIVE entities.
            active_universe: If provided, only include entities in this universe.
        """
        facts = []
        entities = self.get_active_entities() if active_only else self._entities.values()
        for entity in entities:
            if active_universe and entity.canonical_id not in active_universe.all_entities:
                continue
            for trait in entity.traits:
                facts.append(f"trait({entity.canonical_id}, {trait}).")
        return facts
    
    def get_emotion_facts(
        self, 
        active_only: bool = True,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get ASP emotion facts for characters.
        
        Args:
            active_only: If True, only include ACTIVE characters.
            active_universe: If provided, only include entities in this universe.
        """
        facts = []
        characters = self.get_all_characters()
        for entity in characters:
            if active_only and not entity.is_active:
                continue
            if active_universe and entity.canonical_id not in active_universe.all_entities:
                continue
            if entity.emotion:
                facts.append(f"character_emotion({entity.canonical_id}, {entity.emotion}).")
        return facts
    
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
    
    # =========================================================================
    # Statistics and Serialization
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics including lifecycle breakdown."""
        return {
            "total_entities": len(self._entities),
            "characters": len(self.get_all_characters()),
            "locations": len(self.get_all_locations()),
            "items": len(self.get_all_items()),
            "dead_characters": len(self.get_dead_characters()),
            "aliases": len(self._alias_to_canonical),
            "registrations": self._registrations,
            "updates": self._updates,
            # Lifecycle breakdown
            "active": len(self.get_active_entities()),
            "latent": len(self.get_latent_entities()),
            "frozen": len(self.get_frozen_entities()),
        }
    
    def reset(self) -> None:
        """Reset registry to initial state."""
        self._entities.clear()
        self._alias_to_canonical.clear()
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
            self._alias_to_canonical[eid] = eid
            for alias in entity.aliases:
                self._alias_to_canonical[alias] = eid
