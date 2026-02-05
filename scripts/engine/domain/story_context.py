"""
Story Context - Context about a story that affects rule interpretation.

Used to identify when violations should be treated as story exceptions
rather than actual errors.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class StoryContext:
    """
    Context about a story that affects rule interpretation.
    
    Used to identify when violations should be treated as story exceptions
    rather than actual errors.
    """
    story_id: str = ""
    is_fantasy: bool = False
    has_magic: bool = False
    has_teleportation: bool = False
    undead_characters: List[str] = field(default_factory=list)
    ghost_characters: List[str] = field(default_factory=list)
    immortal_characters: List[str] = field(default_factory=list)
    custom_exceptions: Dict[str, List[str]] = field(default_factory=dict)
