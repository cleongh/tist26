"""
Managers Module - Character and Location Alias Management

This module provides classes for managing canonical IDs and aliases
for characters and locations in the narrative logic engine.

Classes:
    - CharacterAliasManager: Character-specific alias management
    - LocationAliasManager: Location-specific alias management with containment
    - RelationshipManager: Relationship filtering and projection
    - PersistenceManager: Context persistence to disk
    - ConsultantsManager: Read-only context queries
    - RuleManager: Rule projection into ASP context

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
    - Logic-first architecture: ASP is the source of truth

Phase 2: These modules ensure consistent entity identity across chapters,
preventing issues like "uncle_vernon" vs "mr_dursley" referring to the same entity.
"""

from .character_alias_manager import (
    CharacterAliasManager,
    normalize_character_id,
    _LEGACY_CHARACTER_ALIASES,
)
from .location_alias_manager import LocationAliasManager
from .relationship_manager import RelationshipManager
from .persistence_manager import PersistenceManager
from .consultants_manager import ConsultantsManager
from .rule_manager import RuleManager

__all__ = [
    "CharacterAliasManager",
    "LocationAliasManager",
    "RelationshipManager",
    "PersistenceManager",
    "ConsultantsManager",
    "RuleManager",
    "normalize_character_id",
    "_LEGACY_CHARACTER_ALIASES",
]
