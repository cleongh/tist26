"""
Phase 3: Event Type Mapper

Maps legacy event types to refined event types for improved semantic precision.

Refined event types (Phase 3):
    Movement:
        - enter: entering a container/building/room
        - exit: exiting a container/building/room  
        - travel: movement between distant/unconnected locations
        
    Posture:
        - sit: character sits down
        - stand: character stands up
        - lie_down: character lies down
        
    Consciousness:
        - wake_up: character wakes from sleep
        - sleep: character falls asleep (legacy, already exists)

Legacy mappings (backward compatible):
    - arrive → enter (when entering a building/room)
    - arrive → travel (when moving between distant locations)
    - leave → exit (when exiting a building/room)
    - leave → travel (when departing for distant location)
    - get_up → stand (posture change)

This mapper preserves the original event type as 'original_type' for auditing
while setting a normalized 'type' field.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


class RefinedEventCategory(Enum):
    """Categories of refined event types."""
    MOVEMENT = "movement"
    POSTURE = "posture"
    CONSCIOUSNESS = "consciousness"
    ACTION = "action"
    COMMUNICATION = "communication"
    OTHER = "other"


# Refined event types with their categories
REFINED_EVENT_TYPES: Dict[str, RefinedEventCategory] = {
    # Movement
    "enter": RefinedEventCategory.MOVEMENT,
    "exit": RefinedEventCategory.MOVEMENT,
    "travel": RefinedEventCategory.MOVEMENT,
    "walk": RefinedEventCategory.MOVEMENT,
    "run": RefinedEventCategory.MOVEMENT,
    "fly": RefinedEventCategory.MOVEMENT,
    "apparate": RefinedEventCategory.MOVEMENT,
    "teleport": RefinedEventCategory.MOVEMENT,
    
    # Posture
    "sit": RefinedEventCategory.POSTURE,
    "sit_down": RefinedEventCategory.POSTURE,
    "stand": RefinedEventCategory.POSTURE,
    "stand_up": RefinedEventCategory.POSTURE,
    "lie_down": RefinedEventCategory.POSTURE,
    "lie": RefinedEventCategory.POSTURE,
    "recline": RefinedEventCategory.POSTURE,
    "collapse": RefinedEventCategory.POSTURE,
    "fall": RefinedEventCategory.POSTURE,
    "faint": RefinedEventCategory.POSTURE,
    "get_up": RefinedEventCategory.POSTURE,
    "rise": RefinedEventCategory.POSTURE,
    
    # Consciousness
    "wake_up": RefinedEventCategory.CONSCIOUSNESS,
    "wake": RefinedEventCategory.CONSCIOUSNESS,
    "awaken": RefinedEventCategory.CONSCIOUSNESS,
    "sleep": RefinedEventCategory.CONSCIOUSNESS,
    "fall_asleep": RefinedEventCategory.CONSCIOUSNESS,
    "doze": RefinedEventCategory.CONSCIOUSNESS,
    "nap": RefinedEventCategory.CONSCIOUSNESS,
    "pass_out": RefinedEventCategory.CONSCIOUSNESS,
    
    # Communication
    "talk": RefinedEventCategory.COMMUNICATION,
    "speak": RefinedEventCategory.COMMUNICATION,
    "tell": RefinedEventCategory.COMMUNICATION,
    "ask": RefinedEventCategory.COMMUNICATION,
    "shout": RefinedEventCategory.COMMUNICATION,
    "whisper": RefinedEventCategory.COMMUNICATION,
    
    # Other actions (pass-through)
    "attack": RefinedEventCategory.ACTION,
    "help": RefinedEventCategory.ACTION,
    "give": RefinedEventCategory.ACTION,
    "take": RefinedEventCategory.ACTION,
    "use": RefinedEventCategory.ACTION,
    "read": RefinedEventCategory.ACTION,
    "discover": RefinedEventCategory.ACTION,
    "meet": RefinedEventCategory.ACTION,
    "hug": RefinedEventCategory.ACTION,
    "think": RefinedEventCategory.ACTION,
    "escape": RefinedEventCategory.ACTION,
    "buy": RefinedEventCategory.ACTION,
    "smile": RefinedEventCategory.ACTION,
    "wave": RefinedEventCategory.ACTION,
    "knock": RefinedEventCategory.ACTION,
}

# Legacy event types that should be mapped to refined types
# Format: legacy_type -> default_refined_type
# NOTE: Only include types that are NOT already in REFINED_EVENT_TYPES
LEGACY_TYPE_MAPPING: Dict[str, str] = {
    # Movement legacy types
    "arrive": "enter",      # Default: entering a location
    "leave": "exit",        # Default: exiting a location
    "depart": "exit",       # Synonym for leave
    "go": "travel",         # Generic movement
    "move": "travel",       # Generic movement
    
    # Posture legacy types
    # NOTE: get_up, rise are already refined types (in REFINED_EVENT_TYPES)
    "seat": "sit",          # Sitting (unusual form)
    
    # Consciousness legacy types  
    # NOTE: awaken, doze, nap are already refined types (in REFINED_EVENT_TYPES)
    "rouse": "wake_up",     # Normalize to wake_up
}


@dataclass
class EventTypeMapping:
    """Records a mapping from legacy to refined event type."""
    original_type: str
    refined_type: str
    category: RefinedEventCategory
    event_id: str
    chapter: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_type": self.original_type,
            "refined_type": self.refined_type,
            "category": self.category.value,
            "event_id": self.event_id,
            "chapter": self.chapter,
        }


@dataclass
class EventTypeMappingResult:
    """Result of event type mapping for a batch of events."""
    events: List[Dict[str, Any]]
    mappings: List[EventTypeMapping]
    unmapped_types: Set[str]
    
    def get_mapping_count(self) -> int:
        """Count of events that were remapped."""
        return len(self.mappings)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_count": len(self.events),
            "mapping_count": self.get_mapping_count(),
            "unmapped_types": list(self.unmapped_types),
            "mappings": [m.to_dict() for m in self.mappings],
        }


class EventTypeMapper:
    """
    Maps legacy event types to refined event types.
    
    Preserves backward compatibility by:
    1. Keeping the original type in 'original_type' field
    2. Only remapping known legacy types
    3. Passing through unknown types unchanged
    
    Usage:
        mapper = EventTypeMapper()
        result = mapper.map_events(events, chapter=1)
        # result.events contains events with refined types
        # result.mappings records what was changed
    """
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize the mapper.
        
        Args:
            strict_mode: If True, only allow known refined event types.
                        If False, pass through unknown types.
        """
        self._strict_mode = strict_mode
        self._unmapped_types: Set[str] = set()
        self._total_mappings: int = 0
    
    def _normalize_type(self, event_type: str) -> str:
        """Normalize event type string for comparison."""
        return event_type.lower().strip().replace("-", "_").replace(" ", "_")
    
    def map_event_type(
        self, 
        event_type: str,
        event: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, bool]:
        """
        Map a single event type to its refined equivalent.
        
        Args:
            event_type: Original event type
            event: Full event dict (for context-aware mapping)
            
        Returns:
            Tuple of (refined_type, was_remapped)
        """
        normalized = self._normalize_type(event_type)
        
        # Check if it's already a refined type
        if normalized in REFINED_EVENT_TYPES:
            return normalized, False
        
        # Check legacy mapping
        if normalized in LEGACY_TYPE_MAPPING:
            refined = LEGACY_TYPE_MAPPING[normalized]
            return refined, True
        
        # Unknown type - pass through or reject
        self._unmapped_types.add(normalized)
        return normalized, False
    
    def map_event(
        self,
        event: Dict[str, Any],
        chapter: int = 0,
    ) -> Tuple[Dict[str, Any], Optional[EventTypeMapping]]:
        """
        Map a single event's type to refined type.
        
        Args:
            event: Event dictionary with 'type' field
            chapter: Current chapter number
            
        Returns:
            Tuple of (mapped_event, mapping_record or None)
        """
        original_type = event.get("type", "unknown")
        refined_type, was_remapped = self.map_event_type(original_type, event)
        
        # Create mapped event
        mapped_event = dict(event)
        if was_remapped:
            mapped_event["type"] = refined_type
            mapped_event["original_type"] = original_type
        
        # Create mapping record if remapped
        mapping = None
        if was_remapped:
            category = REFINED_EVENT_TYPES.get(
                refined_type, 
                RefinedEventCategory.OTHER
            )
            mapping = EventTypeMapping(
                original_type=original_type,
                refined_type=refined_type,
                category=category,
                event_id=event.get("id", "unknown"),
                chapter=chapter,
            )
            self._total_mappings += 1
        
        return mapped_event, mapping
    
    def map_events(
        self,
        events: List[Dict[str, Any]],
        chapter: int = 0,
    ) -> EventTypeMappingResult:
        """
        Map event types for a list of events.
        
        Args:
            events: List of event dictionaries
            chapter: Current chapter number
            
        Returns:
            EventTypeMappingResult with mapped events and metadata
        """
        mapped_events: List[Dict[str, Any]] = []
        mappings: List[EventTypeMapping] = []
        
        for event in events:
            mapped_event, mapping = self.map_event(event, chapter)
            mapped_events.append(mapped_event)
            if mapping:
                mappings.append(mapping)
        
        return EventTypeMappingResult(
            events=mapped_events,
            mappings=mappings,
            unmapped_types=set(self._unmapped_types),
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mapping statistics."""
        return {
            "total_mappings": self._total_mappings,
            "unmapped_types": list(self._unmapped_types),
            "unmapped_count": len(self._unmapped_types),
        }
    
    def reset(self) -> None:
        """Reset the mapper state."""
        self._unmapped_types.clear()
        self._total_mappings = 0


def get_event_category(event_type: str) -> RefinedEventCategory:
    """Get the category of an event type."""
    normalized = event_type.lower().strip().replace("-", "_").replace(" ", "_")
    return REFINED_EVENT_TYPES.get(normalized, RefinedEventCategory.OTHER)


def is_state_changing_event(event_type: str) -> bool:
    """Check if an event type changes character state."""
    category = get_event_category(event_type)
    return category in (
        RefinedEventCategory.POSTURE,
        RefinedEventCategory.CONSCIOUSNESS,
    )


def is_movement_event(event_type: str) -> bool:
    """Check if an event type is a movement event."""
    return get_event_category(event_type) == RefinedEventCategory.MOVEMENT
