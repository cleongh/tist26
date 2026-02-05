"""
Events Extractor.

Extracts events from chapter text using LLM.
"""

from typing import Any, Dict, Optional, Tuple

from ..prompts import EXTRACT_EVENTS_PROMPT
from ..json_utils import parse_events_with_salvage
from ..temporal_diagnostics import analyze_temporal_extraction, TemporalDiagnostic
from ...state.logging import log


class EventsExtractor:
    """Extracts events from chapter text."""
    
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
        chapter_item_ids: str = "(No items in this chapter)",
        chapter_location_ids: str = "(No locations in this chapter)",
        chapter_id: str = "unknown",
        enable_temporal_diagnostics: bool = True,
    ) -> Tuple[Dict[str, Any], bool, Optional[TemporalDiagnostic]]:
        """
        Extract events from chapter text.
        
        This method uses truncation salvage: if the LLM output is cut off
        mid-generation, it will attempt to recover any complete events
        that appear before the truncation point.
        
        Temporal diagnostics: If enabled, scans chapter text for temporal
        markers and emits a warning if temporal language is detected but
        no temporal predicates are extracted.
        
        Args:
            chapter_text: The full chapter text
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
            response = self._api_client.extract(prompt, max_tokens=6024, timeout=self._timeout)
        except Exception as e:
            log(f"Event extraction failed: {e}", "WARN")
            return default, False, None
        
        result, success, was_salvaged = parse_events_with_salvage(response, default)
        
        if was_salvaged:
            log(f"  [Events] Recovered {len(result.get('events', []))} events from truncated output", "INFO")
        
        if not success:
            return default, False, None
        
        extraction_result = {
            "events": result.get("events", []),
            "temporal_constraints": result.get("temporal_constraints", []),
        }
        
        temporal_diagnostic = self._run_temporal_diagnostics(
            chapter_id,
            chapter_text,
            extraction_result,
            enable_temporal_diagnostics,
        )
        
        return extraction_result, was_salvaged, temporal_diagnostic
    
    def _run_temporal_diagnostics(
        self,
        chapter_id: str,
        chapter_text: str,
        extraction_result: Dict[str, Any],
        enable_temporal_diagnostics: bool,
    ) -> Optional[TemporalDiagnostic]:
        """
        Run temporal diagnostics if enabled.
        
        Args:
            chapter_id: Chapter identifier for diagnostic logging
            chapter_text: The full chapter text
            extraction_result: The extraction result dict
            enable_temporal_diagnostics: If True, analyze temporal extraction recall
            
        Returns:
            TemporalDiagnostic if diagnostics enabled, else None
        """
        if not enable_temporal_diagnostics:
            return None
        
        return analyze_temporal_extraction(
            chapter_id=chapter_id,
            chapter_text=chapter_text,
            extraction_result=extraction_result,
            emit_warning=True,
        )
