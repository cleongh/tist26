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

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any, TYPE_CHECKING
from pathlib import Path
import json
import re

from .entity_registry import EntityRegistry, EntityType, RegisteredEntity

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult


@dataclass
class Entity:
    """Represents an entity in the Logic Knowledge Graph."""
    id: str
    entity_type: str  # 'character', 'location', 'item'
    traits: Set[str] = field(default_factory=set)
    state: str = "alive"  # 'alive', 'dead', etc.
    emotion: Optional[str] = None
    # Phase 1: New optional fields for enhanced extraction
    aliases: List[str] = field(default_factory=list)  # Character aliases (e.g., ["Uncle Vernon", "Mr. Dursley"])
    relevance: Optional[str] = None  # Item relevance: "causal" | "latent" (for Chekhov tracking)


@dataclass
class Relation:
    """Represents a time-indexed relation in the LKG."""
    predicate: str  # 'relationship', 'present', 'carries', 'connected'
    args: Tuple[str, ...]
    time: int
    source_event: Optional[str] = None


@dataclass
class StoryRule:
    """
    A story-specific rule that can modify/override universal rules.
    
    Types: relationship, trait, location, possession, temporal
    """
    rule_type: str  # 'relationship', 'trait', 'location', 'possession', 'temporal'
    subject: str
    predicate: str
    object: Optional[str] = None
    established_by: str = "e0"  # Event ID that established this rule
    valid: bool = True


@dataclass
class WorldState:
    """
    Snapshot of the world state at a specific timestep.
    
    Contains all entities, relations, and derived facts valid at time T.
    """
    time: int
    entities: Dict[str, Entity] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
    story_rules: List[StoryRule] = field(default_factory=list)
    
    def to_asp_facts(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Convert world state to ASP fact format.
        
        Phase 8.6: If active_universe is provided, only facts for entities
        in that universe are included.
        
        Args:
            active_universe: Optional filter - only include entities in this universe.
        """
        lines = [f"% World state at time {self.time}"]
        all_entities = active_universe.all_entities if active_universe else None
        
        # Entity facts
        for entity_id, entity in self.entities.items():
            # Skip entities not in active universe
            if all_entities is not None and entity_id not in all_entities:
                continue
            lines.append(f"{entity.entity_type}({entity_id}).")
            for trait in entity.traits:
                lines.append(f"trait({entity_id}, {trait}).")
            if entity.state == "dead":
                lines.append(f"is_dead({entity_id}).")
            if entity.emotion:
                lines.append(f"character_emotion({entity_id}, {entity.emotion}).")
        
        # Relation facts (time-indexed) - filter by active universe
        for rel in self.relations:
            if rel.time == self.time:
                # Check if all entity args are in active universe
                if all_entities is not None:
                    # Filter relation if any entity arg is not in universe
                    skip = False
                    for arg in rel.args:
                        # Skip numeric args (times, quantities)
                        if arg.isdigit():
                            continue
                        if arg not in all_entities:
                            skip = True
                            break
                    if skip:
                        continue
                args_str = ", ".join(rel.args)
                lines.append(f"{rel.predicate}({args_str}, {rel.time}).")
        
        # Story rules
        for rule in self.story_rules:
            if rule.valid:
                # Filter by active universe
                if all_entities is not None:
                    if rule.subject not in all_entities:
                        continue
                    if rule.object and rule.object not in all_entities:
                        continue
                lines.append(self._rule_to_asp(rule))
        
        # Derived facts - filter by active universe
        for fact in self.derived_facts:
            if all_entities is not None:
                # Simple heuristic: check if any known entity appears in fact
                # Skip facts that reference entities not in universe
                skip = False
                for entity_id in all_entities:
                    # If we can't determine, include it
                    pass
                # For now, include derived facts (they're typically small)
            lines.append(fact)
        
        return "\n".join(lines)
    
    def _rule_to_asp(self, rule: StoryRule) -> str:
        """Convert a story rule to ASP fact."""
        if rule.rule_type == 'relationship':
            return f"relationship_rule({rule.subject}, {rule.predicate}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'trait':
            return f"trait_rule({rule.subject}, {rule.predicate}, {rule.established_by})."
        elif rule.rule_type == 'location':
            return f"location_rule({rule.subject}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'possession':
            return f"possession_rule({rule.subject}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'temporal':
            return f"temporal_rule({rule.subject}, must_precede, {rule.object}, {rule.established_by})."
        return ""
    
    def update_time(self, new_time: int) -> None:
        """Update the time index without cloning."""
        self.time = new_time


@dataclass
class StateDelta:
    """
    Represents changes between two world states.
    
    Used for tracking what changed due to an event.
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
    
    @staticmethod
    def _sanitize_id(value: Any) -> str:
        """Sanitize a value for use as an ASP atom."""
        if not value:
            return "unknown"
        s = str(value).lower()
        s = re.sub(r'[^a-z0-9_]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if s and s[0].isdigit():
            s = 'n' + s
        return s or "unknown"
    
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
    
    def get_next_event_id(self) -> str:
        """Get the next global event ID and increment counter."""
        event_id = f"e{self.next_event_id}"
        self.next_event_id += 1
        return event_id
    
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
        char1 = self._sanitize_id(char1)
        char2 = self._sanitize_id(char2)
        rel_type = self._sanitize_id(rel_type)
        
        self.persistent_relationships[(char1, char2)] = rel_type
        self.add_relation("relationship", (char1, char2, rel_type), source_event)
    
    def add_story_rule(self, rule_type: str, subject: str, predicate: str,
                       obj: str = None, established_by: str = "e0") -> StoryRule:
        """Add a story-specific rule to the current state."""
        rule = StoryRule(
            rule_type=rule_type,
            subject=self._sanitize_id(subject),
            predicate=self._sanitize_id(predicate),
            object=self._sanitize_id(obj) if obj else None,
            established_by=established_by,
            valid=True
        )
        
        current = self.get_current_state()
        current.story_rules.append(rule)
        
        return rule
    
    def invalidate_rule(self, subject: str, obj: str, event_id: str) -> bool:
        """Invalidate an existing rule (when relationships change)."""
        subject = self._sanitize_id(subject)
        obj = self._sanitize_id(obj) if obj else None
        
        current = self.get_current_state()
        for rule in current.story_rules:
            if rule.subject == subject and rule.object == obj and rule.valid:
                rule.valid = False
                return True
        return False
    
    def mark_dead(self, character_id: str) -> None:
        """Mark a character as permanently dead."""
        character_id = self._sanitize_id(character_id)
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
        character_id = self._sanitize_id(character_id)
        # Prefer EntityRegistry, fall back to persistent_dead
        if self._entity_registry.has_entity(character_id):
            return self._entity_registry.is_dead(character_id)
        return character_id in self.persistent_dead
        character_id = self._sanitize_id(character_id)
        return character_id in self.persistent_dead
    
    def set_emotion(self, character_id: str, emotion: str) -> None:
        """Set a character's emotional state."""
        character_id = self._sanitize_id(character_id)
        emotion = self._sanitize_id(emotion)
        self.persistent_emotions[character_id] = emotion
        
        # Update EntityRegistry
        self._entity_registry.set_emotion(character_id, emotion)
        
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].emotion = emotion
    
    def set_trait(self, character_id: str, trait: str) -> None:
        """Set a character's established trait."""
        character_id = self._sanitize_id(character_id)
        trait = self._sanitize_id(trait)
        self.persistent_traits[character_id] = trait
        
        # Update EntityRegistry
        self._entity_registry.add_trait(character_id, trait)
        
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].traits.add(trait)
    
    def log_event(self, event_data: Dict, chapter_num: int) -> str:
        """Log an event with global ID assignment."""
        event_id = self.get_next_event_id()
        
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
        
        # Dead characters - from EntityRegistry
        facts.extend(self._entity_registry.get_dead_character_facts(active_universe=active_universe))
        
        # Previous emotions - filter by active universe
        for char, emotion in self.persistent_emotions.items():
            if all_entities is not None and char not in all_entities:
                continue
            facts.append(f"previous_emotion({char}, {emotion}).")
        
        # Established traits - from EntityRegistry
        facts.extend(self._entity_registry.get_trait_facts(active_universe=active_universe))
        
        # Relationships - only include if BOTH characters are in active universe
        for (char1, char2), rel_type in self.persistent_relationships.items():
            if all_entities is not None:
                if char1 not in all_entities or char2 not in all_entities:
                    continue
            facts.append(f"previous_relationship({char1}, {char2}, {rel_type}).")
            # Also generate initial_relationship for EC to derive relationship/4
            facts.append(f"initial_relationship({char1}, {char2}, {rel_type}).")
        
        return facts
    
    def get_asp_facts_for_clingo(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Generate all ASP facts for the current state.
        
        Includes:
            - Character alias facts (for ASP-based alias resolution)
            - Current world state facts
            - Persistent dead character facts
            - Cross-chapter state
            - Time declaration
            
        Phase 8.6: If active_universe is provided, only facts for entities
        in that universe are included, reducing ASP grounding time.
        
        Args:
            active_universe: Optional filter - only include entities in this universe.
        """
        # Import here to avoid circular import
        from .event_executor import generate_alias_facts
        
        lines = [
            f"% Generated by StateManager at time {self.current_time}",
            f"current_time({self.current_time}).",
            "",
            "% Character aliases (for ASP-based resolution)",
            generate_alias_facts(self._alias_resolver, active_universe=active_universe),
            "",
        ]
        
        # Add current state facts (filtered by active universe)
        current = self.get_current_state()
        lines.append(current.to_asp_facts(active_universe=active_universe))
        
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
    
    def accumulate_persistent_facts(self, facts: str) -> None:
        """
        Legacy method - now a no-op.
        
        Memory optimization (Phase 8.1): Entity facts are now derived on-demand
        from persistent_entities (populated via add_entity). No accumulation needed.
        
        This method is kept for backward compatibility but does nothing.
        Entity registration happens via add_entity() which updates persistent_entities.
        """
        # No-op: facts are derived from persistent_entities, not accumulated
        pass
    
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
    
    def to_json(self) -> Dict[str, Any]:
        """Serialize state manager to JSON-compatible dict."""
        return {
            "current_time": self.current_time,
            "next_event_id": self.next_event_id,
            "persistent_dead": list(self.persistent_dead),
            "persistent_emotions": self.persistent_emotions,
            "persistent_traits": self.persistent_traits,
            "persistent_relationships": {
                f"{k[0]},{k[1]}": v 
                for k, v in self.persistent_relationships.items()
            },
            "persistent_entities": {
                eid: {
                    "id": e.id,
                    "type": e.entity_type,
                    "traits": list(e.traits),
                    "state": e.state,
                    "emotion": e.emotion
                }
                for eid, e in self.persistent_entities.items()
            },
            # EntityRegistry state (Phase 8.2)
            "entity_registry": self._entity_registry.to_dict(),
            # Note: accumulated_facts now derived from _entity_registry, 
            # kept in JSON for backward compatibility
            "accumulated_facts": self.accumulated_facts,
            "event_log": self.event_log,
        }
    
    def save(self, path: Path) -> None:
        """Save state to file."""
        with open(path, 'w') as f:
            json.dump(self.to_json(), f, indent=2)
    
    def load(self, path: Path) -> None:
        """Load state from file."""
        with open(path) as f:
            data = json.load(f)
        
        self.current_time = data.get("current_time", 0)
        self.next_event_id = data.get("next_event_id", 1)
        self.persistent_dead = set(data.get("persistent_dead", []))
        self.persistent_emotions = data.get("persistent_emotions", {})
        self.persistent_traits = data.get("persistent_traits", {})
        
        self.persistent_relationships = {}
        for key, val in data.get("persistent_relationships", {}).items():
            parts = key.split(",")
            if len(parts) == 2:
                self.persistent_relationships[(parts[0], parts[1])] = val
        
        self.persistent_entities = {}
        for eid, edata in data.get("persistent_entities", {}).items():
            self.persistent_entities[eid] = Entity(
                id=edata["id"],
                entity_type=edata["type"],
                traits=set(edata.get("traits", [])),
                state=edata.get("state", "alive"),
                emotion=edata.get("emotion")
            )
        
        # Load EntityRegistry state (Phase 8.2)
        if "entity_registry" in data:
            self._entity_registry.load_from_dict(data["entity_registry"])
        else:
            # Backward compatibility: Reconstruct registry from persistent_entities
            self._entity_registry.reset()
            type_map = {
                'character': EntityType.CHARACTER,
                'location': EntityType.LOCATION,
                'item': EntityType.ITEM,
            }
            for eid, entity in self.persistent_entities.items():
                registry_type = type_map.get(entity.entity_type, EntityType.CHARACTER)
                self._entity_registry.register_entity(
                    canonical_id=eid,
                    entity_type=registry_type,
                    aliases=entity.aliases,
                    state=entity.state,
                    traits=list(entity.traits),
                    emotion=entity.emotion,
                )
            # Restore dead state
            for char in self.persistent_dead:
                self._entity_registry.mark_dead(char)
        
        # Note: accumulated_facts in JSON is ignored on load - derived from _entity_registry
        self.event_log = data.get("event_log", [])
    
    # =========================================================================
    # Context Persistence Integration (Phase 8.4)
    # =========================================================================
    
    def save_to_persistent_context(self, context, chapter: int) -> None:
        """
        Save state to PersistentContext.
        
        This is the primary method for incremental context updates.
        Called at the end of each chapter.
        
        Args:
            context: PersistentContext instance
            chapter: Chapter number just processed
        """
        context.update_from_state_manager(self, chapter)
    
    def load_from_persistent_context(self, context) -> None:
        """
        Load state from PersistentContext.
        
        Used when resuming from a saved context.
        
        Args:
            context: PersistentContext instance (must be loaded)
        """
        context.apply_to_state_manager(self)
