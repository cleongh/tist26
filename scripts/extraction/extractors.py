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
from .json_utils import parse_llm_json, parse_events_with_salvage
from .post_salvage_reconciler import reconcile_salvaged_events, ReconciliationResult
from .temporal_diagnostics import analyze_temporal_extraction, TemporalDiagnostic
from .extraction_diagnostics import (
    analyze_chapter_extraction,
    ChapterDiagnostic,
    EvidenceType,
)
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


def format_chapter_character_ids(characters: List[Dict[str, Any]]) -> str:
    """
    Format chapter character IDs for injection into the relationships prompt.
    
    Args:
        characters: List of character dicts from extraction (must have 'id' field)
        
    Returns:
        Formatted string with one character ID per line, or placeholder if empty.
    """
    # Extract and normalize IDs
    ids = []
    for char in characters:
        if not isinstance(char, dict):
            continue
        char_id = char.get("id", "")
        if char_id:
            # Normalize to snake_case
            normalized = re.sub(r'[^a-z0-9_]', '_', char_id.lower())
            normalized = re.sub(r'_+', '_', normalized).strip('_')
            if normalized:
                ids.append(normalized)
    
    if not ids:
        return "(No characters in this chapter)"
    
    # Sort for determinism
    return "\n".join(f"- {cid}" for cid in sorted(set(ids)))


def format_chapter_item_ids(items: List[Dict[str, Any]]) -> str:
    """
    Format chapter item IDs for injection into the events prompt.
    
    Args:
        items: List of item dicts from extraction (must have 'id' field)
        
    Returns:
        Formatted string with one item ID per line, or placeholder if empty.
    """
    ids = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id", "")
        if item_id:
            # Normalize to snake_case
            normalized = re.sub(r'[^a-z0-9_]', '_', item_id.lower())
            normalized = re.sub(r'_+', '_', normalized).strip('_')
            if normalized:
                ids.append(normalized)
    
    if not ids:
        return "(No items in this chapter)"
    
    # Sort for determinism
    return "\n".join(f"- {iid}" for iid in sorted(set(ids)))


def format_chapter_location_ids(locations: List[Dict[str, Any]]) -> str:
    """
    Format chapter location IDs for injection into the events prompt.
    
    Args:
        locations: List of location dicts from extraction (must have 'id' field)
        
    Returns:
        Formatted string with one location ID per line, or placeholder if empty.
    """
    ids = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        loc_id = loc.get("id", "")
        if loc_id:
            # Normalize to snake_case
            normalized = re.sub(r'[^a-z0-9_]', '_', loc_id.lower())
            normalized = re.sub(r'_+', '_', normalized).strip('_')
            if normalized:
                ids.append(normalized)
    
    if not ids:
        return "(No locations in this chapter)"
    
    # Sort for determinism
    return "\n".join(f"- {lid}" for lid in sorted(set(ids)))


def extract_characters_and_locations(
    chapter_text: str, 
    api_client, 
    timeout: int = 300,
    known_characters_list: str = "(No characters established yet)",
    known_locations_list: str = "(No locations established yet)",
) -> Dict[str, Any]:
    """
    Extract characters and locations from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        timeout: Timeout for LLM API call in seconds
        known_characters_list: Formatted string of known character IDs from previous chapters
        known_locations_list: Formatted string of known location IDs from previous chapters
        
    Returns:
        Dict with "characters" and "locations" lists
    """
    default = {"characters": [], "locations": []}
    prompt = EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT.format(
        chapter_text=chapter_text,
        known_characters_list=known_characters_list,
        known_locations_list=known_locations_list,
    )
    
    try:
        response = api_client.extract(prompt, max_tokens=4096, timeout=timeout)
    except Exception as e:
        log(f"Character/location extraction failed: {e}", "WARN")
        return default
    
    result, success = parse_llm_json(response, "characters_locations", default)
    if not success:
        return default
    
    return {
        "characters": result.get("characters", []),
        "locations": result.get("locations", []),
    }


def extract_items(
    chapter_text: str, 
    api_client, 
    timeout: int = 300,
    known_items_with_states: str = "(No items established yet)",
) -> Dict[str, Any]:
    """
    Extract items from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        timeout: Timeout for LLM API call in seconds
        known_items_with_states: Formatted string of known item IDs and states from previous chapters
        
    Returns:
        Dict with "items" list
    """
    default = {"items": []}
    prompt = EXTRACT_ITEMS_PROMPT.format(
        chapter_text=chapter_text,
        known_items_with_states=known_items_with_states,
    )
    
    try:
        response = api_client.extract(prompt, max_tokens=2048, timeout=timeout)
    except Exception as e:
        log(f"Item extraction failed: {e}", "WARN")
        return default
    
    result, success = parse_llm_json(response, "items", default)
    if not success:
        return default
    
    return {
        "items": result.get("items", []),
    }


def extract_relationships(
    chapter_text: str, 
    api_client, 
    timeout: int = 300,
    chapter_character_ids: str = "(No characters in this chapter)",
) -> Dict[str, Any]:
    """
    Extract relationships and initial rules from chapter text.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        timeout: Timeout for LLM API call in seconds
        chapter_character_ids: Formatted string of character IDs that appear in this chapter
        
    Returns:
        Dict with "relationships" and "initial_rules" lists
    """
    default = {"relationships": [], "initial_rules": []}
    prompt = EXTRACT_RELATIONSHIPS_PROMPT.format(
        chapter_text=chapter_text,
        chapter_character_ids=chapter_character_ids,
    )
    
    try:
        response = api_client.extract(prompt, max_tokens=2048, timeout=timeout)
    except Exception as e:
        log(f"Relationship extraction failed: {e}", "WARN")
        return default
    
    result, success = parse_llm_json(response, "relationships", default)
    if not success:
        return default
    
    return {
        "relationships": result.get("relationships", []),
        "initial_rules": result.get("initial_rules", []),
    }


def extract_events(
    chapter_text: str, 
    api_client, 
    timeout: int = 300,
    chapter_character_ids: str = "(No characters in this chapter)",
    chapter_item_ids: str = "(No items in this chapter)",
    chapter_location_ids: str = "(No locations in this chapter)",
    chapter_id: str = "unknown",
    enable_temporal_diagnostics: bool = True,
) -> Tuple[Dict[str, Any], bool, Optional[TemporalDiagnostic]]:
    """
    Extract events from chapter text.
    
    This function uses truncation salvage: if the LLM output is cut off
    mid-generation, it will attempt to recover any complete events
    that appear before the truncation point.
    
    Temporal diagnostics: If enabled, scans chapter text for temporal
    markers and emits a warning if temporal language is detected but
    no temporal predicates are extracted. Per LOGIC_DESIGN.md, this
    does NOT affect logic or block execution.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        timeout: Timeout for LLM API call in seconds
        chapter_character_ids: Formatted string of character IDs in this chapter (for agent/patient)
        chapter_item_ids: Formatted string of item IDs in this chapter (for patient)
        chapter_location_ids: Formatted string of location IDs in this chapter
        chapter_id: Chapter identifier for diagnostic logging
        enable_temporal_diagnostics: If True, analyze temporal extraction recall
        
    Returns:
        Tuple of (events_dict, was_salvaged, temporal_diagnostic):
        - events_dict: Dict with "events" and optional "temporal_constraints" lists
        - was_salvaged: True if truncation salvage was used
        - temporal_diagnostic: TemporalDiagnostic if diagnostics enabled, else None
    """
    default = {"events": [], "temporal_constraints": []}
    prompt = EXTRACT_EVENTS_PROMPT.format(
        chapter_text=chapter_text,
        chapter_character_ids=chapter_character_ids,
        chapter_item_ids=chapter_item_ids,
        chapter_location_ids=chapter_location_ids,
    )
    
    try:
        response = api_client.extract(prompt, max_tokens=6024, timeout=timeout)
    except Exception as e:
        log(f"Event extraction failed: {e}", "WARN")
        return default, False, None
    
    # Use salvage-enabled parsing for events
    result, success, was_salvaged = parse_events_with_salvage(response, default)
    
    if was_salvaged:
        log(f"  [Events] Recovered {len(result.get('events', []))} events from truncated output", "INFO")
    
    if not success:
        return default, False, None
    
    extraction_result = {
        "events": result.get("events", []),
        "temporal_constraints": result.get("temporal_constraints", []),
    }
    
    # Run temporal diagnostics if enabled
    temporal_diagnostic = None
    if enable_temporal_diagnostics:
        temporal_diagnostic = analyze_temporal_extraction(
            chapter_id=chapter_id,
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=True,
        )
    
    return extraction_result, was_salvaged, temporal_diagnostic


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
    timeout: int = 300,
    known_characters_list: str = "(No characters established yet)",
    known_locations_list: str = "(No locations established yet)",
    known_items_with_states: str = "(No items established yet)",
    chapter_id: str = "unknown",
    enable_temporal_diagnostics: bool = True,
    enable_extraction_diagnostics: bool = True,
) -> Tuple[Dict[str, Any], Optional[EntityRegistry], Optional[RelationshipNormalizer], Optional[EventNormalizer], Optional[TemporalDiagnostic], Optional[ChapterDiagnostic]]:
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
    
    Temporal Diagnostics: Detects when temporal language exists in chapter
    text but no temporal predicates are extracted. Per LOGIC_DESIGN.md,
    diagnostics do NOT affect logic or block execution.
    
    Extraction Diagnostics: Detects when narrative evidence (emotional,
    appearance, location, temporal) exists but is not promoted to structured
    predicates. Provides clear report of why certain errors could not fire.
    
    Args:
        chapter_text: The full chapter text
        api_client: API client for LLM calls
        use_entity_registry: If True, build and use EntityRegistry for validation
        use_relationship_normalizer: If True, build and use RelationshipNormalizer
        use_event_normalizer: If True, build and use EventNormalizer
        timeout: Timeout for LLM API calls in seconds
        known_characters_list: Formatted string of known character IDs from previous chapters
        known_locations_list: Formatted string of known location IDs from previous chapters
        known_items_with_states: Formatted string of known item IDs and states from previous chapters
        chapter_id: Chapter identifier for diagnostic logging
        enable_temporal_diagnostics: If True, analyze temporal extraction recall
        enable_extraction_diagnostics: If True, analyze all evidence extraction recall
        
    Returns:
        Tuple of (merged extraction, EntityRegistry, RelationshipNormalizer, EventNormalizer, 
                  TemporalDiagnostic, ChapterDiagnostic)
        Any normalizer or diagnostic may be None if disabled.
    """
    # Phase 1: Extract characters and locations
    log("  [Phase 2] Extracting characters and locations...")
    chars_locs = extract_characters_and_locations(
        chapter_text, 
        api_client, 
        timeout=timeout,
        known_characters_list=known_characters_list,
        known_locations_list=known_locations_list,
    )
    log(f"    -> {len(chars_locs.get('characters', []))} characters, {len(chars_locs.get('locations', []))} locations")
    
    # Phase 2: Extract items
    log("  [Phase 2] Extracting items...")
    items = extract_items(
        chapter_text, 
        api_client, 
        timeout=timeout,
        known_items_with_states=known_items_with_states,
    )
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
    # Use character IDs from this chapter's extraction (not global registry)
    chapter_character_ids = format_chapter_character_ids(chars_locs.get("characters", []))
    log("  [Phase 2] Extracting relationships...")
    relationships = extract_relationships(
        chapter_text, 
        api_client, 
        timeout=timeout,
        chapter_character_ids=chapter_character_ids,
    )
    log(f"    -> {len(relationships.get('relationships', []))} relationships, {len(relationships.get('initial_rules', []))} initial rules")
    
    # Phase 4 (extraction): Extract events
    # Use entity IDs from this chapter's extraction for fully grounded events
    chapter_item_ids = format_chapter_item_ids(items.get("items", []))
    chapter_location_ids = format_chapter_location_ids(chars_locs.get("locations", []))
    log("  [Phase 2] Extracting events...")
    events, was_salvaged, temporal_diagnostic = extract_events(
        chapter_text, 
        api_client, 
        timeout=timeout,
        chapter_character_ids=chapter_character_ids,
        chapter_item_ids=chapter_item_ids,
        chapter_location_ids=chapter_location_ids,
        chapter_id=chapter_id,
        enable_temporal_diagnostics=enable_temporal_diagnostics,
    )
    log(f"    -> {len(events.get('events', []))} events, {len(events.get('temporal_constraints', []))} temporal constraints")
    
    # Post-salvage reconciliation: run ONLY if events were salvaged
    # This attempts to repair obvious entity reference issues before validation
    if was_salvaged and registry is not None and events.get("events"):
        log("  [Phase 4.5] Running post-salvage reconciliation...")
        original_count = len(events.get("events", []))
        reconciled_events, reconciliation_result = reconcile_salvaged_events(
            events.get("events", []),
            registry,
            rel_normalizer,
        )
        events = {"events": reconciled_events}
        if reconciliation_result.agent_remaps or reconciliation_result.location_remaps:
            log(
                f"    -> Reconciled {original_count} salvaged events: "
                f"{reconciliation_result.agent_remaps} agent remaps, "
                f"{reconciliation_result.location_remaps} location remaps, "
                f"{reconciliation_result.expanded_count} expanded"
            )
    
    # Merge with validation and normalization
    merged, event_result = merge_extractions(
        chars_locs, items, relationships, events,
        registry, rel_normalizer, event_normalizer
    )
    
    # Run extraction diagnostics if enabled
    extraction_diagnostic = None
    if enable_extraction_diagnostics:
        extraction_diagnostic = analyze_chapter_extraction(
            chapter_id=chapter_id,
            chapter_text=chapter_text,
            extraction_result=merged,
            emit_warnings=True,
        )
    
    return merged, registry, rel_normalizer, event_normalizer, temporal_diagnostic, extraction_diagnostic
