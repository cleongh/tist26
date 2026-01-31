"""
State Manager - World State Snapshots & Deltas

Responsibilities:
    - Maintain the Logic Knowledge Graph (LKG) state
    - Create world state snapshots at each timestep
    - Compute deltas between timesteps
    - Track entities, relations, and derived facts

Per LOGIC_DESIGN.md Section 3.2:
    Entities: character(X), location(X), item(X)
    Relations: relationship(C1, C2, Type, T), present(E, L, T), carries(C, I, T)
    Derived: item presence via carrying

Per LOGIC_DESIGN.md Section 3.3 (Global Constraints):
    - Non-ubiquity: entity cannot be in multiple locations at same time
    - Linear time: discrete, monotonic, strictly ordered
    - No branching timelines

Phase 3 Refactoring (Step 3.1):
    - Extract accumulated_facts, dead_characters, relationships from LogicEvaluator
    - Implement world state snapshots: snapshot(T)
    - Implement delta computation: delta(T-1, T)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
import json
import copy
import re


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
    
    def to_asp_facts(self) -> str:
        """Convert world state to ASP fact format."""
        lines = [f"% World state at time {self.time}"]
        
        # Entity facts
        for entity_id, entity in self.entities.items():
            lines.append(f"{entity.entity_type}({entity_id}).")
            for trait in entity.traits:
                lines.append(f"trait({entity_id}, {trait}).")
            if entity.state == "dead":
                lines.append(f"is_dead({entity_id}).")
            if entity.emotion:
                lines.append(f"character_emotion({entity_id}, {entity.emotion}).")
        
        # Relation facts (time-indexed)
        for rel in self.relations:
            if rel.time == self.time:
                args_str = ", ".join(rel.args)
                lines.append(f"{rel.predicate}({args_str}, {rel.time}).")
        
        # Story rules
        for rule in self.story_rules:
            if rule.valid:
                lines.append(self._rule_to_asp(rule))
        
        # Derived facts
        for fact in self.derived_facts:
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
    
    def clone(self) -> 'WorldState':
        """Create a deep copy of this world state."""
        return WorldState(
            time=self.time,
            entities=copy.deepcopy(self.entities),
            relations=copy.deepcopy(self.relations),
            derived_facts=copy.deepcopy(self.derived_facts),
            story_rules=copy.deepcopy(self.story_rules),
        )


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
    Manages world state across the story timeline.
    
    Provides:
        - State snapshots at each timestep
        - Delta computation between states
        - Entity and relation tracking
        - Persistence of state history
        - Cross-chapter state management (Step 3.1)
    
    Does NOT:
        - Encode story logic (delegated to ASP)
        - Make reasoning decisions
        - Interpret violations
    
    Extracted from LogicEvaluator (Phase 3, Step 3.1):
        - accumulated_facts → persistent_entities, persistent_facts
        - dead_characters → persistent_dead
        - relationships → persistent_relationships
        - character_emotions → persistent_emotions
        - established_traits → persistent_traits
        - story_rules → story_rules in WorldState
    """
    
    def __init__(self):
        self.current_time: int = 0
        self.states: Dict[int, WorldState] = {}
        self.states[0] = WorldState(time=0)
        
        # Cross-chapter persistent state (extracted from LogicEvaluator)
        self.persistent_entities: Dict[str, Entity] = {}
        self.persistent_dead: Set[str] = set()  # Characters confirmed dead
        self.persistent_relationships: Dict[Tuple[str, str], str] = {}  # (char1, char2) -> rel_type
        self.persistent_emotions: Dict[str, str] = {}  # char -> emotion
        self.persistent_traits: Dict[str, str] = {}  # char -> trait
        
        # Accumulated facts for Clingo (from LogicEvaluator.accumulated_facts)
        self.accumulated_facts: List[str] = []
        
        # Global event tracking (continuous across chapters)
        self.next_event_id: int = 1  # Start from 1, e0 reserved for initial state
        self.event_log: List[Dict] = []  # [{id, type, agent, patient, location, source_text, chapter}]
    
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
        return self.states.get(self.current_time, WorldState(time=self.current_time))
    
    def get_state_at(self, time: int) -> Optional[WorldState]:
        """Get world state at a specific timestep."""
        return self.states.get(time)
    
    def snapshot(self, time: int = None) -> WorldState:
        """
        Create a snapshot of the world state at the given time.
        
        Per LOGIC_DESIGN.md: snapshot(T) returning current LKG
        """
        t = time if time is not None else self.current_time
        state = self.get_state_at(t)
        if state:
            return state.clone()
        return WorldState(time=t)
    
    def advance_time(self) -> int:
        """
        Advance to next timestep.
        
        Creates a new world state based on the current one,
        carrying forward persistent facts.
        """
        self.current_time += 1
        
        # Clone current state as base for new timestep
        if self.current_time - 1 in self.states:
            new_state = self.states[self.current_time - 1].clone()
            new_state.time = self.current_time
        else:
            new_state = WorldState(time=self.current_time)
        
        self.states[self.current_time] = new_state
        return self.current_time
    
    def get_next_event_id(self) -> str:
        """Get the next global event ID and increment counter."""
        event_id = f"e{self.next_event_id}"
        self.next_event_id += 1
        return event_id
    
    def add_entity(self, entity_id: str, entity_type: str, 
                   traits: Set[str] = None, state: str = "alive",
                   emotion: str = None, aliases: List[str] = None,
                   relevance: str = None) -> Entity:
        """Add an entity to the current world state."""
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
        
        # Also add to persistent entities
        self.persistent_entities[entity_id] = entity
        
        # Track in accumulated facts for Clingo
        fact = f"{entity_type}({entity_id})."
        if fact not in self.accumulated_facts:
            self.accumulated_facts.append(fact)
        
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
        
        # Update entity state
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].state = "dead"
        
        current = self.get_current_state()
        if character_id in current.entities:
            current.entities[character_id].state = "dead"
    
    def is_dead(self, character_id: str) -> bool:
        """Check if a character is dead."""
        character_id = self._sanitize_id(character_id)
        return character_id in self.persistent_dead
    
    def set_emotion(self, character_id: str, emotion: str) -> None:
        """Set a character's emotional state."""
        character_id = self._sanitize_id(character_id)
        emotion = self._sanitize_id(emotion)
        self.persistent_emotions[character_id] = emotion
        
        if character_id in self.persistent_entities:
            self.persistent_entities[character_id].emotion = emotion
    
    def set_trait(self, character_id: str, trait: str) -> None:
        """Set a character's established trait."""
        character_id = self._sanitize_id(character_id)
        trait = self._sanitize_id(trait)
        self.persistent_traits[character_id] = trait
        
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
        
        Per LOGIC_DESIGN.md: delta(T-1, T)
        Returns what was added/removed between the two timesteps.
        """
        return self.compute_delta(from_time, to_time)
    
    def compute_delta(self, from_time: int, to_time: int) -> StateDelta:
        """
        Compute the delta (changes) between two world states.
        
        Returns what was added/removed between the two timesteps.
        """
        from_state = self.get_state_at(from_time)
        to_state = self.get_state_at(to_time)
        
        if not from_state or not to_state:
            return StateDelta(from_time=from_time, to_time=to_time)
        
        delta = StateDelta(from_time=from_time, to_time=to_time)
        
        # Find added/removed entities
        from_ids = set(from_state.entities.keys())
        to_ids = set(to_state.entities.keys())
        
        for eid in to_ids - from_ids:
            delta.added_entities.append(to_state.entities[eid])
        
        delta.removed_entities = list(from_ids - to_ids)
        
        # Find added/removed relations (compare by predicate+args, ignore time)
        from_rels = {(r.predicate, r.args) for r in from_state.relations}
        to_rels = {(r.predicate, r.args) for r in to_state.relations}
        
        for rel in to_state.relations:
            if (rel.predicate, rel.args) not in from_rels:
                delta.added_relations.append(rel)
        
        for rel in from_state.relations:
            if (rel.predicate, rel.args) not in to_rels:
                delta.removed_relations.append(rel)
        
        # Find added/removed derived facts
        from_derived = set(from_state.derived_facts)
        to_derived = set(to_state.derived_facts)
        
        delta.added_derived = list(to_derived - from_derived)
        delta.removed_derived = list(from_derived - to_derived)
        
        # Find added/invalidated story rules
        from_rules = {(r.rule_type, r.subject, r.object) for r in from_state.story_rules if r.valid}
        to_rules = {(r.rule_type, r.subject, r.object) for r in to_state.story_rules if r.valid}
        
        for rule in to_state.story_rules:
            if rule.valid and (rule.rule_type, rule.subject, rule.object) not in from_rules:
                delta.added_rules.append(rule)
        
        for rule in from_state.story_rules:
            if rule.valid and (rule.rule_type, rule.subject, rule.object) not in to_rules:
                delta.invalidated_rules.append(rule)
        
        return delta
    
    def get_cross_chapter_state_facts(self) -> List[str]:
        """
        Get ASP facts for cross-chapter state.
        
        Includes: dead characters, previous emotions, established traits, relationships
        """
        facts = []
        
        # Dead characters
        for char in self.persistent_dead:
            facts.append(f"is_dead({char}).")
        
        # Previous emotions
        for char, emotion in self.persistent_emotions.items():
            facts.append(f"previous_emotion({char}, {emotion}).")
        
        # Established traits
        for char, trait in self.persistent_traits.items():
            facts.append(f"established_trait({char}, {trait}).")
        
        # Relationships
        for (char1, char2), rel_type in self.persistent_relationships.items():
            facts.append(f"previous_relationship({char1}, {char2}, {rel_type}).")
        
        return facts
    
    def get_asp_facts_for_clingo(self) -> str:
        """
        Generate all ASP facts for the current state.
        
        Includes:
            - Character alias facts (for ASP-based alias resolution)
            - Current world state facts
            - Persistent dead character facts
            - Cross-chapter state
            - Time declaration
        """
        # Import here to avoid circular import
        from .event_executor import generate_alias_facts
        
        lines = [
            f"% Generated by StateManager at time {self.current_time}",
            f"current_time({self.current_time}).",
            "",
            "% Character aliases (for ASP-based resolution)",
            generate_alias_facts(),
            "",
        ]
        
        # Add current state facts
        current = self.get_current_state()
        lines.append(current.to_asp_facts())
        
        # Add cross-chapter state
        cross_chapter = self.get_cross_chapter_state_facts()
        if cross_chapter:
            lines.append("\n% Cross-chapter state:")
            lines.extend(cross_chapter)
        
        # Add accumulated persistent facts (entities only, not events)
        if self.accumulated_facts:
            lines.append("\n% Previously introduced entities:")
            lines.extend(self.accumulated_facts)
        
        return "\n".join(lines)
    
    def accumulate_persistent_facts(self, facts: str) -> None:
        """
        Accumulate only PERSISTENT facts that should carry across chapters.
        
        Extracted from LogicEvaluator._accumulate_persistent_facts()
        
        Persistent facts include:
        - character(X) - Once a character exists, they remain in the story world
        - location_entity(X) - Once a location is introduced, it exists
        
        NOT persisted (chapter-specific):
        - event(X) - Events happen in specific chapters, should not be re-evaluated
        - agent(X, Y), patient(X, Y), location(X, Y) - Event-related facts
        """
        for line in facts.split('\n'):
            line = line.strip()
            if not line or line.startswith('%'):
                continue
            
            # Only persist structural facts, NOT events
            if line.startswith('character(') or line.startswith('location_entity('):
                if line not in self.accumulated_facts:
                    self.accumulated_facts.append(line)
    
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
    
    def reset(self) -> None:
        """Reset all state for a new story."""
        self.current_time = 0
        self.states = {0: WorldState(time=0)}
        self.persistent_entities = {}
        self.persistent_dead = set()
        self.persistent_relationships = {}
        self.persistent_emotions = {}
        self.persistent_traits = {}
        self.accumulated_facts = []
        self.next_event_id = 1
        self.event_log = []
    
    def reset_chapter(self) -> None:
        """Reset chapter-specific state while preserving cross-chapter state."""
        self.current_time = 0
        
        # Create fresh state but keep persistent entities
        new_state = WorldState(time=0)
        new_state.entities = copy.deepcopy(self.persistent_entities)
        self.states = {0: new_state}
    
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
        
        self.accumulated_facts = data.get("accumulated_facts", [])
        self.event_log = data.get("event_log", [])
