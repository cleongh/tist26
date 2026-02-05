"""
State Manager Persistence - Save and Load StateManager state

Handles persistence operations for StateManager including:
    - JSON file serialization/deserialization
    - PersistentContext integration
"""

import json
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

from ..domain import Entity, EntityType

if TYPE_CHECKING:
    from ..state_manager import StateManager


class StateManagerPersistence:
    """
    Handles save/load operations for StateManager.
    
    Provides methods to:
        - Serialize StateManager to JSON-compatible dict
        - Save state to file
        - Load state from file
        - Save/load from PersistentContext
    
    Usage:
        persistence = StateManagerPersistence(state_manager)
        persistence.save(path)
        persistence.load(path)
    """
    
    def __init__(self, state_manager: 'StateManager'):
        """
        Initialize the StateManagerPersistence.
        
        Args:
            state_manager: The StateManager to persist
        """
        self._state_manager = state_manager
    
    def to_json(self) -> Dict[str, Any]:
        """
        Serialize state manager to JSON-compatible dict.
        
        Returns:
            Dict containing all state that can be serialized to JSON
        """
        sm = self._state_manager
        return {
            "current_time": sm.current_time,
            "next_event_id": sm.next_event_id,
            "persistent_dead": list(sm.persistent_dead),
            "persistent_emotions": sm.persistent_emotions,
            "persistent_traits": sm.persistent_traits,
            "persistent_relationships": {
                f"{k[0]},{k[1]}": v 
                for k, v in sm.persistent_relationships.items()
            },
            "persistent_entities": self._entities_to_dict(sm.persistent_entities),
            # EntityRegistry state (Phase 8.2)
            "entity_registry": sm._entity_registry.to_dict(),
            # Note: accumulated_facts now derived from _entity_registry, 
            # kept in JSON for backward compatibility
            "accumulated_facts": sm.accumulated_facts,
            "event_log": sm.event_log,
        }
    
    def _entities_to_dict(self, entities: Dict[str, Entity]) -> Dict[str, Dict[str, Any]]:
        """
        Convert persistent_entities to JSON-compatible dict.
        
        Args:
            entities: Dict of entity ID to Entity objects
            
        Returns:
            Dict of entity ID to entity data dict
        """
        return {
            eid: {
                "id": e.id,
                "type": e.entity_type,
                "traits": list(e.traits),
                "state": e.state,
                "emotion": e.emotion
            }
            for eid, e in entities.items()
        }
    
    def save(self, path: Path) -> None:
        """
        Save state to file.
        
        Args:
            path: Path to save the state JSON file
        """
        with open(path, 'w') as f:
            json.dump(self.to_json(), f, indent=2)
    
    def load(self, path: Path) -> None:
        """
        Load state from file.
        
        Args:
            path: Path to load the state JSON file from
        """
        with open(path) as f:
            data = json.load(f)
        
        self._apply_data(data)
    
    def _apply_data(self, data: Dict[str, Any]) -> None:
        """
        Apply loaded data to the state manager.
        
        Args:
            data: Dict containing state data to apply
        """
        sm = self._state_manager
        
        sm.current_time = data.get("current_time", 0)
        sm.next_event_id = data.get("next_event_id", 1)
        sm.persistent_dead = set(data.get("persistent_dead", []))
        sm.persistent_emotions = data.get("persistent_emotions", {})
        sm.persistent_traits = data.get("persistent_traits", {})
        
        self._load_relationships(data.get("persistent_relationships", {}))
        self._load_entities(data.get("persistent_entities", {}))
        self._load_entity_registry(data)
        
        # Note: accumulated_facts in JSON is ignored on load - derived from _entity_registry
        sm.event_log = data.get("event_log", [])
    
    def _load_relationships(self, relationships_data: Dict[str, str]) -> None:
        """
        Load relationships from serialized data.
        
        Args:
            relationships_data: Dict of "char1,char2" -> rel_type
        """
        sm = self._state_manager
        sm.persistent_relationships = {}
        
        for key, val in relationships_data.items():
            parts = key.split(",")
            if len(parts) == 2:
                sm.persistent_relationships[(parts[0], parts[1])] = val
    
    def _load_entities(self, entities_data: Dict[str, Dict[str, Any]]) -> None:
        """
        Load entities from serialized data.
        
        Args:
            entities_data: Dict of entity ID to entity data dict
        """
        sm = self._state_manager
        sm.persistent_entities = {}
        
        for eid, edata in entities_data.items():
            sm.persistent_entities[eid] = Entity(
                id=edata["id"],
                entity_type=edata["type"],
                traits=set(edata.get("traits", [])),
                state=edata.get("state", "alive"),
                emotion=edata.get("emotion")
            )
    
    def _load_entity_registry(self, data: Dict[str, Any]) -> None:
        """
        Load EntityRegistry state from serialized data.
        
        Handles backward compatibility if entity_registry key is missing.
        
        Args:
            data: Full state data dict
        """
        sm = self._state_manager
        
        # Load EntityRegistry state (Phase 8.2)
        if "entity_registry" in data:
            sm._entity_registry.load_from_dict(data["entity_registry"])
        else:
            self._reconstruct_registry_from_entities()
    
    def _reconstruct_registry_from_entities(self) -> None:
        """
        Reconstruct EntityRegistry from persistent_entities for backward compatibility.
        
        Used when loading old format that doesn't have entity_registry data.
        """
        sm = self._state_manager
        
        sm._entity_registry.reset()
        type_map = {
            'character': EntityType.CHARACTER,
            'location': EntityType.LOCATION,
            'item': EntityType.ITEM,
        }
        
        for eid, entity in sm.persistent_entities.items():
            registry_type = type_map.get(entity.entity_type, EntityType.CHARACTER)
            sm._entity_registry.register_entity(
                canonical_id=eid,
                entity_type=registry_type,
                aliases=entity.aliases,
                state=entity.state,
                traits=list(entity.traits),
                emotion=entity.emotion,
            )
        
        # Restore dead state
        for char in sm.persistent_dead:
            sm._entity_registry.mark_dead(char)
    
    # =========================================================================
    # Context Persistence Integration (Phase 8.4)
    # =========================================================================
    
    def save_to_persistent_context(self, context, chapter: int) -> None:
        """
        Save state to PersistentContext.
        
        This is the primary method for incremental context updates.
        Called at the end of each chapter.
        
        Args:
            context: PersistentContext instance
            chapter: Chapter number just processed
        """
        context.update_from_state_manager(self._state_manager, chapter)
    
    def load_from_persistent_context(self, context) -> None:
        """
        Load state from PersistentContext.
        
        Used when resuming from a saved context.
        
        Args:
            context: PersistentContext instance (must be loaded)
        """
        context.apply_to_state_manager(self._state_manager)
