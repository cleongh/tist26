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

from typing import Dict, List, Set, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass
import logging

if TYPE_CHECKING:
    from .entity_registry import EntityRegistry
    from .item_tracker import ItemTracker
    from .state_manager import StateManager

logger = logging.getLogger(__name__)


@dataclass
class ActiveUniverseResult:
    """
    Result of active universe computation.
    
    Contains sets of canonical entity IDs that should be visible to ASP.
    """
    characters: Set[str]
    items: Set[str]
    locations: Set[str]
    
    # Statistics for debugging/logging
    current_chapter_actors: int = 0
    previous_chapter_actors: int = 0
    relationship_expansions: int = 0
    item_expansions: int = 0
    
    @property
    def all_entities(self) -> Set[str]:
        """Get all entity IDs (characters + items + locations)."""
        return self.characters | self.items | self.locations
    
    @property
    def total_count(self) -> int:
        """Total number of entities in the active universe."""
        return len(self.characters) + len(self.items) + len(self.locations)
    
    def contains(self, entity_id: str) -> bool:
        """Check if an entity is in the active universe."""
        return entity_id in self.all_entities
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "characters": sorted(self.characters),
            "items": sorted(self.items),
            "locations": sorted(self.locations),
            "statistics": {
                "total": self.total_count,
                "characters": len(self.characters),
                "items": len(self.items),
                "locations": len(self.locations),
                "current_chapter_actors": self.current_chapter_actors,
                "previous_chapter_actors": self.previous_chapter_actors,
                "relationship_expansions": self.relationship_expansions,
                "item_expansions": self.item_expansions,
            }
        }


def extract_entities_from_events(events: List[Dict[str, Any]]) -> Set[str]:
    """
    Extract all entity IDs referenced in a list of events.
    
    Extracts from fields: agent, patient, location, item, object
    
    Args:
        events: List of event dictionaries
        
    Returns:
        Set of canonical entity IDs
    """
    entities: Set[str] = set()
    
    for event in events:
        # Primary participants
        if event.get("agent"):
            entities.add(event["agent"])
        if event.get("patient"):
            entities.add(event["patient"])
        if event.get("location"):
            entities.add(event["location"])
        
        # Secondary participants (items, objects)
        if event.get("item"):
            entities.add(event["item"])
        if event.get("object"):
            entities.add(event["object"])
    
    # Filter out empty/unknown values
    entities.discard("")
    entities.discard("unknown")
    entities.discard("none")
    entities.discard(None)
    
    return entities


def compute_active_universe(
    current_chapter_events: List[Dict[str, Any]],
    previous_chapter_events: Optional[List[Dict[str, Any]]],
    entity_registry: 'EntityRegistry',
    item_tracker: Optional['ItemTracker'],
    relationships: Dict[tuple, str],
) -> ActiveUniverseResult:
    """
    Compute the ASP-visible entity universe for a chapter.
    
    This function determines which entities should appear in ASP facts.
    Only entities in the returned set may appear in any ASP fact.
    
    Algorithm:
        1. Extract entities from current chapter events (agents, patients, locations)
        2. Extract entities from previous chapter events
        3. Expand by 1-hop: relationship partners of the above
        4. Expand by 1-hop: items carried by characters in the set
        5. Expand by 1-hop: locations where characters are present
    
    Args:
        current_chapter_events: Events in the current chapter
        previous_chapter_events: Events in the previous chapter (may be None for ch 0)
        entity_registry: EntityRegistry with all registered entities
        item_tracker: ItemTracker with item state (may be None)
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
    
    # =========================================================================
    # Step 1: Extract entities from current chapter events
    # =========================================================================
    current_entities = extract_entities_from_events(current_chapter_events)
    current_actors = len(current_entities)
    
    # Classify by entity type
    for entity_id in current_entities:
        entity = entity_registry.get_entity(entity_id)
        if entity:
            if entity.entity_type.value == "character":
                active_characters.add(entity_id)
            elif entity.entity_type.value == "item":
                active_items.add(entity_id)
            elif entity.entity_type.value == "location":
                active_locations.add(entity_id)
        else:
            # Unknown entity - check if it's an item in ItemTracker
            if item_tracker and item_tracker.get_item(entity_id):
                active_items.add(entity_id)
            else:
                # Could be location (often not registered as entities)
                # Include it in locations as a fallback
                active_locations.add(entity_id)
    
    # =========================================================================
    # Step 2: Extract entities from previous chapter events
    # =========================================================================
    if previous_chapter_events:
        previous_entities = extract_entities_from_events(previous_chapter_events)
        previous_actors = len(previous_entities)
        
        for entity_id in previous_entities:
            entity = entity_registry.get_entity(entity_id)
            if entity:
                if entity.entity_type.value == "character":
                    active_characters.add(entity_id)
                elif entity.entity_type.value == "item":
                    active_items.add(entity_id)
                elif entity.entity_type.value == "location":
                    active_locations.add(entity_id)
            else:
                if item_tracker and item_tracker.get_item(entity_id):
                    active_items.add(entity_id)
                else:
                    active_locations.add(entity_id)
    
    # =========================================================================
    # Step 3: Expand by relationship partners (1-hop)
    # =========================================================================
    # For each active character, add their relationship partners
    chars_to_expand = set(active_characters)  # Copy to avoid modification during iteration
    
    for (char1, char2), rel_type in relationships.items():
        if char1 in chars_to_expand:
            if char2 not in active_characters:
                active_characters.add(char2)
                rel_expansions += 1
        if char2 in chars_to_expand:
            if char1 not in active_characters:
                active_characters.add(char1)
                rel_expansions += 1
    
    # =========================================================================
    # Step 4: Expand by carried items (1-hop)
    # =========================================================================
    if item_tracker:
        for char_id in active_characters:
            carried = item_tracker.get_carried_items(char_id)
            for item in carried:
                if item.item_id not in active_items:
                    active_items.add(item.item_id)
                    item_expansions += 1
    
    # =========================================================================
    # Step 5: Expand by location presence (1-hop)
    # =========================================================================
    # Note: Current implementation doesn't track "present(char, loc)" persistently
    # Locations are already included from events, so this step is implicit
    
    # =========================================================================
    # Build result
    # =========================================================================
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


def compute_active_universe_from_state_manager(
    current_chapter_events: List[Dict[str, Any]],
    previous_chapter_events: Optional[List[Dict[str, Any]]],
    state_manager: 'StateManager',
    item_tracker: Optional['ItemTracker'] = None,
) -> ActiveUniverseResult:
    """
    Convenience function that extracts dependencies from StateManager.
    
    Args:
        current_chapter_events: Events in the current chapter
        previous_chapter_events: Events in the previous chapter (may be None)
        state_manager: StateManager instance
        item_tracker: Optional ItemTracker instance
        
    Returns:
        ActiveUniverseResult with sets of visible entity IDs
    """
    return compute_active_universe(
        current_chapter_events=current_chapter_events,
        previous_chapter_events=previous_chapter_events,
        entity_registry=state_manager.entity_registry,
        item_tracker=item_tracker,
        relationships=state_manager.persistent_relationships,
    )


def filter_asp_facts_by_universe(
    asp_facts: List[str],
    active_universe: ActiveUniverseResult,
) -> List[str]:
    """
    Filter ASP facts to only include entities in the active universe.
    
    Args:
        asp_facts: List of ASP fact strings
        active_universe: ActiveUniverseResult from compute_active_universe
        
    Returns:
        Filtered list of ASP facts
    """
    all_entities = active_universe.all_entities
    filtered = []
    
    for fact in asp_facts:
        # Extract entity IDs from the fact
        # Facts have format: predicate(arg1, arg2, ...).
        # We check if any argument is NOT in our universe
        
        # Skip comments and empty lines
        if fact.startswith("%") or not fact.strip():
            filtered.append(fact)
            continue
        
        # Parse arguments from fact
        # Simple heuristic: extract words inside parentheses
        import re
        match = re.search(r'\(([^)]+)\)', fact)
        if not match:
            filtered.append(fact)  # No arguments, keep it
            continue
        
        args = [arg.strip() for arg in match.group(1).split(",")]
        
        # Check if all entity-like arguments are in universe
        # Entity IDs are typically lowercase with underscores
        include = True
        for arg in args:
            # Skip numeric values (times, quantities)
            if arg.isdigit():
                continue
            # Skip quoted strings
            if arg.startswith('"') or arg.startswith("'"):
                continue
            # Check if this looks like an entity ID
            if re.match(r'^[a-z_][a-z0-9_]*$', arg):
                if arg not in all_entities:
                    # Entity not in active universe - exclude this fact
                    include = False
                    break
        
        if include:
            filtered.append(fact)
    
    return filtered


# =============================================================================
# Time-Scoped ASP Fact Generation (Phase 8.7)
# =============================================================================

@dataclass
class TimeScope:
    """
    Defines the valid time window for ASP fact generation.
    
    Per LOGIC_DESIGN.md Section 4: Events are state transitions at specific timesteps.
    To limit ASP grounding, we only include facts for:
    - current_time: The time window for the current chapter
    - previous_time: The time window for the previous chapter (for continuity)
    
    All other timesteps are excluded from ASP facts.
    """
    current_chapter: int
    current_time_start: int  # First event time in current chapter
    current_time_end: int    # Last event time in current chapter
    previous_time_start: Optional[int] = None  # First event time in previous chapter
    previous_time_end: Optional[int] = None    # Last event time in previous chapter
    
    def is_time_in_scope(self, time: int) -> bool:
        """Check if a time value is within the valid scope."""
        # Current chapter times
        if self.current_time_start <= time <= self.current_time_end:
            return True
        # Previous chapter times
        if self.previous_time_start is not None and self.previous_time_end is not None:
            if self.previous_time_start <= time <= self.previous_time_end:
                return True
        return False
    
    def get_time_facts(self) -> List[str]:
        """
        Generate explicit time scope facts for ASP.
        
        Instead of emitting time(N) for all N, we emit:
        - current_chapter(C)
        - current_time_window(Start, End)
        - previous_time_window(Start, End)  [if applicable]
        - time(N) for only N in the valid windows
        """
        facts = [
            f"% Time scope: chapter {self.current_chapter}",
            f"current_chapter({self.current_chapter}).",
            f"current_time_window({self.current_time_start}, {self.current_time_end}).",
        ]
        
        if self.previous_time_start is not None and self.previous_time_end is not None:
            facts.append(f"previous_time_window({self.previous_time_start}, {self.previous_time_end}).")
            facts.append(f"previous_chapter({self.current_chapter - 1}).")
        
        # Emit time/1 facts only for in-scope times
        for t in range(self.current_time_start, self.current_time_end + 1):
            facts.append(f"time({t}).")
        
        if self.previous_time_start is not None and self.previous_time_end is not None:
            for t in range(self.previous_time_start, self.previous_time_end + 1):
                facts.append(f"time({t}).")
        
        return facts
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "current_chapter": self.current_chapter,
            "current_time_start": self.current_time_start,
            "current_time_end": self.current_time_end,
            "previous_time_start": self.previous_time_start,
            "previous_time_end": self.previous_time_end,
        }


def compute_time_scope(
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
        event_id_to_time: Optional mapping of event ID to time (if not using global IDs)
        
    Returns:
        TimeScope defining the valid time window
    """
    def extract_time_from_event(event: Dict, index: int) -> int:
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
    
    # Compute current chapter time range
    if current_chapter_events:
        current_times = [extract_time_from_event(e, i) for i, e in enumerate(current_chapter_events)]
        current_time_start = min(current_times)
        current_time_end = max(current_times)
    else:
        # No events in current chapter - use chapter-based time
        current_time_start = 1
        current_time_end = 1
    
    # Compute previous chapter time range
    previous_time_start = None
    previous_time_end = None
    if previous_chapter_events:
        previous_times = [extract_time_from_event(e, i) for i, e in enumerate(previous_chapter_events)]
        previous_time_start = min(previous_times)
        previous_time_end = max(previous_times)
    
    return TimeScope(
        current_chapter=current_chapter,
        current_time_start=current_time_start,
        current_time_end=current_time_end,
        previous_time_start=previous_time_start,
        previous_time_end=previous_time_end,
    )


def filter_facts_by_time_scope(
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
    import re
    filtered = []
    
    # Pattern for time/1 fact: time(123).
    time_pattern = re.compile(r'^time\((\d+)\)\.$')
    
    # Pattern for time-indexed facts: predicate(..., 123).
    # Common patterns: event_time(E, T), relationship(A, B, Type, T), etc.
    time_indexed_pattern = re.compile(r',\s*(\d+)\)\.$')
    
    for fact in facts:
        fact = fact.strip()
        
        # Skip comments and empty lines
        if not fact or fact.startswith("%"):
            filtered.append(fact)
            continue
        
        # Check for time/1 fact - skip these entirely, we'll regenerate them
        time_match = time_pattern.match(fact)
        if time_match:
            time_val = int(time_match.group(1))
            if time_scope.is_time_in_scope(time_val):
                filtered.append(fact)
            # Skip facts outside scope (silently)
            continue
        
        # Check for event_time/2 and other time-indexed facts
        if "event_time(" in fact or "event_order(" in fact:
            # Extract time from format: event_time(eN, T).
            match = re.search(r'\(e(\d+),\s*(\d+)\)', fact)
            if match:
                time_val = int(match.group(2))
                if time_scope.is_time_in_scope(time_val):
                    filtered.append(fact)
                continue
        
        # For other facts, include them (entity facts, relationships, etc.)
        filtered.append(fact)
    
    return filtered
