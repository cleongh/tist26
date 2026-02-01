"""
Post-Salvage Reconciler for Events.

This module provides a conservative reconciliation step that runs AFTER JSON
salvage but BEFORE EventNormalizer validation. Its purpose is to repair
obvious, safe mapping issues in salvaged events without weakening ID control.

Context:
- Salvaged events often reference entities not present in the chapter EntityRegistry.
- EventNormalizer correctly drops such events, but this can result in entire chapters
  having 0 validated events (e.g., 69 salvaged → 0 valid).
- We want to reconcile ONLY obvious, safe cases without creating new entities.

Reconciliation strategies:
1. Agent reconciliation:
   - If agent is a plural/group token (e.g., "dursleys"):
     - Check if all known members of that group exist in EntityRegistry.
     - If so, expand into multiple events (one per member) OR
       map to a canonical representative if only one member exists.
   - If no safe mapping exists, leave unchanged.

2. Location reconciliation:
   - If location is not found in EntityRegistry:
     - Attempt alias resolution (existing EntityRegistry resolver).
     - Attempt containment resolution (sub-location name → known container).
   - If still unresolved, leave unchanged.

Per LOGIC_DESIGN.md:
- No new entities are created
- No fuzzy matching is used
- Any reconciliation is logged
- EventNormalizer validation rules remain unchanged
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .entity_registry import EntityRegistry, _normalize_id
from .relationship_normalizer import RelationshipNormalizer
from ..state.logging import log


@dataclass
class ReconciliationResult:
    """Result of post-salvage reconciliation."""
    original_count: int
    reconciled_count: int
    expanded_count: int  # Events created from group expansion
    agent_remaps: int    # Agents successfully remapped
    location_remaps: int # Locations successfully remapped
    unchanged_count: int # Events that couldn't be reconciled
    events: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_count": self.original_count,
            "reconciled_count": self.reconciled_count,
            "expanded_count": self.expanded_count,
            "agent_remaps": self.agent_remaps,
            "location_remaps": self.location_remaps,
            "unchanged_count": self.unchanged_count,
        }


# Common plural/group suffixes and patterns
GROUP_PATTERNS = frozenset({
    "s",      # dursleys, potters
    "es",     # weasleys (when base ends in y)
    "family", # the_dursley_family
    "group",  # the_group
    "team",   # the_team
    "all",    # all_of_them
    "both",   # both_of_them
    "they",   # they
    "them",   # them
})

# Known group tokens that should map to family groups
KNOWN_GROUP_TOKENS = {
    "dursleys": "dursley",
    "potters": "potter",
    "weasleys": "weasley",
    "malfoys": "malfoy",
    "grangers": "granger",
}


class PostSalvageReconciler:
    """
    Reconciles salvaged events before EventNormalizer validation.
    
    This class provides conservative reconciliation for events that were
    recovered from truncated/malformed LLM output. It attempts to fix
    obvious issues without creating new entities or using fuzzy matching.
    
    Usage:
        reconciler = PostSalvageReconciler(entity_registry, relationship_normalizer)
        result = reconciler.reconcile(salvaged_events)
        # result.events can then be passed to EventNormalizer
    """
    
    def __init__(
        self,
        registry: EntityRegistry,
        rel_normalizer: Optional[RelationshipNormalizer] = None,
    ):
        """
        Initialize the reconciler.
        
        Args:
            registry: EntityRegistry with registered characters, locations, items
            rel_normalizer: Optional RelationshipNormalizer for group definitions
        """
        self._registry = registry
        self._rel_normalizer = rel_normalizer
        
        # Build group mappings from RelationshipNormalizer if available
        self._groups: Dict[str, Set[str]] = {}
        if rel_normalizer is not None:
            self._groups = rel_normalizer.get_groups()
        
        # Build family-based groups from character data
        self._build_family_groups()
    
    def _build_family_groups(self) -> None:
        """
        Build family group mappings from character data.
        
        This identifies characters that share a family name and creates
        mappings from plural forms (e.g., "dursleys") to the family members.
        """
        # Group characters by family name
        family_members: Dict[str, Set[str]] = {}
        
        for canonical_id in self._registry.get_all_character_ids():
            char_data = self._registry.get_character(canonical_id)
            if not char_data:
                continue
            
            # Extract family name from canonical_id
            parts = canonical_id.split("_")
            if len(parts) >= 2:
                # Last part is often the family name
                family_name = parts[-1]
                if family_name not in family_members:
                    family_members[family_name] = set()
                family_members[family_name].add(canonical_id)
            
            # Also check aliases for family patterns
            for alias in char_data.get("aliases", []):
                alias_norm = _normalize_id(alias)
                for token, family_base in KNOWN_GROUP_TOKENS.items():
                    if token in alias_norm or alias_norm.startswith(family_base):
                        if family_base not in family_members:
                            family_members[family_base] = set()
                        family_members[family_base].add(canonical_id)
        
        # Create plural form mappings for families with 2+ members
        for family_name, members in family_members.items():
            if len(members) >= 2:
                # Create plural form key
                plural_key = family_name + "s"
                if plural_key not in self._groups:
                    self._groups[plural_key] = members
                
                # Also try common patterns
                the_key = "the_" + plural_key
                if the_key not in self._groups:
                    self._groups[the_key] = members
    
    def _is_group_token(self, identifier: str) -> bool:
        """
        Check if an identifier looks like a group/plural reference.
        
        Args:
            identifier: The identifier to check
            
        Returns:
            True if this looks like a group reference
        """
        if not identifier:
            return False
        
        normalized = _normalize_id(identifier)
        
        # Check direct group mappings
        if normalized in self._groups:
            return True
        
        # Check known group tokens
        if normalized in KNOWN_GROUP_TOKENS:
            return True
        
        # Check if it ends with a known plural pattern
        for pattern in ["s", "es"]:
            if normalized.endswith(pattern) and len(normalized) > len(pattern) + 2:
                base = normalized[:-len(pattern)]
                if base in self._groups or f"the_{normalized}" in self._groups:
                    return True
        
        return False
    
    def _get_group_members(self, identifier: str) -> Optional[Set[str]]:
        """
        Get the members of a group identifier.
        
        Args:
            identifier: The group identifier (e.g., "dursleys")
            
        Returns:
            Set of canonical character IDs, or None if not a known group
        """
        if not identifier:
            return None
        
        normalized = _normalize_id(identifier)
        
        # Direct lookup
        if normalized in self._groups:
            return self._groups[normalized].copy()
        
        # Try known group token mappings
        if normalized in KNOWN_GROUP_TOKENS:
            family_base = KNOWN_GROUP_TOKENS[normalized]
            # Look for family_base + "s" in groups
            plural_key = family_base + "s"
            if plural_key in self._groups:
                return self._groups[plural_key].copy()
            # Try the_family_base + "s"
            the_key = "the_" + plural_key
            if the_key in self._groups:
                return self._groups[the_key].copy()
        
        # Try with "the_" prefix
        the_key = "the_" + normalized
        if the_key in self._groups:
            return self._groups[the_key].copy()
        
        return None
    
    def _reconcile_agent(
        self,
        event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Reconcile the agent field of an event.
        
        If the agent is a group token and all members exist in the registry,
        either:
        - Expand to multiple events (one per member)
        - Map to a single representative (if only one member)
        
        Args:
            event: The event to reconcile
            
        Returns:
            List of events (may be multiple if expanded, single if remapped, 
            or original if no reconciliation possible)
        """
        agent = event.get("agent", "")
        
        if not agent:
            return [event]
        
        # First, try standard resolution
        canonical = self._registry.resolve_character(agent)
        if canonical:
            # Agent is already valid - just normalize it
            if agent != canonical:
                event = event.copy()
                event["agent"] = canonical
            return [event]
        
        # Agent not found - check if it's a group token
        members = self._get_group_members(agent)
        
        if members:
            # Verify all members exist in registry
            valid_members = set()
            for member in members:
                if self._registry.resolve_character(member):
                    valid_members.add(member)
            
            if not valid_members:
                # No valid members - can't reconcile
                return [event]
            
            if len(valid_members) == 1:
                # Single valid member - remap to that member
                event = event.copy()
                event["agent"] = list(valid_members)[0]
                event["_reconciled"] = True
                event["_original_agent"] = agent
                event["_reconciliation_type"] = "group_to_single"
                log(f"    [PostSalvageReconciler] Remapped agent '{agent}' → '{event['agent']}'", "DEBUG")
                return [event]
            
            # Multiple valid members - expand into multiple events
            expanded_events = []
            for member in sorted(valid_members):
                new_event = event.copy()
                new_event["agent"] = member
                new_event["_reconciled"] = True
                new_event["_original_agent"] = agent
                new_event["_reconciliation_type"] = "group_expansion"
                expanded_events.append(new_event)
            
            log(
                f"    [PostSalvageReconciler] Expanded agent '{agent}' → "
                f"{len(expanded_events)} events ({', '.join(sorted(valid_members))})",
                "DEBUG"
            )
            return expanded_events
        
        # Not a group token - leave unchanged
        return [event]
    
    def _reconcile_location(
        self,
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Reconcile the location field of an event.
        
        Attempts:
        1. Standard alias resolution via EntityRegistry
        2. Containment-based resolution (sub-location name → known container)
        
        Args:
            event: The event to reconcile
            
        Returns:
            Event with reconciled location (or unchanged if no reconciliation)
        """
        location = event.get("location")
        
        if not location:
            return event
        
        # First, try standard resolution
        canonical = self._registry.resolve_location(location)
        if canonical:
            # Location is valid - normalize it
            if location != canonical:
                event = event.copy()
                event["location"] = canonical
            return event
        
        # Location not found - try containment-based resolution
        normalized = _normalize_id(location)
        
        # Strategy 1: Check if location name is a suffix of a known location
        # e.g., "hall" might match "entrance_hall" or "great_hall"
        all_locations = self._registry.get_all_location_ids()
        
        # Exact suffix match (conservative)
        suffix_matches = []
        for loc_id in all_locations:
            if loc_id.endswith("_" + normalized):
                suffix_matches.append(loc_id)
        
        if len(suffix_matches) == 1:
            # Unique suffix match - safe to use
            event = event.copy()
            event["location"] = suffix_matches[0]
            event["_reconciled"] = True
            event["_original_location"] = location
            event["_reconciliation_type"] = "suffix_match"
            log(
                f"    [PostSalvageReconciler] Remapped location '{location}' → "
                f"'{event['location']}' (suffix match)",
                "DEBUG"
            )
            return event
        
        # Strategy 2: Check location data for containment info
        # Some locations may have a "contains" field with sub-location names
        for loc_id in all_locations:
            loc_data = self._registry.get_location(loc_id)
            if not loc_data:
                continue
            
            # Check if this location contains the missing sub-location
            contains = loc_data.get("contains", [])
            for sub_loc in contains:
                sub_norm = _normalize_id(sub_loc)
                if sub_norm == normalized:
                    # The missing location is a sub-location of this one
                    # Map to the container
                    event = event.copy()
                    event["location"] = loc_id
                    event["_reconciled"] = True
                    event["_original_location"] = location
                    event["_reconciliation_type"] = "containment_fallback"
                    log(
                        f"    [PostSalvageReconciler] Remapped location '{location}' → "
                        f"'{loc_id}' (containment fallback)",
                        "DEBUG"
                    )
                    return event
        
        # Strategy 3: Check if location is part of a known location name
        # e.g., "cupboard" might be part of "cupboard_under_the_stairs"
        prefix_matches = []
        for loc_id in all_locations:
            if loc_id.startswith(normalized + "_"):
                prefix_matches.append(loc_id)
        
        if len(prefix_matches) == 1:
            # Unique prefix match - safe to use
            event = event.copy()
            event["location"] = prefix_matches[0]
            event["_reconciled"] = True
            event["_original_location"] = location
            event["_reconciliation_type"] = "prefix_match"
            log(
                f"    [PostSalvageReconciler] Remapped location '{location}' → "
                f"'{event['location']}' (prefix match)",
                "DEBUG"
            )
            return event
        
        # No reconciliation possible - leave unchanged
        return event
    
    def reconcile(
        self,
        events: List[Dict[str, Any]],
    ) -> ReconciliationResult:
        """
        Reconcile a list of salvaged events.
        
        This is the main entry point for post-salvage reconciliation.
        Events are processed in order, with agent reconciliation potentially
        expanding a single event into multiple events.
        
        Args:
            events: List of salvaged events to reconcile
            
        Returns:
            ReconciliationResult with reconciled events and statistics
        """
        if not events:
            return ReconciliationResult(
                original_count=0,
                reconciled_count=0,
                expanded_count=0,
                agent_remaps=0,
                location_remaps=0,
                unchanged_count=0,
                events=[],
            )
        
        reconciled_events: List[Dict[str, Any]] = []
        agent_remaps = 0
        location_remaps = 0
        expanded_count = 0
        unchanged_count = 0
        
        for event in events:
            # Step 1: Agent reconciliation (may produce multiple events)
            agent_events = self._reconcile_agent(event)
            
            # Track agent reconciliation statistics
            if len(agent_events) > 1:
                expanded_count += len(agent_events) - 1
            elif len(agent_events) == 1:
                if agent_events[0].get("_reconciliation_type") in ("group_to_single", "group_expansion"):
                    agent_remaps += 1
            
            # Step 2: Location reconciliation for each event
            for evt in agent_events:
                reconciled_evt = self._reconcile_location(evt)
                
                if reconciled_evt.get("_reconciliation_type") in (
                    "suffix_match", "containment_fallback", "prefix_match"
                ):
                    location_remaps += 1
                
                # Track if event was unchanged
                if not reconciled_evt.get("_reconciled"):
                    unchanged_count += 1
                
                reconciled_events.append(reconciled_evt)
        
        result = ReconciliationResult(
            original_count=len(events),
            reconciled_count=len(reconciled_events),
            expanded_count=expanded_count,
            agent_remaps=agent_remaps,
            location_remaps=location_remaps,
            unchanged_count=unchanged_count,
            events=reconciled_events,
        )
        
        # Log summary if any reconciliation occurred
        if agent_remaps or location_remaps or expanded_count:
            log(
                f"    [PostSalvageReconciler] Reconciled: {agent_remaps} agents, "
                f"{location_remaps} locations, {expanded_count} expanded, "
                f"{unchanged_count} unchanged",
                "INFO"
            )
        
        return result


def reconcile_salvaged_events(
    events: List[Dict[str, Any]],
    registry: EntityRegistry,
    rel_normalizer: Optional[RelationshipNormalizer] = None,
) -> Tuple[List[Dict[str, Any]], ReconciliationResult]:
    """
    Convenience function to reconcile salvaged events.
    
    This is the main entry point for the post-salvage reconciliation step.
    It creates a PostSalvageReconciler and runs reconciliation.
    
    Args:
        events: List of salvaged events
        registry: EntityRegistry with registered entities
        rel_normalizer: Optional RelationshipNormalizer for group definitions
        
    Returns:
        Tuple of (reconciled_events, result)
    """
    reconciler = PostSalvageReconciler(registry, rel_normalizer)
    result = reconciler.reconcile(events)
    return result.events, result
