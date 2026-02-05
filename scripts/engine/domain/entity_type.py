"""
Entity Type - Valid entity types per LOGIC_DESIGN.md Section 3.2.

Entities: character(X), location(X), item(X)
Each entity has exactly one canonical ID.
"""

from enum import Enum


class EntityType(Enum):
    """Valid entity types per LOGIC_DESIGN.md Section 3.2."""
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
