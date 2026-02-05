"""
Items Extractor.

Extracts items from chapter text using LLM.
"""

import re
from typing import Any, Dict, List

from ..prompts import EXTRACT_ITEMS_PROMPT
from ..json_utils import parse_llm_json
from ...state.logging import log


class ItemsExtractor:
    """Extracts items from chapter text."""
    
    def __init__(self, api_client, timeout: int = 300):
        """
        Initialize the extractor.
        
        Args:
            api_client: API client for LLM calls
            timeout: Timeout for LLM API calls in seconds
        """
        self._api_client = api_client
        self._timeout = timeout
    
    def format_chapter_item_ids(self, items: List[Dict[str, Any]]) -> str:
        """
        Format chapter item IDs for injection into prompts.
        
        Args:
            items: List of item dicts from extraction (must have 'id' field)
            
        Returns:
            Formatted string with one item ID per line, or placeholder if empty.
        """
        ids = []
        for item in items:
            item_id = item.get("id", "")
            if item_id:
                normalized = self._normalize_id(item_id)
                if normalized:
                    ids.append(normalized)
        
        if not ids:
            return "(No items in this chapter)"
        
        return "\n".join(f"- {iid}" for iid in sorted(set(ids)))
    
    def extract(
        self,
        chapter_text: str,
        known_items_with_states: str = "(No items established yet)",
    ) -> Dict[str, Any]:
        """
        Extract items from chapter text.
        
        Args:
            chapter_text: The full chapter text
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
            response = self._api_client.extract(prompt, max_tokens=2048, timeout=self._timeout)
        except Exception as e:
            log(f"Item extraction failed: {e}", "WARN")
            return default
        
        result, success = parse_llm_json(response, "items", default)
        if not success:
            return default
        
        return {
            "items": result.get("items", []),
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
