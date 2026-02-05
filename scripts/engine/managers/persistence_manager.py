"""
Persistence Manager - Handles file I/O for persistent narrative context.

Responsibilities:
    - Persist global narrative context to disk using JSON
    - Load-once / update-incrementally behavior
    - No memory growth from historical context
    - Atomic file writes

Per LOGIC_DESIGN.md Section 7.1 (Python Layer):
    Python is for orchestration, including state management.
    This module handles persistence, not reasoning.

Stored Context:
    - EntityRegistry (characters, locations, items with lifecycle)
    - ItemTracker registry (item states and Chekhov tracking)
    - Relationships (cross-chapter relationship state)
    - Metadata (chapter progress, timestamps, statistics)

Storage Design:
    - Single JSON file for deterministic serialization
    - Append/update based - no full rewrite each chapter
    - Human-readable format
    - WorldState is NOT stored (kept small and in-memory)

Phase 8.4: Memory Optimization
    - Load context once at start
    - Update incrementally after each chapter
    - FinalAnalyzer reads from persistent context
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..domain import Context

if TYPE_CHECKING:
    from ..state_manager import StateManager
    from ..item_tracker import ItemTracker

logger = logging.getLogger(__name__)


class PersistenceManager:
    """
    Manages file I/O for persistent narrative context.
    
    Provides:
        - Load-once behavior at start
        - Incremental updates after each chapter
        - JSON-based storage (human-readable)
        - Atomic file writes
    
    Does NOT:
        - Store WorldState snapshots
        - Store event sequences
        - Store ASP programs
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize persistence manager.
        
        Args:
            storage_dir: Directory for context files. If None, uses current directory.
        """
        self._storage_dir = Path(storage_dir) if storage_dir else Path(".")
        self._context_file: Optional[Path] = None
        
        # Context data (loaded from / saved to JSON)
        self._context: Context = Context()
        self._entity_registry_data: Dict[str, Any] = {}
        self._item_tracker_data: Dict[str, Any] = {}
        self._relationships: Dict[str, str] = {}  # (char1,char2) -> rel_type as string key
        self._dead_characters: List[str] = []
        self._emotions: Dict[str, str] = {}
        self._traits: Dict[str, str] = {}
        
        # Statistics
        self._load_count: int = 0
        self._save_count: int = 0
    
    @property
    def context(self) -> Context:
        """Get the context metadata."""
        return self._context
    
    @property
    def entity_registry_data(self) -> Dict[str, Any]:
        """Get entity registry data."""
        return self._entity_registry_data
    
    @property
    def item_tracker_data(self) -> Dict[str, Any]:
        """Get item tracker data."""
        return self._item_tracker_data
    
    @property
    def relationships(self) -> Dict[str, str]:
        """Get relationships data."""
        return self._relationships
    
    @property
    def dead_characters(self) -> List[str]:
        """Get dead characters list."""
        return self._dead_characters
    
    @property
    def emotions(self) -> Dict[str, str]:
        """Get emotions data."""
        return self._emotions
    
    @property
    def traits(self) -> Dict[str, str]:
        """Get traits data."""
        return self._traits
    
    def load_or_create(self, story_id: str) -> bool:
        """
        Load existing context or create new one.
        
        Args:
            story_id: Unique identifier for the story
            
        Returns:
            True if loaded existing, False if created new
        """
        self._context_file = self._storage_dir / f"{story_id}_context.json"
        
        if self._context_file.exists():
            return self._load()
        else:
            return self._create(story_id)
    
    def _create(self, story_id: str) -> bool:
        """Create new context file."""
        self._context = Context(
            story_id=story_id,
            created_at=datetime.now().isoformat(),
            last_updated_at=datetime.now().isoformat(),
        )
        self._entity_registry_data = {"entities": {}, "statistics": {}}
        self._item_tracker_data = {"items": {}, "statistics": {}}
        self._relationships = {}
        self._dead_characters = []
        self._emotions = {}
        self._traits = {}
        
        self._context.mark_loaded()
        self._context.mark_dirty()
        
        # Ensure directory exists
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created new context for story '{story_id}'")
        return False
    
    def _load(self) -> bool:
        """Load context from JSON file."""
        if not self._context_file or not self._context_file.exists():
            raise FileNotFoundError(f"Context file not found: {self._context_file}")
        
        try:
            with open(self._context_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._context = Context.from_dict(data.get("metadata", {}))
            self._entity_registry_data = data.get("entity_registry", {"entities": {}, "statistics": {}})
            self._item_tracker_data = data.get("item_tracker", {"items": {}, "statistics": {}})
            self._relationships = data.get("relationships", {})
            self._dead_characters = data.get("dead_characters", [])
            self._emotions = data.get("emotions", {})
            self._traits = data.get("traits", {})
            
            self._context.mark_loaded()
            self._context.mark_clean()
            self._load_count += 1
            
            logger.info(f"Loaded context from '{self._context_file}' "
                       f"(chapter {self._context.current_chapter})")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse context file: {e}")
            raise
    
    def save(self) -> None:
        """Save context to JSON file."""
        if not self._context_file:
            raise ValueError("No context file set. Call load_or_create first.")
        
        if not self._context.is_dirty:
            logger.debug("Context not dirty, skipping save")
            return
        
        data = {
            "metadata": self._context.to_dict(),
            "entity_registry": self._entity_registry_data,
            "item_tracker": self._item_tracker_data,
            "relationships": self._relationships,
            "dead_characters": self._dead_characters,
            "emotions": self._emotions,
            "traits": self._traits,
        }
        
        # Write atomically using temp file
        temp_file = self._context_file.with_suffix('.json.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, sort_keys=True)
            
            # Atomic rename
            temp_file.replace(self._context_file)
            
            self._context.mark_clean()
            self._save_count += 1
            
            logger.info(f"Saved context to '{self._context_file}'")
            
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def update_from_state_manager(self, state_manager: 'StateManager', chapter: int) -> None:
        """
        Update context from StateManager after processing a chapter.
        
        This is an incremental update - only changed data is updated.
        
        Args:
            state_manager: The StateManager instance
            chapter: Chapter number just processed
        """
        # Update context metadata
        self._context.update(chapter)
        
        # Update EntityRegistry data
        self._entity_registry_data = state_manager.entity_registry.to_dict()
        
        # Update relationships
        for (char1, char2), rel_type in state_manager.persistent_relationships.items():
            key = f"{char1},{char2}"
            self._relationships[key] = rel_type
        
        # Update dead characters
        self._dead_characters = list(state_manager.persistent_dead)
        
        # Update emotions
        self._emotions = dict(state_manager.persistent_emotions)
        
        # Update traits
        self._traits = dict(state_manager.persistent_traits)
    
    def update_from_item_tracker(self, item_tracker: 'ItemTracker', chapter: int) -> None:
        """
        Update context from ItemTracker after processing a chapter.
        
        Args:
            item_tracker: The ItemTracker instance
            chapter: Chapter number just processed
        """
        # Convert ItemTracker to serializable dict
        self._item_tracker_data = {
            "items": {
                item_id: item.to_dict() 
                for item_id, item in item_tracker._items.items()
            },
            "statistics": item_tracker.get_statistics(),
            "relevance_transitions": item_tracker.get_relevance_transitions(),
        }
        
        self._context.mark_dirty()
    
    def apply_to_state_manager(self, state_manager: 'StateManager') -> None:
        """
        Apply loaded context to StateManager.
        
        Used when resuming from a saved context.
        
        Args:
            state_manager: The StateManager to update
        """
        if not self._context.is_loaded:
            raise RuntimeError("Context not loaded. Call load_or_create first.")
        
        # Apply EntityRegistry
        if self._entity_registry_data.get("entities"):
            state_manager.entity_registry.load_from_dict(self._entity_registry_data)
        
        # Apply relationships
        for key, rel_type in self._relationships.items():
            parts = key.split(",")
            if len(parts) == 2:
                state_manager.persistent_relationships[(parts[0], parts[1])] = rel_type
        
        # Apply dead characters
        state_manager.persistent_dead = set(self._dead_characters)
        
        # Apply emotions
        state_manager.persistent_emotions = dict(self._emotions)
        
        # Apply traits
        state_manager.persistent_traits = dict(self._traits)
        
        logger.info(f"Applied context to StateManager (chapter {self._context.current_chapter})")
    
    def apply_to_item_tracker(self, item_tracker: 'ItemTracker') -> None:
        """
        Apply loaded context to ItemTracker.
        
        Used when resuming from a saved context.
        
        Args:
            item_tracker: The ItemTracker to update
        """
        if not self._context.is_loaded:
            raise RuntimeError("Context not loaded. Call load_or_create first.")
        
        # Import here to avoid circular imports
        from ..item_tracker import TrackedItem, ItemRelevance, ItemLifecycleState
        
        items_data = self._item_tracker_data.get("items", {})
        
        for item_id, item_data in items_data.items():
            item = TrackedItem(
                item_id=item_data["item_id"],
                name=item_data.get("name"),
                relevance=ItemRelevance(item_data.get("relevance", "background")),
                original_relevance=ItemRelevance(item_data.get("original_relevance", "background")),
                lifecycle_state=ItemLifecycleState(item_data.get("lifecycle_state", "introduced")),
                introduced_chapter=item_data.get("introduced_chapter", 0),
                last_mentioned_chapter=item_data.get("last_mentioned_chapter", 0),
                promoted_to_causal_chapter=item_data.get("promoted_to_causal_chapter"),
                carrier=item_data.get("carrier"),
                event_references=item_data.get("event_references", []),
                suppressed=item_data.get("suppressed", False),
            )
            item_tracker._items[item_id] = item
        
        # Restore statistics
        stats = self._item_tracker_data.get("statistics", {})
        item_tracker._items_introduced = stats.get("total_items", 0)
        item_tracker._items_suppressed = stats.get("suppressed_items", 0)
        item_tracker._items_promoted = stats.get("promoted_items", 0)
        
        # Restore transitions
        item_tracker._relevance_transitions = self._item_tracker_data.get("relevance_transitions", [])
        
        logger.info(f"Applied context to ItemTracker ({len(items_data)} items)")
    
    def __repr__(self) -> str:
        return (
            f"PersistenceManager(story='{self._context.story_id}', "
            f"chapter={self._context.current_chapter}, "
            f"loaded={self._context.is_loaded}, "
            f"dirty={self._context.is_dirty})"
        )
