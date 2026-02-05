"""
ASP Converter - Unified converter for transforming data to ASP predicates.

This class consolidates all ASP fact/rule generation functionality:
- JSON chapter data → ASP facts
- EntityRegistry → ASP facts  
- WorldState → ASP facts
- StoryRules → ASP facts
- Events → ASP facts
- Relationships → ASP facts
- Time scopes → ASP facts
- ILASP directives → ILASP format
- Rule assembly → ASP program strings

Per LOGIC_DESIGN.md: Python is orchestration only, all logic in ASP.
This class handles conversion of data structures to ASP facts
that can be processed by the Clingo solver.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from ..domain import (
    EntityType,
    RegisteredEntity,
    ItemRelevance,
    TrackedItem,
    DerivedTransition,
    Relationship,
    TimeScope,
)
from ..config.rule_manager_config import ENTITY_PATTERNS, RESERVED_WORDS
from ..utils.sanitation import sanitize_id, sanitize_character_id

if TYPE_CHECKING:
    from ..registries import EntityRegistry, LifecycleRegistry
    from ..active_universe import ActiveUniverseResult
    from ..domain import WorldState, StoryRule, MovementContinuityResult, Event
    from ..state_manager import StateManager
    from ..resolvers import AliasResolver

logger = logging.getLogger(__name__)


class AspConverter:
    """
    Unified converter for transforming various data structures to ASP predicates.
    
    This class centralizes all ASP fact/rule generation to ensure consistency
    and single responsibility for ASP formatting.
    
    Phase 8.8: Supports active_universe filtering to prevent ASP grounding
    explosion by limiting entity declarations.
    
    Usage:
        converter = AspConverter()
        
        # Convert events
        event_facts = converter.event_to_asp(event)
        
        # Convert entities
        entity_facts = converter.entity_to_asp(entity)
        
        # Convert world state
        state_facts = converter.world_state_to_asp(state)
    """
    
    def __init__(
        self,
        alias_resolver: Optional['AliasResolver'] = None,
    ):
        """
        Initialize the ASP converter.
        
        Args:
            alias_resolver: Optional AliasResolver for character normalization
        """
        self._alias_resolver = alias_resolver
    
    # =========================================================================
    # EVENT CONVERSION
    # =========================================================================
    
    def event_to_asp(self, event: 'Event') -> List[str]:
        """
        Convert an Event object to ASP facts.
        
        Generates predicates:
            - event/1
            - event_type/2
            - event_time/2
            - agent/2
            - patient/2
            - location/2
            - event_destination/2
            - event_emotion/2
            - event_source/2
        
        Args:
            event: Event domain object
            
        Returns:
            List of ASP fact strings
        """
        facts = [
            f"event({event.id}).",
            f"event_type({event.id}, {event.event_type}).",
            f"event_time({event.id}, {event.time}).",
        ]
        
        if event.agent:
            facts.append(f"agent({event.id}, {event.agent}).")
        if event.patient:
            facts.append(f"patient({event.id}, {event.patient}).")
        if event.location:
            facts.append(f"location({event.id}, {event.location}).")
        if event.destination:
            facts.append(f"event_destination({event.id}, {event.destination}).")
        if event.emotion:
            facts.append(f"event_emotion({event.id}, {event.emotion}).")
        if event.source_text:
            escaped = event.source_text.replace('"', '\\"').replace('\n', ' ')[:80]
            facts.append(f'event_source({event.id}, "{escaped}").')
        
        return facts
    
    def event_dict_to_asp(
        self,
        event: Dict[str, Any],
        chapter_num: int,
        event_index: int,
    ) -> List[str]:
        """
        Convert an event dictionary (from JSON) to ASP facts.
        
        Args:
            event: Event dict from JSON chapter data
            chapter_num: Current chapter number
            event_index: Index of event in chapter
            
        Returns:
            List of ASP fact strings
        """
        eid = sanitize_id(event.get("global_id", event.get("id", f"e{chapter_num}_{event_index+1}")))
        etype = sanitize_id(event.get("type", "action"))
        
        facts = [
            f"event({eid}).",
            f"event_type({eid}, {etype}).",
            f"event_global({eid}, {etype}, {chapter_num}).",
        ]
        
        # Event order and time
        if eid.startswith('e') and eid[1:].isdigit():
            event_num = int(eid[1:])
            facts.append(f"event_order({eid}, {event_num}).")
            facts.append(f"event_time({eid}, {event_num}).")
            facts.append(f"time({event_num}).")
        
        # Event source text
        source_text = event.get('source_text', '')
        if source_text:
            escaped_source = source_text.replace('"', '\\"').replace('\n', ' ')[:80]
            facts.append(f'event_source({eid}, "{escaped_source}").')
        
        # Agent
        if event.get("agent"):
            agent_id = sanitize_character_id(event['agent'], self._alias_resolver)
            facts.append(f"agent({eid}, {agent_id}).")
        
        # Patient
        if event.get("patient"):
            patient_id = sanitize_id(event['patient'])
            facts.append(f"patient({eid}, {patient_id}).")
            if etype == "death":
                facts.append(f"is_dead({patient_id}).")
        
        # Location
        if event.get("location"):
            loc_id = sanitize_id(event['location'])
            facts.append(f"location({eid}, {loc_id}).")
        
        # Event emotion
        event_emotion = sanitize_id(event.get("emotion", ""))
        if event_emotion and event_emotion != "unknown":
            facts.append(f"event_emotion({eid}, {event_emotion}).")
        
        # Social action type
        social_action_type = sanitize_id(event.get("social_action_type", ""))
        if social_action_type and social_action_type != "unknown":
            facts.append(f"social_action({eid}, {social_action_type}).")
        
        # Temporal ordering
        after_event = sanitize_id(event.get("after", ""))
        if after_event and after_event not in ("unknown", "null"):
            facts.append(f"must_precede({after_event}, {eid}).")
        
        return facts
    
    def derived_transition_to_asp(self, transition: DerivedTransition) -> List[str]:
        """
        Convert a DerivedTransition to ASP facts.
        
        Generates predicates:
            - event/1
            - event_type/2
            - agent/2
            - location/2
            - derived_event/1
            - implicit_transition/5
        
        Args:
            transition: DerivedTransition domain object
            
        Returns:
            List of ASP fact strings
        """
        return [
            f"% Derived transition: {transition.agent} leaves {transition.from_location} for {transition.to_location}",
            f"event({transition.derived_event_id}).",
            f"event_type({transition.derived_event_id}, implicit_leave).",
            f"agent({transition.derived_event_id}, {transition.agent}).",
            f"location({transition.derived_event_id}, {transition.from_location}).",
            f"derived_event({transition.derived_event_id}).",
            f"implicit_transition({transition.agent}, {transition.from_location}, {transition.to_location}, {transition.after_event_id}, {transition.before_event_id}).",
        ]
    
    def transitions_to_asp(self, result: 'MovementContinuityResult') -> str:
        """
        Generate ASP facts for all derived transitions.
        
        Args:
            result: MovementContinuityResult from movement analysis
            
        Returns:
            ASP facts as a string
        """
        if not result.derived_transitions:
            return ""
        
        lines = [
            "",
            "% =============================================================================",
            "% DERIVED MOVEMENT TRANSITIONS (from MovementResolver)",
            "% These facts bridge implicit movement gaps in the narrative.",
            "% They are marked with derived_event/1 for auditing.",
            "% =============================================================================",
            "",
        ]
        
        for transition in result.derived_transitions:
            lines.extend(self.derived_transition_to_asp(transition))
            lines.append("")
        
        return "\n".join(lines)
    
    # =========================================================================
    # ENTITY CONVERSION
    # =========================================================================
    
    def entity_to_asp(self, entity: RegisteredEntity) -> str:
        """
        Generate ASP entity declaration fact.
        
        Args:
            entity: RegisteredEntity domain object
            
        Returns:
            ASP fact string like "character(harry)."
        """
        return f"{entity.entity_type.value}({entity.canonical_id})."
    
    def character_to_asp(self, char_id: str) -> str:
        """Generate character declaration fact."""
        return f"character({char_id})."
    
    def item_to_asp(self, item_id: str) -> str:
        """Generate item declaration fact."""
        return f"item({item_id})."
    
    def location_to_asp(self, loc_id: str) -> str:
        """Generate location declaration fact."""
        return f"location_entity({loc_id})."
    
    def trait_to_asp(self, entity_id: str, trait: str) -> str:
        """Generate trait fact."""
        return f"trait({entity_id}, {trait})."
    
    def is_dead_to_asp(self, entity_id: str) -> str:
        """Generate is_dead fact."""
        return f"is_dead({entity_id})."
    
    def emotion_to_asp(self, entity_id: str, emotion: str) -> str:
        """Generate character_emotion fact."""
        return f"character_emotion({entity_id}, {emotion})."
    
    def alias_to_asp(self, alias: str, canonical: str) -> str:
        """Generate alias fact."""
        return f"alias({alias}, {canonical})."
    
    def tracked_item_to_asp(
        self,
        item: TrackedItem,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Generate ASP facts for a tracked item.
        
        Args:
            item: TrackedItem domain object
            active_universe: Optional filter
            
        Returns:
            List of ASP fact strings
        """
        if item.suppressed:
            return []
        
        all_entities = active_universe.all_entities if active_universe else None
        if all_entities is not None and item.item_id not in all_entities:
            return []
        
        facts = [
            f"item({item.item_id}).",
            f"item_relevance({item.item_id}, {item.relevance.value}).",
            f"item_lifecycle({item.item_id}, {item.lifecycle_state.value}).",
        ]
        
        if item.carrier:
            if all_entities is None or item.carrier in all_entities:
                facts.append(f"carries({item.carrier}, {item.item_id}).")
        
        if item.relevance == ItemRelevance.LATENT:
            facts.append(f"latent_item({item.item_id}).")
        
        return facts
    
    def tracked_items_to_asp(
        self,
        items: Dict[str, TrackedItem],
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Generate ASP facts for multiple tracked items.
        
        Args:
            items: Dict mapping item_id to TrackedItem
            active_universe: Optional filter
            
        Returns:
            List of ASP fact strings
        """
        facts = []
        for item in items.values():
            facts.extend(self.tracked_item_to_asp(item, active_universe))
        return facts
    
    # =========================================================================
    # RELATIONSHIP CONVERSION
    # =========================================================================
    
    def relationship_to_asp(self, rel: Relationship) -> str:
        """Generate relationship/3 fact."""
        return f"relationship({rel.source}, {rel.target}, {rel.rel_type})."
    
    def initial_relationship_to_asp(self, rel: Relationship) -> str:
        """Generate initial_relationship fact for EC framework."""
        return f"initial_relationship({rel.source}, {rel.target}, {rel.rel_type})."
    
    def previous_relationship_to_asp(self, rel: Relationship) -> str:
        """Generate previous_relationship fact for cross-chapter continuity."""
        return f"previous_relationship({rel.source}, {rel.target}, {rel.rel_type})."
    
    def relationships_to_asp(
        self,
        relationships: List[Relationship],
        include_initial: bool = True,
        include_previous: bool = True,
        include_current: bool = False,
    ) -> List[str]:
        """
        Convert Relationship objects to ASP facts.
        
        Args:
            relationships: List of Relationship objects
            include_initial: If True, include initial_relationship facts
            include_previous: If True, include previous_relationship facts
            include_current: If True, include relationship/3 facts
            
        Returns:
            List of ASP fact strings
        """
        facts = []
        for rel in relationships:
            if include_previous:
                facts.append(self.previous_relationship_to_asp(rel))
            if include_initial:
                facts.append(self.initial_relationship_to_asp(rel))
            if include_current:
                facts.append(self.relationship_to_asp(rel))
        return facts
    
    def relationship_tuple_to_asp(
        self,
        source: str,
        target: str,
        rel_type: str,
    ) -> List[str]:
        """
        Generate relationship facts from tuple values.
        
        Args:
            source: Source character
            target: Target character
            rel_type: Relationship type
            
        Returns:
            List containing previous_relationship and initial_relationship facts
        """
        return [
            f"previous_relationship({source}, {target}, {rel_type}).",
            f"initial_relationship({source}, {target}, {rel_type}).",
        ]
    
    # =========================================================================
    # TIME SCOPE CONVERSION
    # =========================================================================
    
    def time_scope_to_asp(self, scope: TimeScope) -> List[str]:
        """
        Generate ASP facts for time scope.
        
        Generates predicates:
            - current_chapter/1
            - current_time_window/2
            - previous_time_window/2 (optional)
            - previous_chapter/1 (optional)
            - time/1 (for each time in scope)
        
        Args:
            scope: TimeScope domain object
            
        Returns:
            List of ASP fact strings
        """
        facts = [
            f"% Time scope: chapter {scope.current_chapter}",
            f"current_chapter({scope.current_chapter}).",
            f"current_time_window({scope.current_time_start}, {scope.current_time_end}).",
        ]
        
        if scope.previous_time_start is not None and scope.previous_time_end is not None:
            facts.append(f"previous_time_window({scope.previous_time_start}, {scope.previous_time_end}).")
            facts.append(f"previous_chapter({scope.current_chapter - 1}).")
        
        for t in range(scope.current_time_start, scope.current_time_end + 1):
            facts.append(f"time({t}).")
        
        if scope.previous_time_start is not None and scope.previous_time_end is not None:
            for t in range(scope.previous_time_start, scope.previous_time_end + 1):
                facts.append(f"time({t}).")
        
        return facts
    
    def current_time_to_asp(self, time: int) -> str:
        """Generate current_time fact."""
        return f"current_time({time})."
    
    def previous_emotion_to_asp(self, char: str, emotion: str) -> str:
        """Generate previous_emotion fact."""
        return f"previous_emotion({char}, {emotion})."
    
    # =========================================================================
    # WORLD STATE CONVERSION
    # =========================================================================
    
    def world_state_to_asp(
        self,
        state: 'WorldState',
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Convert a WorldState to ASP facts.
        
        Args:
            state: WorldState to convert
            active_universe: Optional filter for active universe entities
            
        Returns:
            ASP facts as a string
        """
        lines = [f"% World state at time {state.time}"]
        all_entities = active_universe.all_entities if active_universe else None
        
        # Entity facts
        for entity_id, entity in state.entities.items():
            if all_entities is not None and entity_id not in all_entities:
                continue
            lines.append(f"{entity.entity_type}({entity_id}).")
            for trait in entity.traits:
                lines.append(self.trait_to_asp(entity_id, trait))
            if entity.state == "dead":
                lines.append(self.is_dead_to_asp(entity_id))
            if entity.emotion:
                lines.append(self.emotion_to_asp(entity_id, entity.emotion))
        
        # Relation facts (time-indexed)
        for rel in state.relations:
            if rel.time == state.time:
                if all_entities is not None:
                    skip = False
                    for arg in rel.args:
                        if arg.isdigit():
                            continue
                        if arg not in all_entities:
                            skip = True
                            break
                    if skip:
                        continue
                args_str = ", ".join(rel.args)
                lines.append(f"{rel.predicate}({args_str}, {state.time}).")
        
        # Story rules
        for rule in state.story_rules:
            if rule.valid:
                if all_entities is not None:
                    if rule.subject not in all_entities:
                        continue
                    if rule.object and rule.object not in all_entities:
                        continue
                lines.append(self.story_rule_to_asp(rule))
        
        # Derived facts
        for fact in state.derived_facts:
            lines.append(fact)
        
        return "\n".join(lines)
    
    # =========================================================================
    # STORY RULE CONVERSION
    # =========================================================================
    
    def story_rule_to_asp(self, rule: 'StoryRule') -> str:
        """
        Convert a StoryRule to ASP fact.
        
        Args:
            rule: StoryRule to convert
            
        Returns:
            ASP fact string
        """
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
    
    # =========================================================================
    # CONFLICT OVERRIDE/EXCEPTION RULES
    # =========================================================================
    
    def story_override_rule_to_asp(
        self,
        violation_type: str,
        rule_id: str,
        conflict_id: str,
        reason: str,
    ) -> str:
        """
        Generate ASP rule that overrides a universal rule.
        
        Args:
            violation_type: Type of violation to override
            rule_id: ID of the universal rule being overridden
            conflict_id: ID of the conflict
            reason: Reason for the override
            
        Returns:
            ASP override rule as a string
        """
        return f"""
% Story override for {rule_id}
% Generated from conflict: {conflict_id}
% Reason: {reason}

% Disable violation detection for {violation_type}
story_override({violation_type}).
-violation(Category, {violation_type}, E, D) :- story_override({violation_type}), violation(Category, {violation_type}, E, D).
"""
    
    def story_exception_rule_to_asp(
        self,
        violation_type: str,
        entities: List[str],
        rule_id: str,
        conflict_id: str,
    ) -> str:
        """
        Generate ASP rule that creates exceptions for specific entities.
        
        Args:
            violation_type: Type of violation to create exception for
            entities: List of entity IDs to except
            rule_id: ID of the universal rule being excepted
            conflict_id: ID of the conflict
            
        Returns:
            ASP exception rule as a string
        """
        lines = [
            f"% Story exception for {rule_id}",
            f"% Generated from conflict: {conflict_id}",
            f"% Entities excepted: {', '.join(entities)}",
            "",
        ]
        
        for entity in entities:
            lines.append(f"story_exception({violation_type}, {entity}).")
        
        lines.append("")
        lines.append(f"% Suppress violations for excepted entities")
        lines.append(f"-violation(Category, {violation_type}, E, Entity) :- "
                     f"story_exception({violation_type}, Entity), violation(Category, {violation_type}, E, Entity).")
        
        return "\n".join(lines)
    
    # =========================================================================
    # ALIAS CONVERSION
    # =========================================================================
    
    def aliases_to_asp(
        self,
        aliases: Dict[str, str],
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Generate ASP alias facts.
        
        Args:
            aliases: Dict mapping alias to canonical ID
            active_universe: Optional filter
            
        Returns:
            ASP facts as a string
        """
        lines = ["% Character alias facts"]
        all_entities = active_universe.all_entities if active_universe else None
        
        for alias, canonical in aliases.items():
            if alias == canonical:
                continue
            if all_entities is not None and canonical not in all_entities:
                continue
            lines.append(self.alias_to_asp(alias, canonical))
        
        return "\n".join(lines)
    
    def aliases_from_resolver_to_asp(
        self,
        alias_resolver: Optional[Any] = None,
        active_universe: Optional['ActiveUniverseResult'] = None,
        legacy_aliases: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate ASP alias facts from an AliasResolver or legacy aliases.
        
        Args:
            alias_resolver: Optional AliasResolver for dynamic aliases
            active_universe: Optional filter for active universe entities
            legacy_aliases: Optional fallback dict if no resolver provided
            
        Returns:
            ASP facts as a string with alias/2 predicates
        """
        if alias_resolver is not None:
            aliases = alias_resolver.get_all_aliases()
        elif legacy_aliases is not None:
            aliases = legacy_aliases
        else:
            aliases = {}
        
        return self.aliases_to_asp(aliases, active_universe)
    
    # =========================================================================
    # ILASP CONVERSION
    # =========================================================================
    
    def ilasp_mode_declarations_to_asp(self) -> str:
        """
        Generate default ILASP mode declarations.
        
        Returns:
            ILASP mode declaration string
        """
        return """
% Default mode declarations
#modeh(violation(const(category), const(type), var(event), var(entity))).
#modeb(event(var(event))).
#modeb(agent(var(event), var(entity))).
#modeb(patient(var(event), var(entity))).
#modeb(event_type(var(event), const(type))).
#modeb(character(var(entity))).
#modeb(is_dead(var(entity))).
"""
    
    def ilasp_positive_example_to_asp(
        self,
        example_id: str,
        content: str,
    ) -> str:
        """
        Generate ILASP positive example.
        
        Args:
            example_id: Unique example identifier
            content: Example content (the atom to cover)
            
        Returns:
            ILASP #pos directive
        """
        return f"#pos({example_id}, {{{content}}}, {{}})."
    
    def ilasp_negative_example_to_asp(
        self,
        example_id: str,
        content: str,
    ) -> str:
        """
        Generate ILASP negative example.
        
        Args:
            example_id: Unique example identifier
            content: Example content (the atom that should not be covered)
            
        Returns:
            ILASP #neg directive
        """
        return f"#neg({example_id}, {{{content}}}, {{}})."
    
    def ilasp_violation_example_to_asp(
        self,
        chapter_num: int,
        index: int,
        category: str,
        vtype: str,
        event: str,
        detail: str,
    ) -> str:
        """
        Generate ILASP positive example for a violation.
        
        Args:
            chapter_num: Chapter number
            index: Example index
            category: Violation category
            vtype: Violation type
            event: Event ID
            detail: Violation detail
            
        Returns:
            ILASP #pos directive
        """
        return f"#pos(v{chapter_num}_{index}, {{violation({category}, {vtype}, {event}, {detail})}}, {{}})."
    
    def ilasp_character_negative_example_to_asp(
        self,
        char: str,
    ) -> str:
        """
        Generate ILASP negative example for a known character.
        
        This ensures the system doesn't flag known characters as unknown.
        
        Args:
            char: Character ID
            
        Returns:
            ILASP #neg directive
        """
        return f"#neg(neg_char_{char}, {{violation(coherence, unknown_agent, _, {char})}}, {{}})."
    
    # =========================================================================
    # RULE ASSEMBLY
    # =========================================================================
    
    def rule_header_to_asp(self, header: str) -> str:
        """Generate an ASP comment header."""
        return f"% {header}"
    
    def projected_rules_to_asp(
        self,
        rules: List[Any],
        header: str = "PROJECTED RULES",
    ) -> str:
        """
        Assemble projected rules into an ASP program string.
        
        Args:
            rules: List of projected rule objects (with rule_id and content attrs)
            header: Header text for the section
            
        Returns:
            ASP program string
        """
        lines = [f"% === {header} (Phase 8.11) ==="]
        for rule in rules:
            lines.append(f"% Rule: {rule.rule_id}")
            lines.append(rule.content)
        return "\n".join(lines)
    
    def combined_rules_to_asp(
        self,
        rules: List[Any],
        layer_name: str,
    ) -> List[str]:
        """
        Generate ASP lines for a layer of rules.
        
        Args:
            rules: List of rule objects with id and content attributes
            layer_name: Name of the rule layer
            
        Returns:
            List of ASP lines
        """
        lines = [f"\n% === {layer_name} RULES ==="]
        for rule in rules:
            lines.append(f"% Rule: {rule.id}")
            lines.append(rule.content)
        return lines
    
    # =========================================================================
    # ENTITY EXTRACTION FROM RULES
    # =========================================================================
    
    def extract_entities_from_rule(self, rule_content: str) -> Set[str]:
        """
        Extract entity references from ASP rule content.
        
        This is a heuristic extraction that identifies likely entity constants
        in ASP facts and rules.
        
        Args:
            rule_content: ASP rule content string
            
        Returns:
            Set of entity identifiers found in the rule
        """
        entities: Set[str] = set()
        
        for pattern in ENTITY_PATTERNS:
            for match in pattern.finditer(rule_content):
                for group in match.groups():
                    if group:
                        entities.add(group)
        
        filtered = set()
        for entity in entities:
            if entity.lower() in RESERVED_WORDS:
                continue
            if len(entity) == 1:
                continue
            if entity.isdigit():
                continue
            if entity[0].isupper():
                continue
            if re.match(r'^e\d+$', entity):
                continue
            filtered.add(entity)
        
        return filtered
    
    # =========================================================================
    # MISCELLANEOUS PREDICATES
    # =========================================================================
    
    def time_order_to_asp(self, event1: str, event2: str) -> str:
        """Generate time_order fact."""
        return f"time_order({event1}, {event2})."
    
    def connected_to_asp(self, loc1: str, loc2: str) -> str:
        """Generate connected fact (bidirectional)."""
        return f"connected({loc1}, {loc2})."
    
    def contains_to_asp(self, container: str, contained: str) -> str:
        """Generate contains fact."""
        return f"contains({container}, {contained})."
    
    def object_to_asp(self, obj_id: str) -> str:
        """Generate object declaration fact (legacy)."""
        return f"object({obj_id})."
    
    def item_state_to_asp(self, item_id: str, state: str) -> str:
        """Generate item_state fact."""
        return f"item_state({item_id}, {state})."
    
    def item_relevance_to_asp(self, item_id: str, relevance: str) -> str:
        """Generate item_relevance fact."""
        return f"item_relevance({item_id}, {relevance})."
    
    def character_state_to_asp(self, char_id: str, state: str) -> str:
        """Generate character_state fact."""
        return f"character_state({char_id}, {state})."
    
    def character_appearance_to_asp(self, char_id: str, appearance: str) -> str:
        """Generate character_appearance fact."""
        return f"character_appearance({char_id}, {appearance})."
    
    def report_to_asp(self, event_id: str) -> str:
        """Generate report fact."""
        return f"report({event_id})."
    
    def recipient_to_asp(self, event_id: str, recipient_id: str) -> str:
        """Generate recipient fact."""
        return f"recipient({event_id}, {recipient_id})."
    
    def learned_to_asp(self, agent_id: str, fact_id: str, event_time: int) -> str:
        """Generate learned fact."""
        return f"learned({agent_id}, {fact_id}, {event_time})."
    
    def learn_event_to_asp(self, event_id: str) -> str:
        """Generate learn_event fact."""
        return f"learn_event({event_id})."
    
    def knowledge_source_to_asp(self, event_id: str, source_id: str) -> str:
        """Generate knowledge_source fact."""
        return f"knowledge_source({event_id}, {source_id})."
    
    def implied_presence_to_asp(
        self,
        entity_id: str,
        location_id: str,
        chapter_num: int,
    ) -> str:
        """Generate implied_presence fact."""
        return f"implied_presence({entity_id}, {location_id}, {chapter_num})."
    
    def implied_presence_event_to_asp(self, event_id: str) -> str:
        """Generate implied_presence_event fact."""
        return f"implied_presence_event({event_id})."
    
    def event_location_to_asp(self, event_id: str, location_id: str) -> str:
        """Generate event_location fact."""
        return f"event_location({event_id}, {location_id})."
