"""
Context Persistence - Persistent Narrative Context Storage

Responsibilities:
    - Persist global narrative context to disk using JSON
    - Load-once / update-incrementally behavior
    - No memory growth from historical context
    - Provide context for FinalAnalyzer

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

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from pathlib import Path
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ContextMetadata:
    """Metadata about the persistent context."""
    story_id: str = "unknown"
    created_at: str = ""
    last_updated_at: str = ""
    current_chapter: int = 0
    total_chapters_processed: int = 0
    engine_version: str = "0.8.0"
    
    def update(self, chapter: int) -> None:
        """Update metadata after processing a chapter."""
        self.last_updated_at = datetime.now().isoformat()
        self.current_chapter = chapter
        self.total_chapters_processed = max(self.total_chapters_processed, chapter)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_id": self.story_id,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "current_chapter": self.current_chapter,
            "total_chapters_processed": self.total_chapters_processed,
            "engine_version": self.engine_version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextMetadata":
        return cls(
            story_id=data.get("story_id", "unknown"),
            created_at=data.get("created_at", ""),
            last_updated_at=data.get("last_updated_at", ""),
            current_chapter=data.get("current_chapter", 0),
            total_chapters_processed=data.get("total_chapters_processed", 0),
            engine_version=data.get("engine_version", "0.8.0"),
        )


class PersistentContext:
    """
    Persistent narrative context storage.
    
    Provides:
        - Load-once behavior at start
        - Incremental updates after each chapter
        - JSON-based storage (human-readable)
        - No memory growth from historical context
    
    Does NOT:
        - Store WorldState snapshots
        - Store event sequences
        - Store ASP programs
    
    Usage:
        # At start of story processing
        ctx = PersistentContext(Path("./context"))
        ctx.load_or_create("harry_potter_1")
        
        # After each chapter
        ctx.update_from_state_manager(state_manager, chapter=5)
        ctx.update_from_item_tracker(item_tracker, chapter=5)
        ctx.save()
        
        # FinalAnalyzer access
        analyzer = FinalAnalyzer()
        analyzer.set_persistent_context(ctx)
    """
    
    def __init__(self, storage_dir: Path = None):
        """
        Initialize persistent context.
        
        Args:
            storage_dir: Directory for context files. If None, uses current directory.
        """
        self._storage_dir = Path(storage_dir) if storage_dir else Path(".")
        self._context_file: Optional[Path] = None
        self._loaded: bool = False
        self._dirty: bool = False  # True if changes need to be saved
        
        # Context data (loaded from / saved to JSON)
        self._metadata: ContextMetadata = ContextMetadata()
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
    def is_loaded(self) -> bool:
        """Check if context has been loaded."""
        return self._loaded
    
    @property
    def is_dirty(self) -> bool:
        """Check if there are unsaved changes."""
        return self._dirty
    
    @property
    def metadata(self) -> ContextMetadata:
        """Get context metadata."""
        return self._metadata
    
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
        self._metadata = ContextMetadata(
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
        
        self._loaded = True
        self._dirty = True
        
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
            
            self._metadata = ContextMetadata.from_dict(data.get("metadata", {}))
            self._entity_registry_data = data.get("entity_registry", {"entities": {}, "statistics": {}})
            self._item_tracker_data = data.get("item_tracker", {"items": {}, "statistics": {}})
            self._relationships = data.get("relationships", {})
            self._dead_characters = data.get("dead_characters", [])
            self._emotions = data.get("emotions", {})
            self._traits = data.get("traits", {})
            
            self._loaded = True
            self._dirty = False
            self._load_count += 1
            
            logger.info(f"Loaded context from '{self._context_file}' "
                       f"(chapter {self._metadata.current_chapter})")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse context file: {e}")
            raise
    
    def save(self) -> None:
        """Save context to JSON file."""
        if not self._context_file:
            raise ValueError("No context file set. Call load_or_create first.")
        
        if not self._dirty:
            logger.debug("Context not dirty, skipping save")
            return
        
        data = {
            "metadata": self._metadata.to_dict(),
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
            
            self._dirty = False
            self._save_count += 1
            
            logger.info(f"Saved context to '{self._context_file}'")
            
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def update_from_state_manager(self, state_manager, chapter: int) -> None:
        """
        Update context from StateManager after processing a chapter.
        
        This is an incremental update - only changed data is updated.
        
        Args:
            state_manager: The StateManager instance
            chapter: Chapter number just processed
        """
        # Update metadata
        self._metadata.update(chapter)
        
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
        
        self._dirty = True
    
    def update_from_item_tracker(self, item_tracker, chapter: int) -> None:
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
        
        self._dirty = True
    
    def apply_to_state_manager(self, state_manager) -> None:
        """
        Apply loaded context to StateManager.
        
        Used when resuming from a saved context.
        
        Args:
            state_manager: The StateManager to update
        """
        if not self._loaded:
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
        
        logger.info(f"Applied context to StateManager (chapter {self._metadata.current_chapter})")
    
    def apply_to_item_tracker(self, item_tracker) -> None:
        """
        Apply loaded context to ItemTracker.
        
        Used when resuming from a saved context.
        
        Args:
            item_tracker: The ItemTracker to update
        """
        if not self._loaded:
            raise RuntimeError("Context not loaded. Call load_or_create first.")
        
        # Import here to avoid circular imports
        from .item_tracker import TrackedItem, ItemRelevance, ItemLifecycleState
        
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
    
    # =========================================================================
    # Accessors for FinalAnalyzer
    # =========================================================================
    
    def get_entity_registry_data(self) -> Dict[str, Any]:
        """Get EntityRegistry data for FinalAnalyzer."""
        return self._entity_registry_data
    
    def get_item_tracker_data(self) -> Dict[str, Any]:
        """Get ItemTracker data for FinalAnalyzer."""
        return self._item_tracker_data
    
    def get_relationships(self) -> Dict[Tuple[str, str], str]:
        """Get relationships as tuple-keyed dict."""
        result = {}
        for key, rel_type in self._relationships.items():
            parts = key.split(",")
            if len(parts) == 2:
                result[(parts[0], parts[1])] = rel_type
        return result
    
    def get_dead_characters(self) -> Set[str]:
        """Get set of dead character IDs."""
        return set(self._dead_characters)
    
    def get_emotions(self) -> Dict[str, str]:
        """Get character emotions."""
        return dict(self._emotions)
    
    def get_traits(self) -> Dict[str, str]:
        """Get character traits."""
        return dict(self._traits)
    
    def get_all_entity_ids(self) -> Set[str]:
        """Get all entity IDs from EntityRegistry."""
        entities = self._entity_registry_data.get("entities", {})
        return set(entities.keys())
    
    def get_active_entity_ids(self) -> Set[str]:
        """Get entity IDs with ACTIVE lifecycle state."""
        active_ids = set()
        for eid, edata in self._entity_registry_data.get("entities", {}).items():
            if edata.get("lifecycle_state", "active") == "active":
                active_ids.add(eid)
        return active_ids
    
    def get_chekhov_candidates(self) -> List[Dict[str, Any]]:
        """Get items that are Chekhov's Gun violations."""
        candidates = []
        for item_id, item_data in self._item_tracker_data.get("items", {}).items():
            # Check if item remained latent and is not suppressed
            relevance = item_data.get("relevance", "background")
            promoted = item_data.get("promoted_to_causal_chapter")
            suppressed = item_data.get("suppressed", False)
            
            if relevance == "latent" and promoted is None and not suppressed:
                candidates.append(item_data)
        return candidates
    
    def get_lifecycle_summary(self) -> Dict[str, int]:
        """Get entity lifecycle state summary."""
        summary = {"active": 0, "latent": 0, "frozen": 0}
        for edata in self._entity_registry_data.get("entities", {}).values():
            state = edata.get("lifecycle_state", "active")
            if state in summary:
                summary[state] += 1
        return summary
    
    # =========================================================================
    # Statistics and Debugging
    # =========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get context statistics."""
        entity_stats = self._entity_registry_data.get("statistics", {})
        item_stats = self._item_tracker_data.get("statistics", {})
        
        return {
            "story_id": self._metadata.story_id,
            "current_chapter": self._metadata.current_chapter,
            "total_chapters_processed": self._metadata.total_chapters_processed,
            "entities": entity_stats.get("total_entities", 0),
            "items": item_stats.get("total_items", 0),
            "relationships": len(self._relationships),
            "dead_characters": len(self._dead_characters),
            "load_count": self._load_count,
            "save_count": self._save_count,
            "is_dirty": self._dirty,
        }
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"PersistentContext(story='{stats['story_id']}', "
            f"chapter={stats['current_chapter']}, "
            f"entities={stats['entities']}, "
            f"items={stats['items']})"
        )
