"""
State Manager - Current World State Management

Responsibilities:
    - Maintain the Logic Knowledge Graph (LKG) state
    - Track CURRENT world state only (no historical snapshots)
    - Track entities, relations, and derived facts
    - Manage cross-chapter persistent state

Per LOGIC_DESIGN.md Section 3.2:
    Entities: character(X), location(X), item(X)
    Relations: relationship(C1, C2, Type, T), present(E, L, T), carries(C, I, T)
    Derived: item presence via carrying

Per LOGIC_DESIGN.md Section 3.3 (Global Constraints):
    - Non-ubiquity: entity cannot be in multiple locations at same time
    - Linear time: discrete, monotonic, strictly ordered
    - No branching timelines

Memory Optimization (Phase 8):
    - Removed historical WorldState snapshots (self.states dict)
    - Only current_state is kept in memory
    - advance_time() mutates in place, no deep copies
    - Historical analysis delegated to FinalAnalyzer
"""

from typing import Dict, List, Set, Tuple, Optional, Any, TYPE_CHECKING
import re

from .domain import (
    Entity,
    Relation,
    StoryRule,
    WorldState,
    StateDelta,
    EntityType,
)
from .registries import EntityRegistry
from .utils.sanitation import sanitize_id

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult
    from .preprocessors import AspConverter


def _get_asp_converter() -> 'AspConverter':
    """Lazy import to avoid circular dependency."""
    from .preprocessors import AspConverter
    return AspConverter()


# Domain classes (Entity, Relation, StoryRule, WorldState, StateDelta)
# are now imported from .domain module


class StateManager:
    """
    Manages current world state across the story timeline.
    
    Provides:
        - Current world state tracking (single WorldState, no history)
        - Entity and relation management
        - Cross-chapter persistent state
        - ASP fact generation
    
    Does NOT:
        - Store historical WorldState snapshots (memory optimization)
        - Encode story logic (delegated to ASP)
        - Make reasoning decisions
        - Interpret violations
    
    Memory Optimization (Phase 8):
        - Only self.current_state is maintained
        - advance_time() mutates in place
        - No deep copying of WorldState per chapter
        - Historical analysis delegated to FinalAnalyzer
    """
    
    def __init__(self):
        self.current_time: int = 0
        self.current_state: WorldState = WorldState(time=0)
        
        # Entity Registry (Phase 8.2): Canonical entity storage with cross-chapter deduplication
        # Replaces the role of persistent_entities as the primary entity store
        self._entity_registry: EntityRegistry = EntityRegistry()
        
        # Cross-chapter persistent state (extracted from LogicEvaluator)
        # Note: persistent_entities is kept for backward compatibility but now
        # delegates to _entity_registry for canonical storage
        self.persistent_entities: Dict[str, Entity] = {}
        self.persistent_dead: Set[str] = set()  # Characters confirmed dead
        self.persistent_relationships: Dict[Tuple[str, str], str] = {}  # (char1, char2) -> rel_type
        self.persistent_emotions: Dict[str, str] = {}  # char -> emotion
        self.persistent_traits: Dict[str, str] = {}  # char -> trait
        
        # Static facts for Clingo - derived from _entity_registry on demand
        # Memory optimization (Phase 8.1): No longer accumulates unboundedly
        # Static facts are computed from _entity_registry which tracks unique entities
        
        # Global event tracking (continuous across chapters)
        self.next_event_id: int = 1  # Start from 1, e0 reserved for initial state
        self.event_log: List[Dict] = []  # [{id, type, agent, patient, location, source_text, chapter}]
        
        # Optional AliasResolver for dynamic alias resolution
        self._alias_resolver = None
    
    def set_alias_resolver(self, alias_resolver) -> None:
        """Set the alias resolver for dynamic alias resolution."""
        self._alias_resolver = alias_resolver
    
    @property
    def entity_registry(self) -> EntityRegistry:
        """
        Get the EntityRegistry for entity management.
        
        The EntityRegistry provides set-like entity storage with cross-chapter
        deduplication. Use this for entity queries and statistics.
        """
        return self._entity_registry
    
    def get_current_state(self) -> WorldState:
        """Get the current world state."""
        return self.current_state
    
    def get_state_at(self, time: int) -> Optional[WorldState]:
        """
        Get world state at a specific timestep.
        
        Note: Only current_time is available. Returns None for historical times.
        Historical analysis is handled by FinalAnalyzer.
        """
        if time == self.current_time:
            return self.current_state
        return None
    
    def snapshot(self, time: int = None) -> WorldState:
        """
        Get the current world state.
        
        Note: Historical snapshots are no longer stored.
        Only current state is available.
        
        Per LOGIC_DESIGN.md: snapshot(T) returning current LKG
        """
        # Only current state is available
        return self.current_state
    
    def advance_time(self) -> int:
        """
        Advance to next timestep.
        
        Mutates current_state in place - no deep copying.
        Memory optimization: no historical snapshots stored.
        """
        self.current_time += 1
        self.current_state.update_time(self.current_time)
        return self.current_time
    
    def get_next_global_event_id(self) -> str:
        """Get the next global event ID and increment counter."""
        event_id = f"e{self.next_event_id}"
        self.next_event_id += 1
        return event_id
    
    # Backward compatibility alias
    def get_next_event_id(self) -> str:
        """Deprecated: Use get_next_global_event_id() instead."""
        return self.get_next_global_event_id()
    
    def add_entity(self, entity_id: str, entity_type: str, 
                   traits: Set[str] = None, state: str = "alive",
                   emotion: str = None, aliases: List[str] = None,
                   relevance: str = None, chapter: int = None) -> Entity:
        """
        Add an entity to the current world state and entity registry.
        
        If the entity already exists in the registry, only metadata is updated
        (chapter tracking). This provides set-like deduplication.
        
        Args:
            entity_id: Canonical entity identifier
            entity_type: 'character', 'location', or 'item'
            traits: Set of trait identifiers
            state: Entity state ('alive', 'dead', etc.)
            emotion: Current emotional state
            aliases: Alternative names for this entity
            relevance: Item relevance classification
            chapter: Chapter number where entity is encountered (for tracking)
        
        Returns:
            The Entity object added to the current world state
        """
        entity = Entity(
            id=entity_id,
            entity_type=entity_type,
            traits=traits or set(),
            state=state,
            emotion=emotion,
            aliases=aliases or [],
            relevance=relevance
        )
        
        current = self.get_current_state()
        current.entities[entity_id] = entity
        
        # Map entity_type to EntityType enum
        type_map = {
            'character': EntityType.CHARACTER,
            'location': EntityType.LOCATION,
            'item': EntityType.ITEM,
        }
        registry_type = type_map.get(entity_type, EntityType.CHARACTER)
        
        # Register in EntityRegistry (deduplicates automatically)
        current_chapter = chapter if chapter is not None else 0
        self._entity_registry.register_entity(
            canonical_id=entity_id,
            entity_type=registry_type,
            chapter=current_chapter,
            aliases=aliases,
            state=state,
            traits=list(traits) if traits else None,
            emotion=emotion,
            relevance=relevance,
        )
        
        # Also maintain backward-compatible persistent_entities dict
        self.persistent_entities[entity_id] = entity
        
        return entity
    
    def add_relation(self, predicate: str, args: Tuple[str, ...], 
                     source_event: str = None) -> Relation:
        """Add a time-indexed relation to the current world state."""
        relation = Relation(
            predicate=predicate,
            args=args,
            time=self.current_time,
            source_event=source_event
        )
        
        current = self.get_current_state()
        current.relations.append(relation)
        
        return relation
    
    def add_relationship(self, char1: str, char2: str, rel_type: str,
                        source_event: str = None) -> None:
        """Add a relationship between two characters (persists across chapters)."""
        char1 = sanitize_id(char1)
        char2 = sanitize_id(char2)
        rel_type = sanitize_id(rel_type)
        
        self.persistent_relationships[(char1, char2)] = rel_type
        self.add_relation("relationship", (char1, char2, rel_type), source_event)
    
    def add_presence(self, entity_id: str, location_id: str,
                     time: int = None, source_event: str = None) -> Relation:
        """
        Add a presence fact for an entity at a location.
        
        Per LOGIC_DESIGN.md Section 3.2:
            present(Entity, Location, Time) - Entity is at Location at time T
        
        This records that an entity (character or item) is present at a location
        at a specific time. Used for:
            - Explicit movement events (arrive, leave)
            - Implied presence from extraction (possessed objects, body references)
        
        Args:
            entity_id: Character or item ID
            location_id: Location ID
            time: Time index (defaults to current_time)
            source_event: Optional event ID that established this presence
            
        Returns:
            The Relation object added
        """
        entity_id = sanitize_id(entity_id)
        location_id = sanitize_id(location_id)
        
        if time is None:
            time = self.current_time
        
        return self.add_relation(
            "present",
            (entity_id, location_id),
            source_event
        )
    
    def add_story_rule(self, rule_type: str, subject: str, predicate: str,
                       obj: str = None, established_by: str = "e0") -> StoryRule:
        """Add a story-specific rule to the current state."""
        rule = StoryRule(
            rule_type=rule_type,
            subject=sanitize_id(subject),
            predicate=sanitize_id(predicate),
            object=sanitize_id(obj) if obj else None,
            established_by=established_by,
            valid=True
        )
        
        current = self.get_current_state()
        current.story_rules.append(rule)
        
        return rule
    
    def invalidate_rule(self, subject: str, obj: str, event_id: str) -> bool:
        """Invalidate an existing rule (when relationships change)."""
        subject = sanitize_id(subject)
        obj = sanitize_id(obj) if obj else None
        
        current = self.get_current_state()
        for rule in current.story_rules:
            if rule.subject == subject and rule.object == obj and rule.valid:
                rule.valid = False
                return True
        return False
    
    def mark_dead(self, character_id: str) -> None:
        """Mark a character as permanently dead."""
        character_id = sanitize_id(character_id)
        self.persistent_dead.add(character_id)
        
        # Update EntityRegistry
        self._entity_registry.mark_dead(character_id)
        
        # Update entity state (backward compatibility)
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].state = "dead"
        
        current = self.get_current_state()
        if character_id in current.entities:
            current.entities[character_id].state = "dead"
    
    def is_dead(self, character_id: str) -> bool:
        """Check if a character is dead."""
        character_id = sanitize_id(character_id)
        # Prefer EntityRegistry, fall back to persistent_dead
        if self._entity_registry.has_entity(character_id):
            return self._entity_registry.is_dead(character_id)
        return character_id in self.persistent_dead
        character_id = sanitize_id(character_id)
        return character_id in self.persistent_dead
    
    def set_emotion(self, character_id: str, emotion: str) -> None:
        """Set a character's emotional state."""
        character_id = sanitize_id(character_id)
        emotion = sanitize_id(emotion)
        self.persistent_emotions[character_id] = emotion
        
        # Update EntityRegistry
        self._entity_registry.set_emotion(character_id, emotion)
        
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].emotion = emotion
    
    def set_trait(self, character_id: str, trait: str) -> None:
        """Set a character's established trait."""
        character_id = sanitize_id(character_id)
        trait = sanitize_id(trait)
        self.persistent_traits[character_id] = trait
        
        # Update EntityRegistry
        self._entity_registry.add_trait(character_id, trait)
        
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].traits.add(trait)
    
    def log_event(self, event_data: Dict, chapter_num: int) -> str:
        """Log an event with global ID assignment."""
        event_id = self.get_next_global_event_id()
        
        self.event_log.append({
            'id': event_id,
            'type': event_data.get('type'),
            'agent': event_data.get('agent'),
            'patient': event_data.get('patient'),
            'location': event_data.get('location'),
            'source_text': event_data.get('source_text', ''),
            'chapter': chapter_num
        })
        
        return event_id
    
    def delta(self, from_time: int, to_time: int) -> StateDelta:
        """
        Compute the delta (changes) between two world states.
        
        Note: Historical states are not stored. This returns an empty delta
        unless from_time == to_time == current_time.
        
        Per LOGIC_DESIGN.md: delta(T-1, T)
        Historical delta analysis is handled by FinalAnalyzer.
        """
        return StateDelta(from_time=from_time, to_time=to_time)
    
    def compute_delta(self, from_time: int, to_time: int) -> StateDelta:
        """
        Compute the delta (changes) between two world states.
        
        Note: Historical states are not stored. Returns empty delta.
        Historical analysis is handled by FinalAnalyzer.
        """
        return StateDelta(from_time=from_time, to_time=to_time)
    
    def get_static_entity_facts(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get static entity declaration facts for Clingo.
        
        Memory optimization (Phase 8.2): Now delegates to EntityRegistry
        which provides set-like deduplication. Size is bounded by unique entity count.
        
        Phase 8.6: If active_universe is provided, only entities in that
        universe are included in the facts.
        
        Args:
            active_universe: Optional filter - only include entities in this universe.
        
        Returns:
            List of entity declaration facts like 'character(harry).'
        """
        return self._entity_registry.get_asp_facts(active_universe=active_universe)
    
    @property
    def accumulated_facts(self) -> List[str]:
        """
        Backward-compatible property that returns static entity facts.
        
        Memory optimization (Phase 8.1): This is now computed on-demand
        from persistent_entities instead of being accumulated.
        """
        return self.get_static_entity_facts()
    
    def get_cross_chapter_state_facts(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Get ASP facts for cross-chapter state.
        
        Includes: dead characters, previous emotions, established traits, relationships
        Uses EntityRegistry where available (Phase 8.2).
        
        Phase 8.6: If active_universe is provided, only facts involving entities
        in that universe are included.
        
        Args:
            active_universe: Optional filter - only include entities in this universe.
        """
        facts = []
        all_entities = active_universe.all_entities if active_universe else None
        asp_converter = _get_asp_converter()
        
        # Dead characters - from EntityRegistry
        facts.extend(self._entity_registry.get_dead_character_facts(active_universe=active_universe))
        
        # Previous emotions - filter by active universe
        for char, emotion in self.persistent_emotions.items():
            if all_entities is not None and char not in all_entities:
                continue
            facts.append(asp_converter.previous_emotion_to_asp(char, emotion))
        
        # Established traits - from EntityRegistry
        facts.extend(self._entity_registry.get_trait_facts(active_universe=active_universe))
        
        # Relationships - only include if BOTH characters are in active universe
        for (char1, char2), rel_type in self.persistent_relationships.items():
            if all_entities is not None:
                if char1 not in all_entities or char2 not in all_entities:
                    continue
            facts.extend(asp_converter.relationship_tuple_to_asp(char1, char2, rel_type))
        
        return facts
    
    def get_asp_facts_for_clingo(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Generate all ASP facts for the current state.
        
        Note: This is a convenience method that delegates to ToAspConverter.
        For new code, prefer using ToAspConverter directly.
        
        Args:
            active_universe: Optional filter - only include entities in this universe.
        """
        asp_converter = _get_asp_converter()
        
        lines = [
            f"% Generated by StateManager at time {self.current_time}",
            asp_converter.current_time_to_asp(self.current_time),
            "",
            "% Character aliases (for ASP-based resolution)",
            asp_converter.aliases_from_resolver_to_asp(self._alias_resolver, active_universe=active_universe),
            "",
        ]
        
        # Add current state facts (filtered by active universe)
        current = self.get_current_state()
        lines.append(asp_converter.world_state_to_asp(current, active_universe=active_universe))
        
        # Add cross-chapter state (filtered by active universe)
        cross_chapter = self.get_cross_chapter_state_facts(active_universe=active_universe)
        if cross_chapter:
            lines.append("\n% Cross-chapter state:")
            lines.extend(cross_chapter)
        
        # Add static entity facts (filtered by active universe)
        static_facts = self.get_static_entity_facts(active_universe=active_universe)
        if static_facts:
            lines.append("\n% Static entity declarations:")
            lines.extend(static_facts)
        
        return "\n".join(lines)
    
    def extract_state_from_facts(self, facts: str) -> None:
        """
        Extract and update cross-chapter state from ASP facts.
        
        Extracted from LogicEvaluator._accumulate_cross_chapter_state()
        """
        for line in facts.split('\n'):
            line = line.strip()
            
            # Track death events permanently
            if line.startswith('is_dead('):
                match = re.match(r'is_dead\(([^)]+)\)\.', line)
                if match:
                    self.persistent_dead.add(match.group(1))
            
            # Track current emotions
            if line.startswith('character_emotion('):
                match = re.match(r'character_emotion\(([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char, emotion = match.group(1), match.group(2)
                    self.persistent_emotions[char] = emotion
                    # Strong emotions become established traits
                    if emotion in ['nasty', 'kind', 'hostile', 'friendly', 'cruel', 'warm', 'cold']:
                        if char not in self.persistent_traits:
                            self.persistent_traits[char] = emotion
            
            # Track relationships
            if line.startswith('relationship('):
                match = re.match(r'relationship\(([^,]+),\s*([^,]+),\s*([^)]+)\)\.', line)
                if match:
                    char1, char2, rel_type = match.group(1), match.group(2), match.group(3)
                    self.persistent_relationships[(char1, char2)] = rel_type
    
    def end_chapter(self, chapter_num: int) -> Dict[str, int]:
        """
        End-of-chapter processing including lifecycle state updates.
        
        Must be called at the end of each chapter to update entity lifecycle
        states. This is the authoritative update point for lifecycle transitions.
        
        Phase 8.3: Entities transition between ACTIVE/LATENT/FROZEN based on
        how recently they acted.
        
        Args:
            chapter_num: The chapter number that just completed
            
        Returns:
            Dict with lifecycle counts: {"active": N, "latent": N, "frozen": N}
        """
        return self._entity_registry.update_lifecycle_states(chapter_num)
    
    def get_lifecycle_statistics(self) -> Dict[str, Any]:
        """
        Get entity lifecycle statistics.
        
        Returns:
            Dict with active/latent/frozen counts and total entities
        """
        return {
            "total": len(self._entity_registry._entities),
            "active": len(self._entity_registry.get_active_entities()),
            "latent": len(self._entity_registry.get_latent_entities()),
            "frozen": len(self._entity_registry.get_frozen_entities()),
        }
    
    def reset(self) -> None:
        """Reset all state for a new story."""
        self.current_time = 0
        self.current_state = WorldState(time=0)
        self._entity_registry.reset()  # Reset EntityRegistry
        self.persistent_entities = {}
        self.persistent_dead = set()
        self.persistent_relationships = {}
        self.persistent_emotions = {}
        self.persistent_traits = {}
        # Note: accumulated_facts is now a computed property, no need to reset
        self.next_event_id = 1
        self.event_log = []
    
    def reset_chapter(self, chapter_num: int = None) -> None:
        """
        Reset chapter-specific state while preserving cross-chapter state.
        
        Phase 8.3: Only ACTIVE entities are populated into WorldState.
        LATENT and FROZEN entities remain in EntityRegistry but are
        excluded from WorldState and ASP facts.
        
        Args:
            chapter_num: If provided, update lifecycle states first
        """
        self.current_time = 0
        
        # Update lifecycle states if chapter number provided
        if chapter_num is not None:
            self._entity_registry.update_lifecycle_states(chapter_num)
        
        # Create fresh state with only ACTIVE entities
        new_state = WorldState(time=0)
        
        # Only include ACTIVE entities in WorldState
        for reg_entity in self._entity_registry.get_active_entities():
            eid = reg_entity.canonical_id
            # Get from persistent_entities for backward compatibility
            if eid in self.persistent_entities:
                entity = self.persistent_entities[eid]
                new_state.entities[eid] = Entity(
                    id=entity.id,
                    entity_type=entity.entity_type,
                    traits=set(entity.traits),
                    state=entity.state,
                    emotion=entity.emotion,
                    aliases=list(entity.aliases),
                    relevance=entity.relevance,
                )
            else:
                # Create from registry if not in persistent_entities
                new_state.entities[eid] = Entity(
                    id=eid,
                    entity_type=reg_entity.entity_type.value,
                    traits=set(reg_entity.traits),
                    state=reg_entity.state,
                    emotion=reg_entity.emotion,
                    aliases=list(reg_entity.aliases),
                    relevance=reg_entity.relevance,
                )
        
        self.current_state = new_state
    
    # =========================================================================
    # Persistence Methods - Delegate to StateManagerPersistence
    # =========================================================================
    
    def to_json(self) -> Dict[str, Any]:
        """
        Serialize state manager to JSON-compatible dict.
        
        Note: For new code, prefer using StateManagerPersistence directly.
        """
        from .utils.state_manager_persistence import StateManagerPersistence
        return StateManagerPersistence(self).to_json()
    
    def save(self, path) -> None:
        """
        Save state to file.
        
        Note: For new code, prefer using StateManagerPersistence directly.
        """
        from .utils.state_manager_persistence import StateManagerPersistence
        StateManagerPersistence(self).save(path)
    
    def load(self, path) -> None:
        """
        Load state from file.
        
        Note: For new code, prefer using StateManagerPersistence directly.
        """
        from .utils.state_manager_persistence import StateManagerPersistence
        StateManagerPersistence(self).load(path)
    
    def save_to_persistent_context(self, context, chapter: int) -> None:
        """
        Save state to PersistentContext.
        
        Note: For new code, prefer using StateManagerPersistence directly.
        """
        from .utils.state_manager_persistence import StateManagerPersistence
        StateManagerPersistence(self).save_to_persistent_context(context, chapter)
    
    def load_from_persistent_context(self, context) -> None:
        """
        Load state from PersistentContext.
        
        Note: For new code, prefer using StateManagerPersistence directly.
        """
        from .utils.state_manager_persistence import StateManagerPersistence
        StateManagerPersistence(self).load_from_persistent_context(context)
