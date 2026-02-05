"""
ASP Universe Stats - Statistics about ASP universe size for a single chapter.

Phase 8.8: Tracks entity counts to detect grounding explosion.
"""

import logging
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class ASPUniverseStats:
    """
    Statistics about ASP universe size for a single chapter.
    
    Tracks entity counts to detect grounding explosion.
    """
    chapter_num: int
    characters: int = 0
    items: int = 0
    locations: int = 0
    relationships: int = 0
    events: int = 0
    time_facts: int = 0
    total_facts: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'chapter': self.chapter_num,
            'characters': self.characters,
            'items': self.items,
            'locations': self.locations,
            'relationships': self.relationships,
            'events': self.events,
            'time_facts': self.time_facts,
            'total_facts': self.total_facts,
        }
    
    def log_summary(self) -> None:
        """Log a concise summary of universe stats."""
        logger.info(
            f"[ASP Ch.{self.chapter_num}] "
            f"chars={self.characters} items={self.items} locs={self.locations} "
            f"rels={self.relationships} events={self.events} time={self.time_facts} "
            f"total={self.total_facts}"
        )
