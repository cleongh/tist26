"""
Phase 5: Event Normalizer.

Normalizes and validates events with strict entity checking:
1. event.agent MUST exist in EntityRegistry
2. event.patient MUST exist OR be null
3. event.location MUST exist OR be null
4. Invalid events are dropped with a logged reason
5. Events preserve original order
6. Generates event_time(e, t) automatically

Also tracks item usage to classify items as:
- Latent: Introduced but unused (Chekhov's Gun candidates)
- Causal: Used in events

Per LOGIC_DESIGN.md Section 4:
- Events are state transitions, not static facts
- Each event occurs at a specific timestep
- Events are evaluated sequentially
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum

from .entity_registry import EntityRegistry, ValidationWarning, _normalize_id
from ..state.logging import log


class ItemUsageType(Enum):
    """Classification of item usage in events."""
    LATENT = "latent"      # Introduced but not used in events
    CAUSAL = "causal"      # Used in at least one event


# Event types that indicate item usage (makes item causal)
ITEM_CAUSAL_EVENTS = frozenset({
    "give", "take", "use", "destroy", "drop", "discover",
    "wield", "drink", "eat", "read", "open", "break",
    "steal", "receive", "throw", "hide", "find", "pick_up",
    "activate", "deactivate", "repair", "examine",
})


@dataclass
class DroppedEvent:
    """Records a dropped event with the reason."""
    event_index: int
    event_id: str
    event_type: str
    reason: str
    original_event: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_index": self.event_index,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "reason": self.reason,
            "original_event": self.original_event,
        }


@dataclass
class ItemUsage:
    """Tracks an item's usage across events."""
    item_id: str
    usage_type: ItemUsageType
    introduced_at_event: Optional[int] = None  # Event index where first seen
    used_in_events: List[int] = field(default_factory=list)  # Event indices
    
    def is_causal(self) -> bool:
        return self.usage_type == ItemUsageType.CAUSAL
    
    def is_latent(self) -> bool:
        return self.usage_type == ItemUsageType.LATENT
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "usage_type": self.usage_type.value,
            "introduced_at_event": self.introduced_at_event,
            "used_in_events": self.used_in_events,
        }


@dataclass
class EventNormalizationResult:
    """Result of event normalization."""
    events: List[Dict[str, Any]]  # Validated events with event_time added
    dropped_events: List[DroppedEvent]
    item_usage: Dict[str, ItemUsage]  # item_id -> ItemUsage
    
    def get_causal_items(self) -> Set[str]:
        """Get IDs of all causal items."""
        return {k for k, v in self.item_usage.items() if v.is_causal()}
    
    def get_latent_items(self) -> Set[str]:
        """Get IDs of all latent items."""
        return {k for k, v in self.item_usage.items() if v.is_latent()}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_count": len(self.events),
            "dropped_count": len(self.dropped_events),
            "causal_items": list(self.get_causal_items()),
            "latent_items": list(self.get_latent_items()),
            "dropped_events": [d.to_dict() for d in self.dropped_events],
            "item_usage": {k: v.to_dict() for k, v in self.item_usage.items()},
        }


class EventNormalizer:
    """
    Normalizes and validates events using an EntityRegistry.
    
    Strict validation rules:
    - event.agent MUST exist in EntityRegistry (required)
    - event.patient MUST exist OR be null (optional)
    - event.location MUST exist OR be null (optional)
    - Invalid events are dropped with a logged reason
    
    Features:
    - Preserves original event order
    - Generates event_time(e, t) for ASP integration
    - Tracks item usage (latent vs causal)
    
    Usage:
        normalizer = EventNormalizer(entity_registry)
        result = normalizer.normalize(events, base_time=0)
        # result.events contains validated events with event_time
        # result.dropped_events contains events that failed validation
        # result.item_usage tracks causal vs latent items
    """
    
    def __init__(self, registry: EntityRegistry):
        """
        Initialize the normalizer with an EntityRegistry.
        
        Args:
            registry: EntityRegistry with registered characters, locations, items
        """
        self._registry = registry
        
        # Track item usage across all normalized events
        self._item_usage: Dict[str, ItemUsage] = {}
        
        # Initialize all registered items as latent
        for item_id in registry.get_all_item_ids():
            self._item_usage[item_id] = ItemUsage(
                item_id=item_id,
                usage_type=ItemUsageType.LATENT,
            )
    
    def _is_null_value(self, value: Any) -> bool:
        """Check if a value represents null/none."""
        if value is None:
            return True
        if isinstance(value, str):
            return value.lower() in ("null", "none", "", "n/a", "na")
        return False
    
    def _validate_agent(self, event: Dict[str, Any], event_index: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Validate agent field (required, must be a character).
        
        Returns:
            (canonical_id, error_reason) - canonical_id is None if invalid
        """
        agent = event.get("agent", "")
        
        if not agent or self._is_null_value(agent):
            return None, "agent is missing or null (required)"
        
        canonical = self._registry.resolve_character(agent)
        if not canonical:
            return None, f"agent '{agent}' not found in EntityRegistry"
        
        return canonical, None
    
    def _validate_patient(self, event: Dict[str, Any], event_index: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Validate patient field (optional, can be character or item).
        
        Returns:
            (canonical_id, entity_type, error_reason) - all None if null/valid-null
        """
        patient = event.get("patient")
        
        if self._is_null_value(patient):
            return None, None, None  # Valid null
        
        # Try to resolve as character first, then item
        canonical, entity_type = self._registry.resolve_entity(patient)
        
        if canonical:
            return canonical, entity_type, None
        
        return None, None, f"patient '{patient}' not found in EntityRegistry"
    
    def _validate_location(self, event: Dict[str, Any], event_index: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Validate location field (optional, must be a location if present).
        
        Returns:
            (canonical_id, error_reason) - canonical_id is None if null or invalid
        """
        location = event.get("location")
        
        if self._is_null_value(location):
            return None, None  # Valid null
        
        canonical = self._registry.resolve_location(location)
        if canonical:
            return canonical, None
        
        return None, f"location '{location}' not found in EntityRegistry"
    
    def _track_item_usage(self, event: Dict[str, Any], event_index: int, patient_id: Optional[str], patient_type: Optional[str]) -> None:
        """
        Track item usage to determine if items are causal or latent.
        
        An item becomes causal if:
        - It is the patient of an event with a causal event type
        - It is referenced in certain event types
        """
        event_type = event.get("type", "").lower()
        
        # Check if patient is an item and event type makes it causal
        if patient_id and patient_type == "item":
            if patient_id not in self._item_usage:
                self._item_usage[patient_id] = ItemUsage(
                    item_id=patient_id,
                    usage_type=ItemUsageType.LATENT,
                )
            
            usage = self._item_usage[patient_id]
            
            # Track introduction
            if usage.introduced_at_event is None:
                usage.introduced_at_event = event_index
            
            # Check if this event type makes the item causal
            if event_type in ITEM_CAUSAL_EVENTS:
                usage.usage_type = ItemUsageType.CAUSAL
                usage.used_in_events.append(event_index)
        
        # Also check if any item is mentioned in the event's "item" field
        item_ref = event.get("item")
        if item_ref and not self._is_null_value(item_ref):
            item_canonical = self._registry.resolve_item(item_ref)
            if item_canonical:
                if item_canonical not in self._item_usage:
                    self._item_usage[item_canonical] = ItemUsage(
                        item_id=item_canonical,
                        usage_type=ItemUsageType.LATENT,
                    )
                
                usage = self._item_usage[item_canonical]
                if usage.introduced_at_event is None:
                    usage.introduced_at_event = event_index
                
                if event_type in ITEM_CAUSAL_EVENTS:
                    usage.usage_type = ItemUsageType.CAUSAL
                    usage.used_in_events.append(event_index)
    
    def normalize(
        self,
        events: List[Dict[str, Any]],
        base_time: int = 0,
        drop_invalid: bool = True,
    ) -> EventNormalizationResult:
        """
        Normalize and validate a list of events.
        
        Strict validation:
        - agent MUST exist (drop if not)
        - patient CAN be null, but if present MUST exist
        - location CAN be null, but if present MUST exist
        
        Args:
            events: List of event dicts from extraction
            base_time: Starting time for event_time generation
            drop_invalid: If True, drop invalid events; if False, keep with warnings
            
        Returns:
            EventNormalizationResult with validated events and metadata
        """
        validated_events: List[Dict[str, Any]] = []
        dropped_events: List[DroppedEvent] = []
        
        current_time = base_time
        
        for event_index, event in enumerate(events):
            event_id = event.get("id", f"event_{event_index}")
            event_type = event.get("type", "unknown")
            
            # Validate agent (required)
            agent_canonical, agent_error = self._validate_agent(event, event_index)
            if agent_error:
                dropped = DroppedEvent(
                    event_index=event_index,
                    event_id=event_id,
                    event_type=event_type,
                    reason=agent_error,
                    original_event=event,
                )
                dropped_events.append(dropped)
                self._registry._warnings.append(ValidationWarning(
                    phase="events",
                    entity_type="character",
                    unknown_id=event.get("agent", ""),
                    context=f"event[{event_index}] ({event_type})",
                    action="dropped",
                ))
                log(f"    [EventNormalizer] Dropped event[{event_index}] ({event_type}): {agent_error}", "WARN")
                if drop_invalid:
                    continue
            
            # Validate patient (optional)
            patient_canonical, patient_type, patient_error = self._validate_patient(event, event_index)
            if patient_error:
                dropped = DroppedEvent(
                    event_index=event_index,
                    event_id=event_id,
                    event_type=event_type,
                    reason=patient_error,
                    original_event=event,
                )
                dropped_events.append(dropped)
                self._registry._warnings.append(ValidationWarning(
                    phase="events",
                    entity_type="character/item",
                    unknown_id=event.get("patient", ""),
                    context=f"event[{event_index}] ({event_type})",
                    action="dropped",
                ))
                log(f"    [EventNormalizer] Dropped event[{event_index}] ({event_type}): {patient_error}", "WARN")
                if drop_invalid:
                    continue
            
            # Validate location (optional)
            location_canonical, location_error = self._validate_location(event, event_index)
            if location_error:
                dropped = DroppedEvent(
                    event_index=event_index,
                    event_id=event_id,
                    event_type=event_type,
                    reason=location_error,
                    original_event=event,
                )
                dropped_events.append(dropped)
                self._registry._warnings.append(ValidationWarning(
                    phase="events",
                    entity_type="location",
                    unknown_id=event.get("location", ""),
                    context=f"event[{event_index}] ({event_type})",
                    action="dropped",
                ))
                log(f"    [EventNormalizer] Dropped event[{event_index}] ({event_type}): {location_error}", "WARN")
                if drop_invalid:
                    continue
            
            # Build validated event
            validated_event = dict(event)
            validated_event["agent"] = agent_canonical
            if patient_canonical:
                validated_event["patient"] = patient_canonical
            elif "patient" in validated_event:
                validated_event["patient"] = None
            if location_canonical:
                validated_event["location"] = location_canonical
            elif "location" in validated_event:
                validated_event["location"] = None
            
            # Add event_time for ASP
            validated_event["event_time"] = current_time
            validated_event["event_index"] = event_index  # Preserve original order info
            
            # Track item usage
            self._track_item_usage(event, event_index, patient_canonical, patient_type)
            
            validated_events.append(validated_event)
            current_time += 1
        
        result = EventNormalizationResult(
            events=validated_events,
            dropped_events=dropped_events,
            item_usage=dict(self._item_usage),
        )
        
        # Log summary
        causal_count = len(result.get_causal_items())
        latent_count = len(result.get_latent_items())
        log(f"    [EventNormalizer] Validated: {len(validated_events)} events, "
            f"{len(dropped_events)} dropped")
        log(f"    [EventNormalizer] Items: {causal_count} causal, {latent_count} latent")
        
        return result
    
    def get_item_usage(self) -> Dict[str, ItemUsage]:
        """Get the current item usage tracking."""
        return dict(self._item_usage)
    
    def get_causal_items(self) -> Set[str]:
        """Get IDs of all causal items."""
        return {k for k, v in self._item_usage.items() if v.is_causal()}
    
    def get_latent_items(self) -> Set[str]:
        """Get IDs of all latent items."""
        return {k for k, v in self._item_usage.items() if v.is_latent()}
    
    def to_asp_time_facts(self, events: List[Dict[str, Any]]) -> List[str]:
        """
        Generate ASP event_time facts for validated events.
        
        Returns facts in the format:
        - event_time(event_id, time).
        """
        facts = []
        for event in events:
            event_id = _normalize_id(event.get("id", f"event_{event.get('event_index', 0)}"))
            event_time = event.get("event_time", 0)
            facts.append(f"event_time({event_id}, {event_time}).")
        return facts
    
    def to_asp_item_facts(self) -> List[str]:
        """
        Generate ASP facts for item classification.
        
        Returns facts in the format:
        - causal_item(item_id).
        - latent_item(item_id).
        """
        facts = []
        for item_id, usage in self._item_usage.items():
            normalized_id = _normalize_id(item_id)
            if usage.is_causal():
                facts.append(f"causal_item({normalized_id}).")
            else:
                facts.append(f"latent_item({normalized_id}).")
        return facts
