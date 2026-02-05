"""
Context - Metadata about the persistent narrative context.

Phase 8.4: Memory Optimization
    - Tracks context state (loaded, dirty)
    - Tracks chapter progress and timestamps
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class Context:
    """
    Metadata about the persistent narrative context.
    
    Tracks:
        - Story identification
        - Chapter progress
        - Load/save state
        - Engine version
    """
    story_id: str = "unknown"
    created_at: str = ""
    last_updated_at: str = ""
    current_chapter: int = 0
    total_chapters_processed: int = 0
    engine_version: str = "0.8.0"
    is_loaded: bool = False
    is_dirty: bool = False
    
    def update(self, chapter: int) -> None:
        """Update metadata after processing a chapter."""
        self.last_updated_at = datetime.now().isoformat()
        self.current_chapter = chapter
        self.total_chapters_processed = max(self.total_chapters_processed, chapter)
        self.is_dirty = True
    
    def mark_loaded(self) -> None:
        """Mark context as loaded."""
        self.is_loaded = True
    
    def mark_dirty(self) -> None:
        """Mark context as having unsaved changes."""
        self.is_dirty = True
    
    def mark_clean(self) -> None:
        """Mark context as saved (no unsaved changes)."""
        self.is_dirty = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "current_chapter": self.current_chapter,
            "total_chapters_processed": self.total_chapters_processed,
            "engine_version": self.engine_version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Context":
        """Create Context from dictionary."""
        return cls(
            story_id=data.get("story_id", "unknown"),
            created_at=data.get("created_at", ""),
            last_updated_at=data.get("last_updated_at", ""),
            current_chapter=data.get("current_chapter", 0),
            total_chapters_processed=data.get("total_chapters_processed", 0),
            engine_version=data.get("engine_version", "0.8.0"),
        )
