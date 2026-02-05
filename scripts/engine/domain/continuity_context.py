"""
Continuity Context - Represents accumulated continuity context for a chapter.

Phase 3: Continuity Context Injection
    - Context is built before each chapter extraction
    - Context is injected verbatim into the LLM prompt
    - LLM must not reinterpret or soften established facts

Per LOGIC_DESIGN.md Section 5 (Story Evaluation Pipeline):
    Each chapter is treated as a DELTA over the accumulated state.
    The LLM must respect the continuity context as ground truth.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ContinuityContext:
    """
    Represents the accumulated continuity context for a chapter.
    
    This context is injected into the LLM extraction prompt and
    must be treated as authoritative ground truth.
    """
    known_characters: List[Dict[str, Any]]  # [{canonical_id, name, aliases}]
    known_relationships: List[Dict[str, Any]]  # [{from, to, type}]
    known_character_states: List[Dict[str, Any]]  # [{character_id, state, emotion}]
    chapter_number: int
    
    def to_characters_json(self, indent: int = 2) -> str:
        """Format known characters as JSON for prompt injection."""
        if not self.known_characters:
            return "(No characters established yet)"
        return json.dumps(self.known_characters, indent=indent)
    
    def to_relationships_json(self, indent: int = 2) -> str:
        """Format known relationships as JSON for prompt injection."""
        if not self.known_relationships:
            return "(No relationships established yet)"
        return json.dumps(self.known_relationships, indent=indent)
    
    def to_character_states_json(self, indent: int = 2) -> str:
        """Format known character states as JSON for prompt injection."""
        if not self.known_character_states:
            return "(No character states established yet)"
        return json.dumps(self.known_character_states, indent=indent)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chapter_number": self.chapter_number,
            "known_characters": self.known_characters,
            "known_relationships": self.known_relationships,
            "known_character_states": self.known_character_states,
        }
    
    def is_empty(self) -> bool:
        """Check if context is empty (chapter 0)."""
        return (not self.known_characters and 
                not self.known_relationships and 
                not self.known_character_states)
