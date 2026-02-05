"""
LLM prompts for narrative analysis.

Each prompt is stored in its own file for better maintainability.
"""

from .llm_system_message_prompt import LLM_SYSTEM_MESSAGE
from .llm_lint_prompt import LLM_LINT_PROMPT
from .logic_unified_extraction_prompt import UNIFIED_EXTRACTION_PROMPT
from .logic_engine_unified_extraction_prompt import ENGINE_EXTRACTION_PROMPT
from .logic_characters_and_locations_prompt import EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT
from .logic_items_prompt import EXTRACT_ITEMS_PROMPT
from .logic_relationships_prompt import EXTRACT_RELATIONSHIPS_PROMPT
from .logic_events_prompt import EXTRACT_EVENTS_PROMPT

__all__ = [
    "LLM_SYSTEM_MESSAGE",
    "LLM_LINT_PROMPT",
    "UNIFIED_EXTRACTION_PROMPT",
    "ENGINE_EXTRACTION_PROMPT",
    "EXTRACT_CHARACTERS_AND_LOCATIONS_PROMPT",
    "EXTRACT_ITEMS_PROMPT",
    "EXTRACT_RELATIONSHIPS_PROMPT",
    "EXTRACT_EVENTS_PROMPT",
]
