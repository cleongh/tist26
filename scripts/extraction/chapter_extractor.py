"""
Chapter extraction for engine-based evaluation.

Standalone version for use with engine modules.
"""

import json
import re
from typing import Any, Dict, Optional, Tuple

from .prompts import ENGINE_EXTRACTION_PROMPT
from .extractors import extract_chapter_split
from .entity_registry import EntityRegistry
from .relationship_normalizer import RelationshipNormalizer
from .event_normalizer import EventNormalizer
from ..state.logging import log


def structure_chapter_standalone(
    chapter_text: str, 
    api_client,
    known_characters_json: str = "(No characters established yet)",
    known_relationships_json: str = "(No relationships established yet)",
    known_character_states_json: str = "(No character states established yet)",
    use_split_extraction: bool = False,
    use_entity_registry: bool = True,
    use_relationship_normalizer: bool = True,
    use_event_normalizer: bool = True,
    timeout: int = 300,
    known_characters_list: str = "(No characters established yet)",
    known_locations_list: str = "(No locations established yet)",
    known_items_with_states: str = "(No items established yet)",
) -> Tuple[Dict[str, Any], Optional[EntityRegistry], Optional[RelationshipNormalizer], Optional[EventNormalizer]]:
    """
    Structure a chapter using LLM extraction.
    
    Standalone version for use with engine modules.
    Uses the comprehensive extraction prompt with relationship and behavior detection.
    
    Phase 3: Accepts continuity context parameters for prompt injection.
    Phase 2: Optionally uses four-function split extraction pipeline.
    Phase 3 (EntityRegistry): Optionally validates entities with EntityRegistry.
    Phase 4 (RelationshipNormalizer): Optionally normalizes relationships.
    Phase 5 (EventNormalizer): Optionally validates events strictly.
    
    Args:
        chapter_text: The chapter text to extract from
        api_client: API client for LLM calls
        known_characters_json: JSON string of known characters and aliases
        known_relationships_json: JSON string of known relationships
        known_character_states_json: JSON string of known character states
        use_split_extraction: If True, use Phase 2 four-function pipeline
        use_entity_registry: If True, build and use EntityRegistry for validation
        use_relationship_normalizer: If True, build and use RelationshipNormalizer
        use_event_normalizer: If True, build and use EventNormalizer
        timeout: Timeout for LLM API calls in seconds
        known_characters_list: Formatted string of known character IDs from previous chapters
        known_locations_list: Formatted string of known location IDs from previous chapters
        known_items_with_states: Formatted string of known item IDs and states from previous chapters
        
    Returns:
        Tuple of (extracted data, EntityRegistry, RelationshipNormalizer, EventNormalizer)
        Any normalizer may be None if disabled or using single-call extraction.
    """
    # Phase 2: Use split extraction if requested
    if use_split_extraction:
        return extract_chapter_split(
            chapter_text,
            api_client,
            use_entity_registry,
            use_relationship_normalizer,
            use_event_normalizer,
            timeout=timeout,
            known_characters_list=known_characters_list,
            known_locations_list=known_locations_list,
            known_items_with_states=known_items_with_states,
        )
    
    # Original single-call extraction (no EntityRegistry or normalizers)
    prompt = ENGINE_EXTRACTION_PROMPT.format(
        chapter_text=chapter_text,
        known_characters_json=known_characters_json,
        known_relationships_json=known_relationships_json,
        known_character_states_json=known_character_states_json,
    )

    try:
        response = api_client.extract(prompt, max_tokens=8192, timeout=timeout)
        
        # Parse JSON response
        cleaned = re.sub(r'```json\s*', '', response)
        cleaned = re.sub(r'```\s*', '', cleaned)
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group()), None, None, None
    except Exception as e:
        log(f"Structure extraction failed: {e}", "WARN")
    
    return {"entities": {}, "events": [], "initial_rules": []}, None, None, None
