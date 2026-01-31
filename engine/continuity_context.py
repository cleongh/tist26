"""
Continuity Context Builder - Generates context for LLM extraction

Responsibilities:
    - Gather known characters with their aliases
    - Gather known relationships between characters
    - Gather known character states (alive/dead, emotions)
    - Format context as JSON for injection into extraction prompt
    - Mark context as authoritative and immutable

Per LOGIC_DESIGN.md Section 5 (Story Evaluation Pipeline):
    Each chapter is treated as a DELTA over the accumulated state.
    The LLM must respect the continuity context as ground truth.

Phase 3: Continuity Context Injection
    - Context is built before each chapter extraction
    - Context is injected verbatim into the LLM prompt
    - LLM must not reinterpret or soften established facts
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
import json

# Type hints for dependencies (avoid circular imports)
if False:  # TYPE_CHECKING
    from .state_manager import StateManager
    from .alias_resolver import AliasResolver


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


class ContinuityContextBuilder:
    """
    Builds continuity context from accumulated state.
    
    Gathers information from:
        - AliasResolver: known characters and their aliases
        - StateManager: relationships, character states, deaths
    
    The resulting context is injected into the LLM extraction prompt
    to ensure consistent character identification and relationship tracking.
    """
    
    def __init__(self):
        pass
    
    def build_context(
        self,
        state_manager: 'StateManager',
        alias_resolver: 'AliasResolver',
        chapter_number: int,
    ) -> ContinuityContext:
        """
        Build continuity context from accumulated state.
        
        This should be called BEFORE extracting each chapter (except chapter 0).
        
        Args:
            state_manager: StateManager with accumulated world state
            alias_resolver: AliasResolver with known character IDs and aliases
            chapter_number: Current chapter number (0-indexed)
            
        Returns:
            ContinuityContext with all known facts
        """
        known_characters = self._gather_known_characters(state_manager, alias_resolver)
        known_relationships = self._gather_known_relationships(state_manager)
        known_character_states = self._gather_known_character_states(state_manager)
        
        return ContinuityContext(
            known_characters=known_characters,
            known_relationships=known_relationships,
            known_character_states=known_character_states,
            chapter_number=chapter_number,
        )
    
    def _gather_known_characters(
        self,
        state_manager: 'StateManager',
        alias_resolver: 'AliasResolver',
    ) -> List[Dict[str, Any]]:
        """
        Gather known characters with their canonical IDs and aliases.
        
        Combines information from:
            - AliasResolver: canonical IDs and alias mappings
            - StateManager: entity metadata (name, traits)
        """
        characters = []
        
        # Get all known canonical character IDs from alias resolver
        alias_map = alias_resolver.get_alias_map()
        
        # Group by canonical ID
        canonical_ids = set(alias_map.values())
        
        for canonical_id in sorted(canonical_ids):
            # Get all aliases for this canonical ID
            aliases = alias_resolver.get_aliases(canonical_id)
            aliases_list = sorted(list(aliases - {canonical_id}))  # Exclude self
            
            # Get entity info from state manager if available
            entity = state_manager.persistent_entities.get(canonical_id)
            
            char_info = {
                "canonical_id": canonical_id,
                "aliases": aliases_list,
            }
            
            # Add name if different from canonical ID
            if entity and hasattr(entity, 'id'):
                # Try to derive readable name from canonical_id
                name = canonical_id.replace('_', ' ').title()
                if name != canonical_id:
                    char_info["name"] = name
            
            characters.append(char_info)
        
        return characters
    
    def _gather_known_relationships(
        self,
        state_manager: 'StateManager',
    ) -> List[Dict[str, Any]]:
        """
        Gather known relationships from accumulated state.
        
        Returns relationships in format:
            {"from": char_id, "to": char_id, "type": relationship_type}
        """
        relationships = []
        
        for (char1, char2), rel_type in state_manager.persistent_relationships.items():
            relationships.append({
                "from": char1,
                "to": char2,
                "type": rel_type,
            })
        
        return sorted(relationships, key=lambda r: (r["from"], r["to"]))
    
    def _gather_known_character_states(
        self,
        state_manager: 'StateManager',
    ) -> List[Dict[str, Any]]:
        """
        Gather known character states (alive/dead, emotions).
        
        Returns states in format:
            {"character_id": id, "state": "alive/dead", "emotion": emotion_or_null}
        """
        states = []
        seen_chars = set()
        
        # Dead characters
        for char_id in state_manager.persistent_dead:
            states.append({
                "character_id": char_id,
                "state": "dead",
                "emotion": None,
            })
            seen_chars.add(char_id)
        
        # Characters with emotions
        for char_id, emotion in state_manager.persistent_emotions.items():
            if char_id in seen_chars:
                # Update existing entry
                for state in states:
                    if state["character_id"] == char_id:
                        state["emotion"] = emotion
                        break
            else:
                states.append({
                    "character_id": char_id,
                    "state": "alive",
                    "emotion": emotion,
                })
                seen_chars.add(char_id)
        
        return sorted(states, key=lambda s: s["character_id"])


def build_continuity_context(
    state_manager: 'StateManager',
    alias_resolver: 'AliasResolver',
    chapter_number: int,
) -> ContinuityContext:
    """
    Convenience function to build continuity context.
    
    Args:
        state_manager: StateManager with accumulated world state
        alias_resolver: AliasResolver with known character IDs
        chapter_number: Current chapter number
        
    Returns:
        ContinuityContext ready for prompt injection
    """
    builder = ContinuityContextBuilder()
    return builder.build_context(state_manager, alias_resolver, chapter_number)
