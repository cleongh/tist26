"""
Event Preprocessor - Validates, fixes, and prepares events for execution.

Handles:
    - Event creation from raw data
    - Global ID assignment
    - Validation and fixing of common LLM extraction errors
    - Entity extraction from events
"""

from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from ..domain.event import Event
from ..resolvers import AliasResolver
from ..utils.sanitation import sanitize_id, sanitize_character_id

if TYPE_CHECKING:
    from ..state_manager import StateManager


# Actions that logically require no patient (reflexive/intransitive)
NO_PATIENT_ACTIONS = {
    'travel', 'walk', 'run', 'fly', 'drive', 'move', 'go', 'leave', 'arrive',
    'escape', 'flee', 'return', 'enter', 'exit', 'climb', 'jump', 'land',
    'die', 'dies', 'died', 'death', 'faint', 'collapse', 'wake', 'sleep',
    'rest', 'hide', 'wait', 'stand', 'sit', 'kneel', 'bow', 'fall',
    'think', 'read', 'write', 'sing', 'cry', 'laugh', 'scream', 'shout',
    'practice', 'train', 'study', 'work', 'eat', 'drink',
    'discover', 'realize', 'understand', 'learn', 'notice', 'observe',
}


class EventPreprocessor:
    """
    Preprocesses events before execution.
    
    Responsible for:
        - Creating Event objects from raw dictionaries
        - Assigning global continuous event IDs
        - Validating and fixing common LLM extraction errors
    """
    
    def __init__(
        self,
        state_manager: 'StateManager',
        alias_resolver: Optional[AliasResolver] = None,
    ):
        """
        Initialize the event preprocessor.
        
        Args:
            state_manager: StateManager for ID assignment and logging
            alias_resolver: Optional AliasResolver for character normalization
        """
        self.state_manager = state_manager
        self.alias_resolver = alias_resolver
    
    def create_event(
        self,
        event_data: Dict[str, Any],
        time: int,
        chapter_num: int = 0,
    ) -> Event:
        """
        Create an Event from extracted event data.
        
        Args:
            event_data: Dict with keys like 'id', 'type', 'agent', 'patient', 'location'
            time: The timestep for this event
            chapter_num: Current chapter number (for ID generation)
        
        Returns:
            Event object ready for execution
        """
        # Use global_id if available (assigned by StateManager), else generate
        event_id = event_data.get('global_id')
        if not event_id:
            event_id = event_data.get('id', f'e{chapter_num}_{time}')
        
        return Event(
            id=sanitize_id(event_id),
            event_type=sanitize_id(event_data.get('type', 'action')),
            time=time,
            agent=self._get_agent(event_data),
            patient=self._get_patient(event_data),
            location=self._get_location(event_data),
            destination=self._get_destination(event_data),
            source_text=event_data.get('source_text'),
            emotion=self._get_emotion(event_data),
            metadata=event_data.get('metadata', {}),
        )
    
    def _get_agent(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Extract and sanitize agent from event data."""
        if event_data.get('agent'):
            return sanitize_character_id(event_data['agent'], self.alias_resolver)
        return None
    
    def _get_patient(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Extract and sanitize patient from event data."""
        if event_data.get('patient'):
            return sanitize_id(event_data['patient'])
        return None
    
    def _get_location(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Extract and sanitize location from event data."""
        if event_data.get('location'):
            return sanitize_id(event_data['location'])
        return None
    
    def _get_destination(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Extract and sanitize destination from event data."""
        if event_data.get('destination'):
            return sanitize_id(event_data['destination'])
        return None
    
    def _get_emotion(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Extract and sanitize emotion from event data."""
        if event_data.get('emotion'):
            return sanitize_id(event_data['emotion'])
        return None
    
    def assign_global_event_ids(
        self,
        events: List[Dict[str, Any]],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """
        Assign continuous global IDs to events and log them.
        
        Event IDs are continuous across all chapters (e1, e2, ..., eN).
        Extracted from LogicEvaluator._assign_global_event_ids()
        
        Args:
            events: List of event dictionaries
            chapter_num: Current chapter number
            
        Returns:
            Events with 'global_id' and 'chapter' fields added
        """
        for event in events:
            event_id = self.state_manager.log_event(event, chapter_num)
            event['global_id'] = event_id
            event['chapter'] = chapter_num
        
        return events
    
    def validate_and_fix_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Validate and fix extracted events post-processing.
        
        Fixes common LLM extraction errors without deleting valid events.
        Extracted from LogicEvaluator._validate_and_fix_events()
        
        Args:
            events: List of event dictionaries to validate
            
        Returns:
            Validated and fixed events
        """
        fixed_events = []
        
        for event in events:
            agent = event.get('agent')
            patient = event.get('patient')
            event_type = event.get('type', '').lower()
            
            # Fix: If agent == patient, decide based on action type
            if agent and patient and str(agent).lower() == str(patient).lower():
                if event_type in NO_PATIENT_ACTIONS:
                    event['patient'] = None
            
            fixed_events.append(event)
        
        return fixed_events
    
    def preprocess_chapter_events(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> List[Event]:
        """
        Full preprocessing pipeline for chapter events.
        
        Combines validation, ID assignment, and Event object creation.
        
        Args:
            structured_data: Structured chapter data from LLM extraction
            chapter_num: Current chapter number
            
        Returns:
            List of Event objects ready for execution
        """
        events_data = structured_data.get("events", [])
        events_data = self.validate_and_fix_events(events_data)
        events_data = self.assign_global_event_ids(events_data, chapter_num)
        structured_data["events"] = events_data
        
        events = []
        for i, event_data in enumerate(events_data):
            time = self.state_manager.current_time + i
            event = self.create_event(event_data, time=time, chapter_num=chapter_num)
            events.append(event)
        
        return events
    
    def extract_entities_from_events(self, events: List[Dict[str, Any]]) -> Set[str]:
        """
        Extract all entity IDs referenced in a list of events.
        
        Extracts from fields: agent, patient, location, item, object
        
        Args:
            events: List of event dictionaries
            
        Returns:
            Set of canonical entity IDs
        """
        entities: Set[str] = set()
        
        for event in events:
            self._extract_entity_from_field(entities, event, "agent")
            self._extract_entity_from_field(entities, event, "patient")
            self._extract_entity_from_field(entities, event, "location")
            self._extract_entity_from_field(entities, event, "item")
            self._extract_entity_from_field(entities, event, "object")
        
        # Filter out empty/unknown values
        entities.discard("")
        entities.discard("unknown")
        entities.discard("none")
        entities.discard(None)
        
        return entities
    
    def _extract_entity_from_field(
        self,
        entities: Set[str],
        event: Dict[str, Any],
        field: str,
    ) -> None:
        """Extract entity from a single event field."""
        if event.get(field):
            entities.add(event[field])
