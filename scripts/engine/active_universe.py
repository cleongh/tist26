"""
Active Universe Computation - ASP-Visible Entity Filtering

Per LOGIC_DESIGN.md Section 7.1 (Python Layer):
    Python is for orchestration, including determining which entities
    participate in logic evaluation.

This module computes the "ASP-visible entity universe" per chapter.
Only entities in this set should appear in ASP facts.

Definition of Active Universe:
    1. Entities that act in the CURRENT chapter (agents, patients, locations)
    2. Entities that acted in the PREVIOUS chapter
    3. Entities directly related (1-hop) to the above:
        - Relationship partners
        - Carried items
        - Locations where they are present

All other entities are EXCLUDED from ASP facts for this chapter,
significantly reducing ASP grounding time.

Phase 8.5: Memory Optimization
    - Reduces ASP fact count from O(total_entities) to O(active_entities)
    - Deterministic and testable output
    - No entity outside this set may appear in any ASP fact
"""

import re
import logging
from typing import Dict, List, Set, Optional, Any, TYPE_CHECKING

from .domain import ActiveUniverseResult, TimeScope
from .preprocessors import EventPreprocessor

if TYPE_CHECKING:
    from .registries import EntityRegistry
    from .item_tracker import ItemTracker
    from .state_manager import StateManager

logger = logging.getLogger(__name__)


class ActiveUniverse:
    """
    Computes the ASP-visible entity universe for a chapter.
    
    This class determines which entities should appear in ASP facts.
    Only entities in the computed set may appear in any ASP fact.
    
    Algorithm:
        1. Extract entities from current chapter events (agents, patients, locations)
        2. Extract entities from previous chapter events
        3. Expand by 1-hop: relationship partners of the above
        4. Expand by 1-hop: items carried by characters in the set
        5. Expand by 1-hop: locations where characters are present
    """
    
    def __init__(
        self,
        entity_registry: 'EntityRegistry',
        item_tracker: Optional['ItemTracker'] = None,
        event_preprocessor: Optional[EventPreprocessor] = None,
    ):
        """
        Initialize the ActiveUniverse.
        
        Args:
            entity_registry: EntityRegistry with all registered entities
            item_tracker: ItemTracker with item state (may be None)
            event_preprocessor: EventPreprocessor for entity extraction (may be None)
        """
        self._entity_registry = entity_registry
        self._item_tracker = item_tracker
        self._event_preprocessor = event_preprocessor
    
    def compute(
        self,
        current_chapter_events: List[Dict[str, Any]],
        previous_chapter_events: Optional[List[Dict[str, Any]]],
        relationships: Dict[tuple, str],
    ) -> ActiveUniverseResult:
        """
        Compute the ASP-visible entity universe for a chapter.
        
        Args:
            current_chapter_events: Events in the current chapter
            previous_chapter_events: Events in the previous chapter (may be None for ch 0)
            relationships: Dict of (char1, char2) -> rel_type
            
        Returns:
            ActiveUniverseResult with sets of visible entity IDs
        """
        # Initialize result sets
        active_characters: Set[str] = set()
        active_items: Set[str] = set()
        active_locations: Set[str] = set()
        
        # Statistics
        current_actors = 0
        previous_actors = 0
        rel_expansions = 0
        item_expansions = 0
        
        # Step 1: Extract entities from current chapter events
        current_entities = self._extract_entities(current_chapter_events)
        current_actors = len(current_entities)
        self._classify_entities(current_entities, active_characters, active_items, active_locations)
        
        # Step 2: Extract entities from previous chapter events
        if previous_chapter_events:
            previous_entities = self._extract_entities(previous_chapter_events)
            previous_actors = len(previous_entities)
            self._classify_entities(previous_entities, active_characters, active_items, active_locations)
        
        # Step 3: Expand by relationship partners (1-hop)
        rel_expansions = self._expand_by_relationships(active_characters, relationships)
        
        # Step 4: Expand by carried items (1-hop)
        item_expansions = self._expand_by_carried_items(active_characters, active_items)
        
        result = ActiveUniverseResult(
            characters=active_characters,
            items=active_items,
            locations=active_locations,
            current_chapter_actors=current_actors,
            previous_chapter_actors=previous_actors,
            relationship_expansions=rel_expansions,
            item_expansions=item_expansions,
        )
        
        logger.debug(
            f"Active universe: {result.total_count} entities "
            f"({len(active_characters)} chars, {len(active_items)} items, {len(active_locations)} locs)"
        )
        
        return result
    
    def compute_from_state_manager(
        self,
        current_chapter_events: List[Dict[str, Any]],
        previous_chapter_events: Optional[List[Dict[str, Any]]],
        state_manager: 'StateManager',
    ) -> ActiveUniverseResult:
        """
        Convenience method that extracts relationships from StateManager.
        
        Args:
            current_chapter_events: Events in the current chapter
            previous_chapter_events: Events in the previous chapter (may be None)
            state_manager: StateManager instance
            
        Returns:
            ActiveUniverseResult with sets of visible entity IDs
        """
        return self.compute(
            current_chapter_events=current_chapter_events,
            previous_chapter_events=previous_chapter_events,
            relationships=state_manager.persistent_relationships,
        )
    
    def _extract_entities(self, events: List[Dict[str, Any]]) -> Set[str]:
        """Extract entities from events using preprocessor or fallback."""
        if self._event_preprocessor:
            return self._event_preprocessor.extract_entities_from_events(events)
        
        # Fallback: inline extraction
        entities: Set[str] = set()
        for event in events:
            for field in ("agent", "patient", "location", "item", "object"):
                if event.get(field):
                    entities.add(event[field])
        entities.discard("")
        entities.discard("unknown")
        entities.discard("none")
        entities.discard(None)
        return entities
    
    def _classify_entities(
        self,
        entities: Set[str],
        active_characters: Set[str],
        active_items: Set[str],
        active_locations: Set[str],
    ) -> None:
        """Classify entities by type and add to appropriate sets."""
        for entity_id in entities:
            entity = self._entity_registry.get_entity(entity_id)
            if entity:
                if entity.entity_type.value == "character":
                    active_characters.add(entity_id)
                elif entity.entity_type.value == "item":
                    active_items.add(entity_id)
                elif entity.entity_type.value == "location":
                    active_locations.add(entity_id)
            else:
                # Unknown entity - check if it's an item in ItemTracker
                if self._item_tracker and self._item_tracker.get_item(entity_id):
                    active_items.add(entity_id)
                else:
                    # Could be location (often not registered as entities)
                    active_locations.add(entity_id)
    
    def _expand_by_relationships(
        self,
        active_characters: Set[str],
        relationships: Dict[tuple, str],
    ) -> int:
        """Expand active characters by relationship partners (1-hop)."""
        expansions = 0
        chars_to_expand = set(active_characters)  # Copy to avoid modification during iteration
        
        for (char1, char2), rel_type in relationships.items():
            if char1 in chars_to_expand and char2 not in active_characters:
                active_characters.add(char2)
                expansions += 1
            if char2 in chars_to_expand and char1 not in active_characters:
                active_characters.add(char1)
                expansions += 1
        
        return expansions
    
    def _expand_by_carried_items(
        self,
        active_characters: Set[str],
        active_items: Set[str],
    ) -> int:
        """Expand active items by items carried by active characters."""
        expansions = 0
        if not self._item_tracker:
            return expansions
        
        for char_id in active_characters:
            carried = self._item_tracker.get_carried_items(char_id)
            for item in carried:
                if item.item_id not in active_items:
                    active_items.add(item.item_id)
                    expansions += 1
        
        return expansions
    
    def filter_asp_facts_by_universe(
        self,
        asp_facts: List[str],
        active_universe: ActiveUniverseResult,
    ) -> List[str]:
        """
        Filter ASP facts to only include entities in the active universe.
        
        Args:
            asp_facts: List of ASP fact strings
            active_universe: ActiveUniverseResult from compute()
            
        Returns:
            Filtered list of ASP facts
        """
        all_entities = active_universe.all_entities
        filtered = []
        
        for fact in asp_facts:
            if self._should_include_fact(fact, all_entities):
                filtered.append(fact)
        
        return filtered
    
    def _should_include_fact(self, fact: str, all_entities: Set[str]) -> bool:
        """Check if a fact should be included based on entity universe."""
        # Skip comments and empty lines
        if fact.startswith("%") or not fact.strip():
            return True
        
        # Parse arguments from fact
        match = re.search(r'\(([^)]+)\)', fact)
        if not match:
            return True  # No arguments, keep it
        
        args = [arg.strip() for arg in match.group(1).split(",")]
        
        # Check if all entity-like arguments are in universe
        for arg in args:
            if not self._is_entity_in_universe(arg, all_entities):
                return False
        
        return True
    
    def _is_entity_in_universe(self, arg: str, all_entities: Set[str]) -> bool:
        """Check if an argument is either not an entity or is in the universe."""
        # Skip numeric values (times, quantities)
        if arg.isdigit():
            return True
        # Skip quoted strings
        if arg.startswith('"') or arg.startswith("'"):
            return True
        # Check if this looks like an entity ID
        if re.match(r'^[a-z_][a-z0-9_]*$', arg):
            return arg in all_entities
        return True
    
    def compute_time_scope(
        self,
        current_chapter: int,
        current_chapter_events: List[Dict[str, Any]],
        previous_chapter_events: Optional[List[Dict[str, Any]]] = None,
        event_id_to_time: Optional[Dict[str, int]] = None,
    ) -> TimeScope:
        """
        Compute the time scope for ASP fact generation.
        
        Args:
            current_chapter: Current chapter number
            current_chapter_events: Events in the current chapter
            previous_chapter_events: Events in the previous chapter (optional)
            event_id_to_time: Optional mapping of event ID to time
            
        Returns:
            TimeScope defining the valid time window
        """
        # Compute current chapter time range
        current_time_start, current_time_end = self._compute_time_range(
            current_chapter_events, event_id_to_time
        )
        
        # Compute previous chapter time range
        previous_time_start = None
        previous_time_end = None
        if previous_chapter_events:
            previous_time_start, previous_time_end = self._compute_time_range(
                previous_chapter_events, event_id_to_time
            )
        
        return TimeScope(
            current_chapter=current_chapter,
            current_time_start=current_time_start,
            current_time_end=current_time_end,
            previous_time_start=previous_time_start,
            previous_time_end=previous_time_end,
        )
    
    def _compute_time_range(
        self,
        events: List[Dict[str, Any]],
        event_id_to_time: Optional[Dict[str, int]],
    ) -> tuple:
        """Compute time range for a list of events."""
        if not events:
            return (1, 1)
        
        times = [
            self._extract_time_from_event(e, i, event_id_to_time)
            for i, e in enumerate(events)
        ]
        return (min(times), max(times))
    
    def _extract_time_from_event(
        self,
        event: Dict[str, Any],
        index: int,
        event_id_to_time: Optional[Dict[str, int]],
    ) -> int:
        """Extract time from event, using global_id or index."""
        if event_id_to_time:
            eid = event.get("global_id", event.get("id"))
            if eid and eid in event_id_to_time:
                return event_id_to_time[eid]
        
        # Try to extract from global_id format (e.g., "e42")
        global_id = event.get("global_id", event.get("id", ""))
        if global_id.startswith("e") and global_id[1:].isdigit():
            return int(global_id[1:])
        
        # Fall back to index-based time
        return index + 1
    
    def filter_facts_by_time_scope(
        self,
        facts: List[str],
        time_scope: TimeScope,
    ) -> List[str]:
        """
        Filter ASP facts to only include those within the time scope.
        
        Facts with time parameters outside the scope are removed.
        Facts without time parameters are kept.
        
        Args:
            facts: List of ASP fact strings
            time_scope: TimeScope defining the valid time window
            
        Returns:
            Filtered list of ASP facts
        """
        filtered = []
        
        for fact in facts:
            fact = fact.strip()
            if self._should_include_time_fact(fact, time_scope):
                filtered.append(fact)
        
        return filtered
    
    def _should_include_time_fact(self, fact: str, time_scope: TimeScope) -> bool:
        """Check if a fact should be included based on time scope."""
        # Skip comments and empty lines
        if not fact or fact.startswith("%"):
            return True
        
        # Check for time/1 fact: time(123).
        time_match = re.match(r'^time\((\d+)\)\.$', fact)
        if time_match:
            time_val = int(time_match.group(1))
            return time_scope.is_time_in_scope(time_val)
        
        # Check for event_time/2 and other time-indexed facts
        if "event_time(" in fact or "event_order(" in fact:
            match = re.search(r'\(e(\d+),\s*(\d+)\)', fact)
            if match:
                time_val = int(match.group(2))
                return time_scope.is_time_in_scope(time_val)
        
        # For other facts, include them
        return True
