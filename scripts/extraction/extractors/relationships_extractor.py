"""
Relationships Extractor.

Extracts relationships and initial rules from chapter text using LLM.
"""

from typing import Any, Dict

from ..prompts import EXTRACT_RELATIONSHIPS_PROMPT
from ..json_utils import parse_llm_json
from ...state.logging import log


class RelationshipsExtractor:
    """Extracts relationships and initial rules from chapter text."""
    
    def __init__(self, api_client, timeout: int = 300):
        """
        Initialize the extractor.
        
        Args:
            api_client: API client for LLM calls
            timeout: Timeout for LLM API calls in seconds
        """
        self._api_client = api_client
        self._timeout = timeout
    
    def extract(
        self,
        chapter_text: str,
        chapter_character_ids: str = "(No characters in this chapter)",
    ) -> Dict[str, Any]:
        """
        Extract relationships and initial rules from chapter text.
        
        Args:
            chapter_text: The full chapter text
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
            response = self._api_client.extract(prompt, max_tokens=2048, timeout=self._timeout)
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
