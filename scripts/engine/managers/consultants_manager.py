"""
Consultants Manager - Read-only queries for persistent narrative context.

Responsibilities:
    - Provide read-only access to persisted context data
    - Support FinalAnalyzer queries
    - No file I/O or modifications

Per LOGIC_DESIGN.md Section 7.1 (Python Layer):
    Python is for orchestration, including state management.
    This module handles read-only queries.

Phase 8.4: Memory Optimization
    - FinalAnalyzer reads from persistent context via this manager
"""

import logging
from typing import Any, Dict, List, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .persistence_manager import PersistenceManager
    from ..domain import Context

logger = logging.getLogger(__name__)


class ConsultantsManager:
    """
    Read-only queries for persistent narrative context.
    
    Provides:
        - Entity registry data access
        - Item tracker data access
        - Relationship queries
        - Character state queries
        - Statistics and summaries
    
    Does NOT:
        - Modify any data
        - Perform file I/O
    """
    
    def __init__(self, persistence_manager: 'PersistenceManager'):
        """
        Initialize consultants manager.
        
        Args:
            persistence_manager: The PersistenceManager to read data from
        """
        self._pm = persistence_manager
    
    def get_entity_registry_data(self) -> Dict[str, Any]:
        """Get EntityRegistry data for FinalAnalyzer."""
        return self._pm.entity_registry_data
    
    def get_item_tracker_data(self) -> Dict[str, Any]:
        """Get ItemTracker data for FinalAnalyzer."""
        return self._pm.item_tracker_data
    
    def get_relationships(self) -> Dict[Tuple[str, str], str]:
        """Get relationships as tuple-keyed dict."""
        result = {}
        for key, rel_type in self._pm.relationships.items():
            parts = key.split(",")
            if len(parts) == 2:
                result[(parts[0], parts[1])] = rel_type
        return result
    
    def get_dead_characters(self) -> Set[str]:
        """Get set of dead character IDs."""
        return set(self._pm.dead_characters)
    
    def get_emotions(self) -> Dict[str, str]:
        """Get character emotions."""
        return dict(self._pm.emotions)
    
    def get_traits(self) -> Dict[str, str]:
        """Get character traits."""
        return dict(self._pm.traits)
    
    def get_all_entity_ids(self) -> Set[str]:
        """Get all entity IDs from EntityRegistry."""
        entities = self._pm.entity_registry_data.get("entities", {})
        return set(entities.keys())
    
    def get_active_entity_ids(self) -> Set[str]:
        """Get entity IDs with ACTIVE lifecycle state."""
        active_ids = set()
        for eid, edata in self._pm.entity_registry_data.get("entities", {}).items():
            if edata.get("lifecycle_state", "active") == "active":
                active_ids.add(eid)
        return active_ids
    
    def get_chekhov_candidates(self) -> List[Dict[str, Any]]:
        """Get items that are Chekhov's Gun violations."""
        candidates = []
        for item_id, item_data in self._pm.item_tracker_data.get("items", {}).items():
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
        for edata in self._pm.entity_registry_data.get("entities", {}).values():
            state = edata.get("lifecycle_state", "active")
            if state in summary:
                summary[state] += 1
        return summary
    
    def get_statistics(self, context: 'Context') -> Dict[str, Any]:
        """
        Get context statistics.
        
        Args:
            context: The Context metadata
            
        Returns:
            Dictionary with statistics
        """
        entity_stats = self._pm.entity_registry_data.get("statistics", {})
        item_stats = self._pm.item_tracker_data.get("statistics", {})
        
        return {
            "story_id": context.story_id,
            "current_chapter": context.current_chapter,
            "total_chapters_processed": context.total_chapters_processed,
            "entities": entity_stats.get("total_entities", 0),
            "items": item_stats.get("total_items", 0),
            "relationships": len(self._pm.relationships),
            "dead_characters": len(self._pm.dead_characters),
            "is_loaded": context.is_loaded,
            "is_dirty": context.is_dirty,
        }
