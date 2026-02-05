"""
Split Extraction Orchestrator.

Orchestrates the four-function extraction pipeline and merges results.
"""

from typing import Any, Dict, List, Optional, Tuple

from .extractors import (
    CharacterAndLocationExtractor,
    ItemsExtractor,
    RelationshipsExtractor,
    EventsExtractor,
)
from .entity_registry import EntityRegistry
from .relationship_normalizer import RelationshipNormalizer
from .event_normalizer import EventNormalizer, EventNormalizationResult
from .post_salvage_reconciler import reconcile_salvaged_events
from .temporal_diagnostics import TemporalDiagnostic
from .extraction_diagnostics import analyze_chapter_extraction, ChapterDiagnostic
from ..state.logging import log


class SplitExtraction:
    """Orchestrates the split extraction pipeline."""
    
    def __init__(
        self,
        api_client,
        timeout: int = 300,
        use_entity_registry: bool = True,
        use_relationship_normalizer: bool = True,
        use_event_normalizer: bool = True,
    ):
        """
        Initialize the split extraction orchestrator.
        
        Args:
            api_client: API client for LLM calls
            timeout: Timeout for LLM API calls in seconds
            use_entity_registry: If True, build and use EntityRegistry for validation
            use_relationship_normalizer: If True, build and use RelationshipNormalizer
            use_event_normalizer: If True, build and use EventNormalizer
        """
        self._api_client = api_client
        self._timeout = timeout
        self._use_entity_registry = use_entity_registry
        self._use_relationship_normalizer = use_relationship_normalizer
        self._use_event_normalizer = use_event_normalizer
        
        self._char_loc_extractor = CharacterAndLocationExtractor(api_client, timeout)
        self._items_extractor = ItemsExtractor(api_client, timeout)
        self._relationships_extractor = RelationshipsExtractor(api_client, timeout)
        self._events_extractor = EventsExtractor(api_client, timeout)
    
    def extract_chapter(
        self,
        chapter_text: str,
        known_characters_list: str = "(No characters established yet)",
        known_locations_list: str = "(No locations established yet)",
        known_items_with_states: str = "(No items established yet)",
        chapter_id: str = "unknown",
        enable_temporal_diagnostics: bool = True,
        enable_extraction_diagnostics: bool = True,
    ) -> Tuple[
        Dict[str, Any],
        Optional[EntityRegistry],
        Optional[RelationshipNormalizer],
        Optional[EventNormalizer],
        Optional[TemporalDiagnostic],
        Optional[ChapterDiagnostic],
    ]:
        """
        Extract structured data using the four-function pipeline.
        
        This method calls all four extractors in order and merges the results.
        
        Args:
            chapter_text: The full chapter text
            known_characters_list: Formatted string of known character IDs from previous chapters
            known_locations_list: Formatted string of known location IDs from previous chapters
            known_items_with_states: Formatted string of known item IDs and states
            chapter_id: Chapter identifier for diagnostic logging
            enable_temporal_diagnostics: If True, analyze temporal extraction recall
            enable_extraction_diagnostics: If True, analyze all evidence extraction recall
            
        Returns:
            Tuple of (merged extraction, EntityRegistry, RelationshipNormalizer,
                     EventNormalizer, TemporalDiagnostic, ChapterDiagnostic)
            Any normalizer or diagnostic may be None if disabled.
        """
        chars_locs = self._extract_characters_and_locations(
            chapter_text, known_characters_list, known_locations_list
        )
        
        items = self._extract_items(chapter_text, known_items_with_states)
        
        registry, rel_normalizer, event_normalizer = self._build_normalizers(
            chars_locs, items
        )
        
        chapter_character_ids = self._char_loc_extractor.format_chapter_character_ids(
            chars_locs.get("characters", [])
        )
        
        relationships = self._extract_relationships(chapter_text, chapter_character_ids)
        
        chapter_item_ids = self._items_extractor.format_chapter_item_ids(
            items.get("items", [])
        )
        chapter_location_ids = self._char_loc_extractor.format_chapter_location_ids(
            chars_locs.get("locations", [])
        )
        
        events, was_salvaged, temporal_diagnostic = self._extract_events(
            chapter_text,
            chapter_character_ids,
            chapter_item_ids,
            chapter_location_ids,
            chapter_id,
            enable_temporal_diagnostics,
        )
        
        events = self._run_post_salvage_reconciliation(
            events, was_salvaged, registry, rel_normalizer
        )
        
        merged, _ = self._merge_extractions(
            chars_locs, items, relationships, events,
            registry, rel_normalizer, event_normalizer
        )
        
        extraction_diagnostic = self._run_extraction_diagnostics(
            chapter_id, chapter_text, merged, enable_extraction_diagnostics
        )
        
        return (
            merged,
            registry,
            rel_normalizer,
            event_normalizer,
            temporal_diagnostic,
            extraction_diagnostic,
        )
    
    def _extract_characters_and_locations(
        self,
        chapter_text: str,
        known_characters_list: str,
        known_locations_list: str,
    ) -> Dict[str, Any]:
        """Extract characters and locations from chapter text."""
        log("  [Phase 2] Extracting characters and locations...")
        chars_locs = self._char_loc_extractor.extract(
            chapter_text,
            known_characters_list=known_characters_list,
            known_locations_list=known_locations_list,
        )
        log(f"    -> {len(chars_locs.get('characters', []))} characters, "
            f"{len(chars_locs.get('locations', []))} locations")
        return chars_locs
    
    def _extract_items(
        self,
        chapter_text: str,
        known_items_with_states: str,
    ) -> Dict[str, Any]:
        """Extract items from chapter text."""
        log("  [Phase 2] Extracting items...")
        items = self._items_extractor.extract(
            chapter_text,
            known_items_with_states=known_items_with_states,
        )
        log(f"    -> {len(items.get('items', []))} items")
        return items
    
    def _extract_relationships(
        self,
        chapter_text: str,
        chapter_character_ids: str,
    ) -> Dict[str, Any]:
        """Extract relationships from chapter text."""
        log("  [Phase 2] Extracting relationships...")
        relationships = self._relationships_extractor.extract(
            chapter_text,
            chapter_character_ids=chapter_character_ids,
        )
        log(f"    -> {len(relationships.get('relationships', []))} relationships, "
            f"{len(relationships.get('initial_rules', []))} initial rules")
        return relationships
    
    def _extract_events(
        self,
        chapter_text: str,
        chapter_character_ids: str,
        chapter_item_ids: str,
        chapter_location_ids: str,
        chapter_id: str,
        enable_temporal_diagnostics: bool,
    ) -> Tuple[Dict[str, Any], bool, Optional[TemporalDiagnostic]]:
        """Extract events from chapter text."""
        log("  [Phase 2] Extracting events...")
        events, was_salvaged, temporal_diagnostic = self._events_extractor.extract(
            chapter_text,
            chapter_character_ids=chapter_character_ids,
            chapter_item_ids=chapter_item_ids,
            chapter_location_ids=chapter_location_ids,
            chapter_id=chapter_id,
            enable_temporal_diagnostics=enable_temporal_diagnostics,
        )
        log(f"    -> {len(events.get('events', []))} events, "
            f"{len(events.get('temporal_constraints', []))} temporal constraints")
        return events, was_salvaged, temporal_diagnostic
    
    def _build_normalizers(
        self,
        chars_locs: Dict[str, Any],
        items: Dict[str, Any],
    ) -> Tuple[Optional[EntityRegistry], Optional[RelationshipNormalizer], Optional[EventNormalizer]]:
        """Build normalizers if enabled."""
        registry = None
        rel_normalizer = None
        event_normalizer = None
        
        if not self._use_entity_registry:
            return registry, rel_normalizer, event_normalizer
        
        log("  [Phase 3] Building EntityRegistry...")
        registry = EntityRegistry()
        registry.register_characters(chars_locs.get("characters", []))
        registry.register_locations(chars_locs.get("locations", []))
        registry.register_items(items.get("items", []))
        stats = registry.get_statistics()
        log(f"    -> {stats['characters']} characters, {stats['locations']} locations, "
            f"{stats['items']} items registered")
        log(f"    -> {stats['character_aliases']} character aliases, "
            f"{stats['location_aliases']} location aliases, "
            f"{stats['item_aliases']} item aliases")
        
        if self._use_relationship_normalizer:
            log("  [Phase 4] Building RelationshipNormalizer...")
            rel_normalizer = RelationshipNormalizer(registry)
            groups = rel_normalizer.get_groups()
            if groups:
                log(f"    -> {len(groups)} groups detected for expansion")
                for group_name, members in list(groups.items())[:3]:
                    log(f"      - {group_name}: {len(members)} members")
        
        if self._use_event_normalizer:
            log("  [Phase 5] Building EventNormalizer...")
            event_normalizer = EventNormalizer(registry)
        
        return registry, rel_normalizer, event_normalizer
    
    def _run_post_salvage_reconciliation(
        self,
        events: Dict[str, Any],
        was_salvaged: bool,
        registry: Optional[EntityRegistry],
        rel_normalizer: Optional[RelationshipNormalizer],
    ) -> Dict[str, Any]:
        """Run post-salvage reconciliation if events were salvaged."""
        if not was_salvaged or registry is None or not events.get("events"):
            return events
        
        log("  [Phase 4.5] Running post-salvage reconciliation...")
        original_count = len(events.get("events", []))
        reconciled_events, reconciliation_result = reconcile_salvaged_events(
            events.get("events", []),
            registry,
            rel_normalizer,
        )
        
        if reconciliation_result.agent_remaps or reconciliation_result.location_remaps:
            log(
                f"    -> Reconciled {original_count} salvaged events: "
                f"{reconciliation_result.agent_remaps} agent remaps, "
                f"{reconciliation_result.location_remaps} location remaps, "
                f"{reconciliation_result.expanded_count} expanded"
            )
        
        return {"events": reconciled_events, "temporal_constraints": events.get("temporal_constraints", [])}
    
    def _run_extraction_diagnostics(
        self,
        chapter_id: str,
        chapter_text: str,
        merged: Dict[str, Any],
        enable_extraction_diagnostics: bool,
    ) -> Optional[ChapterDiagnostic]:
        """Run extraction diagnostics if enabled."""
        if not enable_extraction_diagnostics:
            return None
        
        return analyze_chapter_extraction(
            chapter_id=chapter_id,
            chapter_text=chapter_text,
            extraction_result=merged,
            emit_warnings=True,
        )
    
    def _merge_extractions(
        self,
        chars_locs: Dict[str, Any],
        items: Dict[str, Any],
        relationships: Dict[str, Any],
        events: Dict[str, Any],
        registry: Optional[EntityRegistry],
        rel_normalizer: Optional[RelationshipNormalizer],
        event_normalizer: Optional[EventNormalizer],
    ) -> Tuple[Dict[str, Any], Optional[EventNormalizationResult]]:
        """
        Merge the four extraction results into the unified output format.
        
        Args:
            chars_locs: Result from character/location extraction
            items: Result from item extraction
            relationships: Result from relationship extraction
            events: Result from event extraction
            registry: Optional EntityRegistry for validation
            rel_normalizer: Optional RelationshipNormalizer for normalization
            event_normalizer: Optional EventNormalizer for strict validation
            
        Returns:
            Tuple of (merged extraction, EventNormalizationResult or None)
        """
        rel_list = relationships.get("relationships", [])
        rules_list = relationships.get("initial_rules", [])
        event_list = events.get("events", [])
        event_norm_result: Optional[EventNormalizationResult] = None
        
        rel_list, rules_list = self._normalize_relationships(
            rel_list, rules_list, registry, rel_normalizer
        )
        
        event_list, event_norm_result = self._normalize_events(
            event_list, registry, event_normalizer
        )
        
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
    
    def _normalize_relationships(
        self,
        rel_list: List[Dict[str, Any]],
        rules_list: List[Dict[str, Any]],
        registry: Optional[EntityRegistry],
        rel_normalizer: Optional[RelationshipNormalizer],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Normalize relationships using the appropriate normalizer."""
        if rel_normalizer is not None:
            log("  [Phase 4] Normalizing relationships with RelationshipNormalizer...")
            norm_result = rel_normalizer.normalize(rel_list, drop_invalid=True)
            rel_list = norm_result.relationships
            log(f"    -> {len(rel_list)} relationships after normalization")
            
            if norm_result.conflicts:
                log(f"    -> {len(norm_result.conflicts)} relationship conflicts detected")
                for conflict in norm_result.conflicts[:3]:
                    log(f"      - {conflict.from_id} → {conflict.to_id}: {conflict.types}", "WARN")
                if len(norm_result.conflicts) > 3:
                    log(f"      ... and {len(norm_result.conflicts) - 3} more", "WARN")
            
            log("  [Phase 4] Normalizing initial rules...")
            rules_list = rel_normalizer.normalize_initial_rules(rules_list, drop_invalid=True)
            log(f"    -> {len(rules_list)} initial rules after normalization")
        
        elif registry is not None:
            log("  [Phase 3] Validating relationships against EntityRegistry...")
            rel_list = registry.validate_relationships(rel_list, drop_invalid=True)
            log(f"    -> {len(rel_list)} relationships after validation")
            
            log("  [Phase 3] Validating initial rules against EntityRegistry...")
            rules_list = registry.validate_initial_rules(rules_list, drop_invalid=True)
            log(f"    -> {len(rules_list)} initial rules after validation")
        
        return rel_list, rules_list
    
    def _normalize_events(
        self,
        event_list: List[Dict[str, Any]],
        registry: Optional[EntityRegistry],
        event_normalizer: Optional[EventNormalizer],
    ) -> Tuple[List[Dict[str, Any]], Optional[EventNormalizationResult]]:
        """Normalize events using the appropriate normalizer."""
        event_norm_result: Optional[EventNormalizationResult] = None
        
        if event_normalizer is not None:
            log("  [Phase 5] Normalizing events with EventNormalizer (strict validation)...")
            event_norm_result = event_normalizer.normalize(event_list, base_time=0, drop_invalid=True)
            event_list = event_norm_result.events
            log(f"    -> {len(event_list)} events validated, "
                f"{len(event_norm_result.dropped_events)} dropped")
            
            causal_count = len(event_norm_result.get_causal_items())
            latent_count = len(event_norm_result.get_latent_items())
            if causal_count or latent_count:
                log(f"    -> Items: {causal_count} causal, {latent_count} latent")
        
        elif registry is not None:
            log("  [Phase 3] Validating events against EntityRegistry...")
            event_list = registry.validate_events(event_list, drop_invalid=False)
            log(f"    -> {len(event_list)} events after validation")
        
        return event_list, event_norm_result
