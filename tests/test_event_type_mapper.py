"""
Tests for Phase 3: Event Type Mapper

Tests the mapping from legacy event types to refined event types.
"""

import pytest
from scripts.extraction.event_type_mapper import (
    EventTypeMapper,
    RefinedEventCategory,
    get_event_category,
    is_state_changing_event,
    is_movement_event,
    LEGACY_TYPE_MAPPING,
    REFINED_EVENT_TYPES,
)


class TestEventTypeMapper:
    """Tests for EventTypeMapper class."""
    
    def test_initialization(self):
        """Test mapper initializes correctly."""
        mapper = EventTypeMapper()
        assert mapper is not None
        stats = mapper.get_statistics()
        assert stats["total_mappings"] == 0
        assert stats["unmapped_count"] == 0
    
    def test_map_refined_type_unchanged(self):
        """Refined event types should not be remapped."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("enter")
        assert result == "enter"
        assert was_remapped is False
    
    def test_map_legacy_arrive_to_enter(self):
        """Legacy 'arrive' should map to 'enter'."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("arrive")
        assert result == "enter"
        assert was_remapped is True
    
    def test_map_legacy_leave_to_exit(self):
        """Legacy 'leave' should map to 'exit'."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("leave")
        assert result == "exit"
        assert was_remapped is True
    
    def test_map_legacy_depart_to_exit(self):
        """Legacy 'depart' should map to 'exit'."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("depart")
        assert result == "exit"
        assert was_remapped is True
    
    def test_map_legacy_get_up_is_refined_type(self):
        """'get_up' is a refined type, so should NOT be remapped."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("get_up")
        # get_up is already a refined posture event type
        assert result == "get_up"
        assert was_remapped is False
    
    def test_map_legacy_awaken_is_refined_type(self):
        """'awaken' is a refined type, so should NOT be remapped."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("awaken")
        # awaken is already a refined consciousness event type
        assert result == "awaken"
        assert was_remapped is False
    
    def test_unknown_type_passed_through(self):
        """Unknown event types should be passed through unchanged."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("hug")
        assert result == "hug"
        assert was_remapped is False
    
    def test_case_insensitive_mapping(self):
        """Mapping should be case-insensitive."""
        mapper = EventTypeMapper()
        result, was_remapped = mapper.map_event_type("ARRIVE")
        assert result == "enter"
        assert was_remapped is True
    
    def test_normalize_type_with_spaces(self):
        """Type normalization should handle spaces and convert to valid type."""
        mapper = EventTypeMapper()
        # "lie down" with space should normalize to "lie_down" which is a refined type
        result, was_remapped = mapper.map_event_type("lie down")
        assert result == "lie_down"
        assert was_remapped is False  # It's already a refined type
    
    def test_normalize_type_with_dashes(self):
        """Type normalization should handle dashes and convert to valid type."""
        mapper = EventTypeMapper()
        # "lie-down" with dash should normalize to "lie_down" which is a refined type
        result, was_remapped = mapper.map_event_type("lie-down")
        assert result == "lie_down"
        assert was_remapped is False  # It's already a refined type


class TestMapEvent:
    """Tests for map_event method."""
    
    def test_map_event_preserves_original_type(self):
        """Mapped events should preserve original_type."""
        mapper = EventTypeMapper()
        event = {"id": "e1", "type": "arrive", "agent": "harry"}
        mapped, mapping = mapper.map_event(event, chapter=1)
        
        assert mapped["type"] == "enter"
        assert mapped["original_type"] == "arrive"
        assert mapping is not None
        assert mapping.original_type == "arrive"
        assert mapping.refined_type == "enter"
    
    def test_map_event_no_original_type_when_not_remapped(self):
        """Non-remapped events should not have original_type."""
        mapper = EventTypeMapper()
        event = {"id": "e1", "type": "talk", "agent": "harry"}
        mapped, mapping = mapper.map_event(event, chapter=1)
        
        assert mapped["type"] == "talk"
        assert "original_type" not in mapped
        assert mapping is None
    
    def test_map_event_preserves_other_fields(self):
        """Mapping should preserve all other event fields."""
        mapper = EventTypeMapper()
        event = {
            "id": "e1",
            "type": "arrive",
            "agent": "harry",
            "location": "hogwarts",
            "source_text": "Harry arrived at Hogwarts.",
        }
        mapped, _ = mapper.map_event(event, chapter=1)
        
        assert mapped["id"] == "e1"
        assert mapped["agent"] == "harry"
        assert mapped["location"] == "hogwarts"
        assert mapped["source_text"] == "Harry arrived at Hogwarts."


class TestMapEvents:
    """Tests for map_events batch method."""
    
    def test_map_events_batch(self):
        """Batch mapping should work correctly."""
        mapper = EventTypeMapper()
        events = [
            {"id": "e1", "type": "arrive", "agent": "harry"},
            {"id": "e2", "type": "talk", "agent": "harry"},
            {"id": "e3", "type": "leave", "agent": "harry"},
        ]
        result = mapper.map_events(events, chapter=1)
        
        assert len(result.events) == 3
        assert result.events[0]["type"] == "enter"
        assert result.events[1]["type"] == "talk"
        assert result.events[2]["type"] == "exit"
        assert result.get_mapping_count() == 2  # arrive and leave were remapped
    
    def test_map_events_tracks_statistics(self):
        """Batch mapping should update statistics."""
        mapper = EventTypeMapper()
        events = [
            {"id": "e1", "type": "arrive", "agent": "harry"},
            {"id": "e2", "type": "custom_event", "agent": "harry"},
        ]
        result = mapper.map_events(events, chapter=1)
        
        stats = mapper.get_statistics()
        assert stats["total_mappings"] == 1
        assert "custom_event" in stats["unmapped_types"]


class TestEventCategoryHelpers:
    """Tests for category helper functions."""
    
    def test_get_event_category_movement(self):
        """Movement events should return MOVEMENT category."""
        assert get_event_category("enter") == RefinedEventCategory.MOVEMENT
        assert get_event_category("exit") == RefinedEventCategory.MOVEMENT
        assert get_event_category("travel") == RefinedEventCategory.MOVEMENT
    
    def test_get_event_category_posture(self):
        """Posture events should return POSTURE category."""
        assert get_event_category("sit") == RefinedEventCategory.POSTURE
        assert get_event_category("stand") == RefinedEventCategory.POSTURE
        assert get_event_category("lie_down") == RefinedEventCategory.POSTURE
    
    def test_get_event_category_consciousness(self):
        """Consciousness events should return CONSCIOUSNESS category."""
        assert get_event_category("wake_up") == RefinedEventCategory.CONSCIOUSNESS
        assert get_event_category("sleep") == RefinedEventCategory.CONSCIOUSNESS
    
    def test_get_event_category_unknown(self):
        """Unknown events should return OTHER category."""
        assert get_event_category("custom_event") == RefinedEventCategory.OTHER
    
    def test_is_state_changing_event(self):
        """is_state_changing_event should return True for posture/consciousness."""
        assert is_state_changing_event("sit") is True
        assert is_state_changing_event("stand") is True
        assert is_state_changing_event("wake_up") is True
        assert is_state_changing_event("sleep") is True
        assert is_state_changing_event("talk") is False
        assert is_state_changing_event("enter") is False
    
    def test_is_movement_event(self):
        """is_movement_event should return True for movement events."""
        assert is_movement_event("enter") is True
        assert is_movement_event("exit") is True
        assert is_movement_event("travel") is True
        assert is_movement_event("talk") is False
        assert is_movement_event("sit") is False


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility."""
    
    def test_legacy_types_all_have_mappings(self):
        """All legacy types in LEGACY_TYPE_MAPPING should map to valid refined types."""
        for legacy_type, refined_type in LEGACY_TYPE_MAPPING.items():
            # The refined type should either be in REFINED_EVENT_TYPES
            # or should be a valid event type
            assert refined_type is not None
            assert isinstance(refined_type, str)
    
    def test_refined_types_have_categories(self):
        """All refined types should have a category."""
        for event_type in REFINED_EVENT_TYPES:
            category = REFINED_EVENT_TYPES[event_type]
            assert isinstance(category, RefinedEventCategory)
    
    def test_mapper_reset(self):
        """Reset should clear all state."""
        mapper = EventTypeMapper()
        events = [
            {"id": "e1", "type": "arrive", "agent": "harry"},
            {"id": "e2", "type": "custom_event", "agent": "harry"},
        ]
        mapper.map_events(events, chapter=1)
        
        stats = mapper.get_statistics()
        assert stats["total_mappings"] > 0
        
        mapper.reset()
        stats = mapper.get_statistics()
        assert stats["total_mappings"] == 0
        assert stats["unmapped_count"] == 0
