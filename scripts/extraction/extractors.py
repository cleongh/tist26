"""
Phase 2: Split extraction functions.
Phase 3: Entity Registry for canonical entity management.
Phase 4: Relationship normalization with group expansion.
Phase 5: Event normalization with strict validation.

Each function calls the LLM independently with the full chapter text.
The merged output is identical to the original single-call extraction.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .prompts import (
    EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT,
    EXTRACT_ITEMS_PROMPT,
    EXTRACT_RELATIONSHIPS_PROMPT,
    EXTRACT_EVENTS_PROMPT,
)
from .entity_registry import EntityRegistry, ValidationWarning
from .relationship_normalizer import RelationshipNormalizer, NormalizationResult
from .event_normalizer import EventNormalizer, EventNormalizationResult
from ..state.logging import log


def _parse_json_response(response: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, handling markdown and think tags.
    
    This is the same parsing logic used in the original extraction.
    """
    # Remove markdown code blocks
    cleaned = re.sub(r'```json\s*', '', response)
    cleaned = re.sub(r'```\s*', '', cleaned)
    # Remove think tags
    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
    
    # Find JSON object
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    
    return {}


def extract_characters_and_locations(chapter_text: str, api_client) -> Dict[str, Any]:
    """
    Extract characters and locations from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        
    Returns:
        Dict with "characters" and "locations" lists
    """
    prompt = EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT.format(chapter_text=chapter_text)
    
    try:
        response = api_client.extract(prompt, max_tokens=4096, timeout=120)
        result = _parse_json_response(response)
        
        # Ensure expected structure
        return {
            "characters": result.get("characters", []),
            "locations": result.get("locations", []),
        }
    except Exception as e:
        log(f"Character/location extraction failed: {e}", "WARN")
        return {"characters": [], "locations": []}


def extract_items(chapter_text: str, api_client) -> Dict[str, Any]:
    """
    Extract items from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        
    Returns:
        Dict with "items" list
    """
    prompt = EXTRACT_ITEMS_PROMPT.format(chapter_text=chapter_text)
    
    try:
        response = api_client.extract(prompt, max_tokens=2048, timeout=60)
        result = _parse_json_response(response)
        
        return {
            "items": result.get("items", []),
        }
    except Exception as e:
        log(f"Item extraction failed: {e}", "WARN")
        return {"items": []}


def extract_relationships(chapter_text: str, api_client) -> Dict[str, Any]:
    """
    Extract relationships and initial rules from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        
    Returns:
        Dict with "relationships" and "initial_rules" lists
    """
    prompt = EXTRACT_RELATIONSHIPS_PROMPT.format(chapter_text=chapter_text)
    
    try:
        response = api_client.extract(prompt, max_tokens=2048, timeout=60)
        result = _parse_json_response(response)
        
        return {
            "relationships": result.get("relationships", []),
            "initial_rules": result.get("initial_rules", []),
        }
    except Exception as e:
        log(f"Relationship extraction failed: {e}", "WARN")
        return {"relationships": [], "initial_rules": []}


def extract_events(chapter_text: str, api_client) -> Dict[str, Any]:
    """
    Extract events from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        
    Returns:
        Dict with "events" list
    """
    prompt = EXTRACT_EVENTS_PROMPT.format(chapter_text=chapter_text)
    
    try:
        response = api_client.extract(prompt, max_tokens=4096, timeout=120)
        result = _parse_json_response(response)
        
        return {
            "events": result.get("events", []),
        }
    except Exception as e:
        log(f"Event extraction failed: {e}", "WARN")
        return {"events": []}


def merge_extractions(
    chars_locs: Dict[str, Any],
    items: Dict[str, Any],
    relationships: Dict[str, Any],
    events: Dict[str, Any],
    registry: Optional[EntityRegistry] = None,
    rel_normalizer: Optional[RelationshipNormalizer] = None,
    event_normalizer: Optional[EventNormalizer] = None,
) -> Tuple[Dict[str, Any], Optional[EventNormalizationResult]]:
    """
    Merge the four extraction results into the unified output format.
    
    If an EntityRegistry is provided (Phase 3), relationships and events
    are validated against it. Unknown entity references generate warnings.
    
    If a RelationshipNormalizer is provided (Phase 4), relationships are
    also normalized: group expansion, deduplication, conflict detection.
    
    If an EventNormalizer is provided (Phase 5), events are strictly validated:
    - agent MUST exist, patient/location CAN be null
    - Invalid events are dropped
    - event_time is generated automatically
    
    The output format matches the original single-call extraction exactly:
    {
        "entities": {
            "characters": [...],
            "locations": [...],
            "items": [...],
            "relationships": [...]
        },
        "events": [...],
        "initial_rules": [...]
    }
    
    Args:
        chars_locs: Result from extract_characters_and_locations()
        items: Result from extract_items()
        relationships: Result from extract_relationships()
        events: Result from extract_events()
        registry: Optional EntityRegistry for validation (Phase 3)
        rel_normalizer: Optional RelationshipNormalizer for normalization (Phase 4)
        event_normalizer: Optional EventNormalizer for strict validation (Phase 5)
        
    Returns:
        Tuple of (merged extraction, EventNormalizationResult or None)
    """
    # Get raw data
    rel_list = relationships.get("relationships", [])
    rules_list = relationships.get("initial_rules", [])
    event_list = events.get("events", [])
    event_norm_result: Optional[EventNormalizationResult] = None
    
    # Phase 4: Use RelationshipNormalizer if provided
    if rel_normalizer is not None:
        log("  [Phase 4] Normalizing relationships with RelationshipNormalizer...")
        norm_result = rel_normalizer.normalize(rel_list, drop_invalid=True)
        rel_list = norm_result.relationships
        log(f"    -> {len(rel_list)} relationships after normalization")
        if norm_result.conflicts:
            log(f"    -> {len(norm_result.conflicts)} relationship conflicts detected (preserved for logic)")
            for conflict in norm_result.conflicts[:3]:
                log(f"      - {conflict.from_id} → {conflict.to_id}: {conflict.types}", "WARN")
            if len(norm_result.conflicts) > 3:
                log(f"      ... and {len(norm_result.conflicts) - 3} more", "WARN")
        
        log("  [Phase 4] Normalizing initial rules...")
        rules_list = rel_normalizer.normalize_initial_rules(rules_list, drop_invalid=True)
        log(f"    -> {len(rules_list)} initial rules after normalization")
    elif registry is not None:
        # Phase 3 fallback for relationships
        log("  [Phase 3] Validating relationships against EntityRegistry...")
        rel_list = registry.validate_relationships(rel_list, drop_invalid=True)
        log(f"    -> {len(rel_list)} relationships after validation")
        
        log("  [Phase 3] Validating initial rules against EntityRegistry...")
        rules_list = registry.validate_initial_rules(rules_list, drop_invalid=True)
        log(f"    -> {len(rules_list)} initial rules after validation")
    
    # Phase 5: Use EventNormalizer if provided (strict validation)
    if event_normalizer is not None:
        log("  [Phase 5] Normalizing events with EventNormalizer (strict validation)...")
        event_norm_result = event_normalizer.normalize(event_list, base_time=0, drop_invalid=True)
        event_list = event_norm_result.events
        log(f"    -> {len(event_list)} events validated, {len(event_norm_result.dropped_events)} dropped")
        causal_count = len(event_norm_result.get_causal_items())
        latent_count = len(event_norm_result.get_latent_items())
        if causal_count or latent_count:
            log(f"    -> Items: {causal_count} causal, {latent_count} latent")
    elif registry is not None:
        # Phase 3 fallback for events
        log("  [Phase 3] Validating events against EntityRegistry...")
        event_list = registry.validate_events(event_list, drop_invalid=False)
        log(f"    -> {len(event_list)} events after validation")
    
    # Log summary of warnings
    if registry is not None:
        warnings = registry.get_warnings()
        if warnings:
            log(f"  [Phase 3/4/5] {len(warnings)} validation warnings generated")
    
    merged = {
        "entities": {
            "characters": chars_locs.get("characters", []),
            "locations": chars_locs.get("locations", []),
            "items": items.get("items", []),
            "relationships": rel_list,
        },
        "events": event_list,
        "initial_rules": rules_list,
    }
    
    return merged, event_norm_result


def extract_chapter_split(
    chapter_text: str,
    api_client,
    use_entity_registry: bool = True,
    use_relationship_normalizer: bool = True,
    use_event_normalizer: bool = True,
) -> Tuple[Dict[str, Any], Optional[EntityRegistry], Optional[RelationshipNormalizer], Optional[EventNormalizer]]:
    """
    Extract structured data using the four-function pipeline.
    
    This function calls all four extractors in order and merges the results.
    The output is identical to the original single-call extraction.
    
    Phase 3: Optionally builds an EntityRegistry after phases 1 and 2,
    and uses it to validate phases 3 and 4.
    
    Phase 4: Optionally builds a RelationshipNormalizer for group expansion,
    deduplication, and conflict detection.
    
    Phase 5: Optionally builds an EventNormalizer for strict validation
    and event_time generation.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        use_entity_registry: If True, build and use EntityRegistry for validation
        use_relationship_normalizer: If True, build and use RelationshipNormalizer
        use_event_normalizer: If True, build and use EventNormalizer
        
    Returns:
        Tuple of (merged extraction, EntityRegistry, RelationshipNormalizer, EventNormalizer)
        Any normalizer may be None if disabled.
    """
    # Phase 1: Extract characters and locations
    log("  [Phase 2] Extracting characters and locations...")
    chars_locs = extract_characters_and_locations(chapter_text, api_client)
    log(f"    -> {len(chars_locs.get('characters', []))} characters, {len(chars_locs.get('locations', []))} locations")
    
    # Phase 2: Extract items
    log("  [Phase 2] Extracting items...")
    items = extract_items(chapter_text, api_client)
    log(f"    -> {len(items.get('items', []))} items")
    
    # Phase 3: Build EntityRegistry (if enabled)
    registry = None
    rel_normalizer = None
    event_normalizer = None
    if use_entity_registry:
        log("  [Phase 3] Building EntityRegistry...")
        registry = EntityRegistry()
        registry.register_characters(chars_locs.get("characters", []))
        registry.register_locations(chars_locs.get("locations", []))
        registry.register_items(items.get("items", []))
        stats = registry.get_statistics()
        log(f"    -> {stats['characters']} characters, {stats['locations']} locations, {stats['items']} items registered")
        log(f"    -> {stats['character_aliases']} character aliases, {stats['location_aliases']} location aliases, {stats['item_aliases']} item aliases")
        
        # Phase 4: Build RelationshipNormalizer (if enabled and registry exists)
        if use_relationship_normalizer:
            log("  [Phase 4] Building RelationshipNormalizer...")
            rel_normalizer = RelationshipNormalizer(registry)
            groups = rel_normalizer.get_groups()
            if groups:
                log(f"    -> {len(groups)} groups detected for expansion")
                for group_name, members in list(groups.items())[:3]:
                    log(f"      - {group_name}: {len(members)} members")
        
        # Phase 5: Build EventNormalizer (if enabled and registry exists)
        if use_event_normalizer:
            log("  [Phase 5] Building EventNormalizer...")
            event_normalizer = EventNormalizer(registry)
    
    # Phase 3 (extraction): Extract relationships
    log("  [Phase 2] Extracting relationships...")
    relationships = extract_relationships(chapter_text, api_client)
    log(f"    -> {len(relationships.get('relationships', []))} relationships, {len(relationships.get('initial_rules', []))} initial rules")
    
    # Phase 4 (extraction): Extract events
    log("  [Phase 2] Extracting events...")
    events = extract_events(chapter_text, api_client)
    log(f"    -> {len(events.get('events', []))} events")
    
    # Merge with validation and normalization
    merged, event_result = merge_extractions(
        chars_locs, items, relationships, events,
        registry, rel_normalizer, event_normalizer
    )
    
    return merged, registry, rel_normalizer, event_normalizer
