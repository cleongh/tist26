"""
Character and Location Extractor.

Extracts characters and locations from chapter text using LLM.
"""

import re
from typing import Any, Dict, List

from ..prompts import EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT
from ..json_utils import parse_llm_json
from ...state.logging import log


class CharacterAndLocationExtractor:
    """Extracts characters and locations from chapter text."""
    
    def __init__(self, api_client, timeout: int = 300):
        """
        Initialize the extractor.
        
        Args:
            api_client: API client for LLM calls
            timeout: Timeout for LLM API calls in seconds
        """
        self._api_client = api_client
        self._timeout = timeout
    
    def format_chapter_character_ids(self, characters: List[Dict[str, Any]]) -> str:
        """
        Format chapter character IDs for injection into prompts.
        
        Args:
            characters: List of character dicts from extraction (must have 'id' field)
            
        Returns:
            Formatted string with one character ID per line, or placeholder if empty.
        """
        ids = []
        for char in characters:
            char_id = char.get("id", "")
            if char_id:
                normalized = self._normalize_id(char_id)
                if normalized:
                    ids.append(normalized)
        
        if not ids:
            return "(No characters in this chapter)"
        
        return "\n".join(f"- {cid}" for cid in sorted(set(ids)))
    
    def format_chapter_location_ids(self, locations: List[Dict[str, Any]]) -> str:
        """
        Format chapter location IDs for injection into prompts.
        
        Args:
            locations: List of location dicts from extraction (must have 'id' field)
            
        Returns:
            Formatted string with one location ID per line, or placeholder if empty.
        """
        ids = []
        for loc in locations:
            loc_id = loc.get("id", "")
            if loc_id:
                normalized = self._normalize_id(loc_id)
                if normalized:
                    ids.append(normalized)
        
        if not ids:
            return "(No locations in this chapter)"
        
        return "\n".join(f"- {lid}" for lid in sorted(set(ids)))
    
    def extract(
        self,
        chapter_text: str,
        known_characters_list: str = "(No characters established yet)",
        known_locations_list: str = "(No locations established yet)",
    ) -> Dict[str, Any]:
        """
        Extract characters and locations from chapter text.
        
        Args:
            chapter_text: The full chapter text
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
            response = self._api_client.extract(prompt, max_tokens=4096, timeout=self._timeout)
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
    
    def _normalize_id(self, entity_id: str) -> str:
        """
        Normalize an entity ID to snake_case.
        
        Args:
            entity_id: Raw entity ID
            
        Returns:
            Normalized snake_case ID
        """
        normalized = re.sub(r'[^a-z0-9_]', '_', entity_id.lower())
        normalized = re.sub(r'_+', '_', normalized).strip('_')
        return normalized
