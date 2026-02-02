"""
Tests for Active Universe Computation

Tests the ASP-visible entity filtering introduced in Phase 8.6.
Verifies that only relevant entities are included in the active universe.
"""

import pytest
from unittest.mock import MagicMock, patch
from engine.active_universe import (
    compute_active_universe,
    compute_active_universe_from_state_manager,
    ActiveUniverseResult,
    extract_entities_from_events,
    filter_asp_facts_by_universe,
    # Time scoping
    TimeScope,
    compute_time_scope,
    filter_facts_by_time_scope,
)
from engine.entity_registry import EntityRegistry, EntityType, LifecycleState
from engine.item_tracker import ItemTracker, TrackedItem, ItemLifecycleState


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def entity_registry():
    """Create an EntityRegistry with sample entities."""
    registry = EntityRegistry()
    # Characters
    registry.register_entity("harry", EntityType.CHARACTER, chapter=0)
    registry.register_entity("ron", EntityType.CHARACTER, chapter=0)
    registry.register_entity("hermione", EntityType.CHARACTER, chapter=0)
    registry.register_entity("dumbledore", EntityType.CHARACTER, chapter=1)
    registry.register_entity("snape", EntityType.CHARACTER, chapter=2)
    registry.register_entity("voldemort", EntityType.CHARACTER, chapter=5)
    # Items
    registry.register_entity("wand", EntityType.ITEM, chapter=0)
    registry.register_entity("invisibility_cloak", EntityType.ITEM, chapter=1)
    registry.register_entity("sword_of_gryffindor", EntityType.ITEM, chapter=10)
    # Locations
    registry.register_entity("hogwarts", EntityType.LOCATION, chapter=0)
    registry.register_entity("forbidden_forest", EntityType.LOCATION, chapter=2)
    return registry


@pytest.fixture
def item_tracker():
    """Create an ItemTracker with sample items."""
    tracker = ItemTracker()
    # Use the internal _items dict to set up test items
    # (ItemTracker normally populates via process_extraction)
    tracker._items["wand"] = TrackedItem(
        item_id="wand",
        name="Wand",
        carrier="harry",
    )
    tracker._items["invisibility_cloak"] = TrackedItem(
        item_id="invisibility_cloak",
        name="Invisibility Cloak",
        carrier="harry",
    )
    tracker._items["sword_of_gryffindor"] = TrackedItem(
        item_id="sword_of_gryffindor",
        name="Sword of Gryffindor",
        carrier="dumbledore",
    )
    return tracker


@pytest.fixture
def relationships():
    """Create sample relationships."""
    return {
        ("harry", "ron"): "friends",
        ("harry", "hermione"): "friends",
        ("ron", "hermione"): "friends",
        ("harry", "dumbledore"): "mentor",
        ("harry", "voldemort"): "enemies",
    }


# =============================================================================
# Tests for extract_entities_from_events
# =============================================================================

class TestExtractEntitiesFromEvents:
    """Tests for the extract_entities_from_events helper."""
    
    def test_extract_empty_events(self):
        """Empty event list returns empty set."""
        result = extract_entities_from_events([])
        assert result == set()
    
    def test_extract_agent_only(self):
        """Extract agent from event."""
        events = [{"agent": "harry", "type": "move"}]
        result = extract_entities_from_events(events)
        assert result == {"harry"}
    
    def test_extract_agent_and_patient(self):
        """Extract both agent and patient."""
        events = [{"agent": "harry", "patient": "draco", "type": "attack"}]
        result = extract_entities_from_events(events)
        assert result == {"harry", "draco"}
    
    def test_extract_location(self):
        """Extract location from event."""
        events = [{"agent": "harry", "location": "hogwarts", "type": "move"}]
        result = extract_entities_from_events(events)
        assert result == {"harry", "hogwarts"}
    
    def test_extract_item(self):
        """Extract item from event."""
        events = [{"agent": "harry", "item": "wand", "type": "acquire"}]
        result = extract_entities_from_events(events)
        assert result == {"harry", "wand"}
    
    def test_extract_object(self):
        """Extract object from event."""
        events = [{"agent": "harry", "object": "door", "type": "open"}]
        result = extract_entities_from_events(events)
        assert result == {"harry", "door"}
    
    def test_extract_all_fields(self):
        """Extract from all relevant fields."""
        events = [{
            "agent": "harry",
            "patient": "draco",
            "location": "hogwarts",
            "item": "wand",
            "object": "door",
            "type": "complex_event",
        }]
        result = extract_entities_from_events(events)
        assert result == {"harry", "draco", "hogwarts", "wand", "door"}
    
    def test_extract_multiple_events(self):
        """Extract from multiple events."""
        events = [
            {"agent": "harry", "location": "hogwarts"},
            {"agent": "ron", "location": "hogwarts"},
            {"agent": "hermione", "location": "library"},
        ]
        result = extract_entities_from_events(events)
        assert result == {"harry", "ron", "hermione", "hogwarts", "library"}
    
    def test_filter_empty_values(self):
        """Filter out empty string values."""
        events = [{"agent": "harry", "patient": "", "location": "unknown"}]
        result = extract_entities_from_events(events)
        assert result == {"harry"}  # Empty and "unknown" filtered
    
    def test_filter_none_values(self):
        """Filter out None values."""
        events = [{"agent": "harry", "patient": None}]
        result = extract_entities_from_events(events)
        assert result == {"harry"}


# =============================================================================
# Tests for compute_active_universe
# =============================================================================

class TestComputeActiveUniverse:
    """Tests for the main compute_active_universe function."""
    
    def test_empty_events(self, entity_registry, relationships):
        """Empty events result in empty universe."""
        result = compute_active_universe(
            current_chapter_events=[],
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships=relationships,
        )
        assert result.characters == set()
        assert result.items == set()
        assert result.locations == set()
    
    def test_current_chapter_characters(self, entity_registry, relationships):
        """Characters from current chapter events are included."""
        events = [{"agent": "harry", "patient": "ron"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships={},  # No relationships
        )
        assert "harry" in result.characters
        assert "ron" in result.characters
    
    def test_previous_chapter_characters(self, entity_registry, relationships):
        """Characters from previous chapter are included."""
        current = [{"agent": "harry"}]
        previous = [{"agent": "hermione"}]
        result = compute_active_universe(
            current_chapter_events=current,
            previous_chapter_events=previous,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships={},
        )
        assert "harry" in result.characters
        assert "hermione" in result.characters
    
    def test_relationship_expansion(self, entity_registry, relationships):
        """Relationship partners are included via 1-hop expansion."""
        events = [{"agent": "harry"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships=relationships,
        )
        # Harry's relationships: ron, hermione, dumbledore, voldemort
        assert "harry" in result.characters
        assert "ron" in result.characters  # friend
        assert "hermione" in result.characters  # friend
        assert "dumbledore" in result.characters  # mentor
        assert "voldemort" in result.characters  # enemy
    
    def test_no_transitive_expansion(self, entity_registry):
        """Expansion is only 1-hop, not transitive."""
        # snape is related to dumbledore, but not to harry
        relationships = {
            ("harry", "ron"): "friends",
            ("dumbledore", "snape"): "colleagues",
        }
        events = [{"agent": "harry"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships=relationships,
        )
        assert "harry" in result.characters
        assert "ron" in result.characters  # 1-hop
        assert "snape" not in result.characters  # 2-hop (dumbledore not active)
    
    def test_item_expansion(self, entity_registry, item_tracker, relationships):
        """Carried items are included via 1-hop expansion."""
        events = [{"agent": "harry"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=item_tracker,
            relationships={},
        )
        assert "harry" in result.characters
        assert "wand" in result.items  # Carried by harry
        assert "invisibility_cloak" in result.items  # Carried by harry
        assert "sword_of_gryffindor" not in result.items  # Carried by dumbledore
    
    def test_locations_from_events(self, entity_registry, relationships):
        """Locations from events are included."""
        events = [{"agent": "harry", "location": "hogwarts"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships={},
        )
        assert "hogwarts" in result.locations
    
    def test_unregistered_entity_fallback(self, entity_registry, relationships):
        """Unregistered entities are classified as locations by default."""
        events = [{"agent": "unknown_character", "location": "some_place"}]
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships={},
        )
        # unknown_character is not registered, defaults to location
        assert "unknown_character" in result.locations
        assert "some_place" in result.locations
    
    def test_statistics_tracking(self, entity_registry, item_tracker, relationships):
        """Statistics are correctly tracked."""
        current = [{"agent": "harry", "patient": "ron"}]
        previous = [{"agent": "hermione"}]
        result = compute_active_universe(
            current_chapter_events=current,
            previous_chapter_events=previous,
            entity_registry=entity_registry,
            item_tracker=item_tracker,
            relationships=relationships,
        )
        assert result.current_chapter_actors == 2  # harry, ron
        assert result.previous_chapter_actors == 1  # hermione
        assert result.relationship_expansions > 0  # At least some expansions
    
    def test_deterministic_output(self, entity_registry, item_tracker, relationships):
        """Output is deterministic (same input = same output)."""
        events = [{"agent": "harry"}, {"agent": "ron"}]
        result1 = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=item_tracker,
            relationships=relationships,
        )
        result2 = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=item_tracker,
            relationships=relationships,
        )
        assert result1.characters == result2.characters
        assert result1.items == result2.items
        assert result1.locations == result2.locations


# =============================================================================
# Tests for ActiveUniverseResult
# =============================================================================

class TestActiveUniverseResult:
    """Tests for the ActiveUniverseResult dataclass."""
    
    def test_all_entities(self):
        """all_entities returns union of all sets."""
        result = ActiveUniverseResult(
            characters={"harry", "ron"},
            items={"wand"},
            locations={"hogwarts"},
        )
        assert result.all_entities == {"harry", "ron", "wand", "hogwarts"}
    
    def test_total_count(self):
        """total_count returns sum of all sets."""
        result = ActiveUniverseResult(
            characters={"harry", "ron"},
            items={"wand"},
            locations={"hogwarts"},
        )
        assert result.total_count == 4
    
    def test_contains(self):
        """contains checks all sets."""
        result = ActiveUniverseResult(
            characters={"harry"},
            items={"wand"},
            locations={"hogwarts"},
        )
        assert result.contains("harry")
        assert result.contains("wand")
        assert result.contains("hogwarts")
        assert not result.contains("voldemort")
    
    def test_to_dict(self):
        """to_dict returns serializable dictionary."""
        result = ActiveUniverseResult(
            characters={"harry", "ron"},
            items={"wand"},
            locations={"hogwarts"},
            current_chapter_actors=2,
            previous_chapter_actors=1,
            relationship_expansions=3,
            item_expansions=1,
        )
        d = result.to_dict()
        assert d["characters"] == ["harry", "ron"]  # sorted
        assert d["items"] == ["wand"]
        assert d["locations"] == ["hogwarts"]
        assert d["statistics"]["total"] == 4
        assert d["statistics"]["current_chapter_actors"] == 2


# =============================================================================
# Tests for compute_active_universe_from_state_manager
# =============================================================================

class TestComputeActiveUniverseFromStateManager:
    """Tests for the StateManager convenience function."""
    
    def test_extracts_from_state_manager(self, entity_registry, item_tracker, relationships):
        """Correctly extracts dependencies from StateManager."""
        # Create mock StateManager
        state_manager = MagicMock()
        state_manager.entity_registry = entity_registry
        state_manager.persistent_relationships = relationships
        
        events = [{"agent": "harry"}]
        result = compute_active_universe_from_state_manager(
            current_chapter_events=events,
            previous_chapter_events=None,
            state_manager=state_manager,
            item_tracker=item_tracker,
        )
        
        assert "harry" in result.characters
        assert "ron" in result.characters  # From relationships


# =============================================================================
# Tests for filter_asp_facts_by_universe
# =============================================================================

class TestFilterAspFactsByUniverse:
    """Tests for ASP fact filtering."""
    
    def test_filter_keeps_matching_facts(self):
        """Facts with entities in universe are kept."""
        universe = ActiveUniverseResult(
            characters={"harry", "ron"},
            items={"wand"},
            locations={"hogwarts"},
        )
        facts = [
            "character(harry).",
            "at(harry, hogwarts).",
            "holds(harry, wand).",
        ]
        result = filter_asp_facts_by_universe(facts, universe)
        assert len(result) == 3
    
    def test_filter_removes_non_matching(self):
        """Facts with entities not in universe are removed."""
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations={"hogwarts"},
        )
        facts = [
            "character(harry).",  # Keep
            "at(voldemort, hogwarts).",  # Remove - voldemort not in universe
        ]
        result = filter_asp_facts_by_universe(facts, universe)
        assert "character(harry)." in result
        assert "at(voldemort, hogwarts)." not in result
    
    def test_filter_keeps_comments(self):
        """Comments are preserved."""
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
        )
        facts = [
            "% This is a comment",
            "character(harry).",
        ]
        result = filter_asp_facts_by_universe(facts, universe)
        assert "% This is a comment" in result
    
    def test_filter_keeps_empty_lines(self):
        """Empty lines are preserved."""
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
        )
        facts = [
            "character(harry).",
            "",
            "at(harry, hogwarts).",
        ]
        result = filter_asp_facts_by_universe(facts, universe)
        assert "" in result
    
    def test_filter_ignores_numeric_args(self):
        """Numeric arguments are ignored (not entity IDs)."""
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
        )
        facts = [
            "event(harry, 5).",  # 5 is a time, not an entity
        ]
        result = filter_asp_facts_by_universe(facts, universe)
        assert "event(harry, 5)." in result


# =============================================================================
# Integration Tests
# =============================================================================

class TestActiveUniverseIntegration:
    """Integration tests with realistic scenarios."""
    
    def test_chapter_transition_scenario(self, entity_registry, item_tracker):
        """Test realistic chapter transition scenario."""
        # Chapter 5: Harry and Ron explore
        chapter_5_events = [
            {"agent": "harry", "location": "forbidden_forest"},
            {"agent": "ron", "patient": "harry"},
        ]
        
        # Chapter 6: Harry confronts Snape
        chapter_6_events = [
            {"agent": "harry", "patient": "snape", "location": "dungeon"},
        ]
        
        # Relationships
        relationships = {
            ("harry", "ron"): "friends",
            ("harry", "hermione"): "friends",
            ("snape", "dumbledore"): "colleagues",
        }
        
        result = compute_active_universe(
            current_chapter_events=chapter_6_events,
            previous_chapter_events=chapter_5_events,
            entity_registry=entity_registry,
            item_tracker=item_tracker,
            relationships=relationships,
        )
        
        # Current chapter actors
        assert "harry" in result.characters
        assert "snape" in result.characters
        
        # Previous chapter actors
        assert "ron" in result.characters
        
        # 1-hop relationships from harry
        assert "hermione" in result.characters  # Friend
        
        # 1-hop relationships from snape
        assert "dumbledore" in result.characters  # Colleague
        
        # Items carried by harry
        assert "wand" in result.items
        assert "invisibility_cloak" in result.items
        
        # Locations from events
        assert "dungeon" in result.locations or "dungeon" in result.all_entities
        assert "forbidden_forest" in result.locations or "forbidden_forest" in result.all_entities
    
    def test_excludes_inactive_entities(self, entity_registry, item_tracker):
        """Entities not in active universe are excluded."""
        events = [{"agent": "harry"}]
        relationships = {}  # No relationships to expand
        
        # Make a simple ItemTracker with no items carried
        simple_tracker = ItemTracker()
        
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=simple_tracker,
            relationships=relationships,
        )
        
        # Only harry should be included
        assert result.characters == {"harry"}
        # Other characters not included
        assert "ron" not in result.characters
        assert "hermione" not in result.characters
        assert "voldemort" not in result.characters


# =============================================================================
# Edge Cases
# =============================================================================

class TestActiveUniverseEdgeCases:
    """Edge case tests."""
    
    def test_self_relationship(self, entity_registry):
        """Handle self-referential relationships gracefully."""
        relationships = {("harry", "harry"): "self"}
        events = [{"agent": "harry"}]
        
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships=relationships,
        )
        assert "harry" in result.characters
    
    def test_empty_entity_registry(self):
        """Handle empty entity registry."""
        registry = EntityRegistry()
        events = [{"agent": "harry"}]
        
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=registry,
            item_tracker=None,
            relationships={},
        )
        # Unregistered entities fall back to locations
        assert "harry" in result.all_entities
    
    def test_bidirectional_relationship_expansion(self, entity_registry):
        """Both directions of relationships are expanded."""
        relationships = {("harry", "ron"): "friends"}
        # Ron is in event, should expand to harry
        events = [{"agent": "ron"}]
        
        result = compute_active_universe(
            current_chapter_events=events,
            previous_chapter_events=None,
            entity_registry=entity_registry,
            item_tracker=None,
            relationships=relationships,
        )
        assert "ron" in result.characters
        assert "harry" in result.characters  # Expanded via relationship


# =============================================================================
# Tests for Time Scoping (Phase 8.7)
# =============================================================================

class TestTimeScope:
    """Tests for the TimeScope dataclass."""
    
    def test_is_time_in_scope_current_chapter(self):
        """Times in current chapter are in scope."""
        scope = TimeScope(
            current_chapter=5,
            current_time_start=100,
            current_time_end=110,
        )
        assert scope.is_time_in_scope(100)
        assert scope.is_time_in_scope(105)
        assert scope.is_time_in_scope(110)
        assert not scope.is_time_in_scope(99)
        assert not scope.is_time_in_scope(111)
    
    def test_is_time_in_scope_previous_chapter(self):
        """Times in previous chapter are in scope."""
        scope = TimeScope(
            current_chapter=5,
            current_time_start=100,
            current_time_end=110,
            previous_time_start=80,
            previous_time_end=95,
        )
        assert scope.is_time_in_scope(80)
        assert scope.is_time_in_scope(90)
        assert scope.is_time_in_scope(95)
        assert not scope.is_time_in_scope(79)
        assert not scope.is_time_in_scope(96)
        assert not scope.is_time_in_scope(99)  # Gap between chapters
    
    def test_get_time_facts(self):
        """get_time_facts generates correct ASP facts."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=52,
            previous_time_start=40,
            previous_time_end=42,
        )
        facts = scope.get_time_facts()
        facts_str = "\n".join(facts)
        
        assert "current_chapter(3)." in facts_str
        assert "current_time_window(50, 52)." in facts_str
        assert "previous_time_window(40, 42)." in facts_str
        assert "previous_chapter(2)." in facts_str
        
        # Time facts for current chapter
        assert "time(50)." in facts_str
        assert "time(51)." in facts_str
        assert "time(52)." in facts_str
        
        # Time facts for previous chapter
        assert "time(40)." in facts_str
        assert "time(41)." in facts_str
        assert "time(42)." in facts_str
        
        # No time facts outside scope
        assert "time(49)." not in facts_str
        assert "time(53)." not in facts_str
    
    def test_to_dict(self):
        """to_dict serializes correctly."""
        scope = TimeScope(
            current_chapter=5,
            current_time_start=100,
            current_time_end=110,
            previous_time_start=80,
            previous_time_end=95,
        )
        d = scope.to_dict()
        assert d["current_chapter"] == 5
        assert d["current_time_start"] == 100
        assert d["previous_time_end"] == 95


class TestComputeTimeScope:
    """Tests for compute_time_scope function."""
    
    def test_compute_from_global_ids(self):
        """Compute time scope from event global IDs."""
        current_events = [
            {"global_id": "e100", "type": "action"},
            {"global_id": "e101", "type": "move"},
            {"global_id": "e105", "type": "speak"},
        ]
        previous_events = [
            {"global_id": "e90", "type": "action"},
            {"global_id": "e95", "type": "action"},
        ]
        
        scope = compute_time_scope(
            current_chapter=5,
            current_chapter_events=current_events,
            previous_chapter_events=previous_events,
        )
        
        assert scope.current_chapter == 5
        assert scope.current_time_start == 100
        assert scope.current_time_end == 105
        assert scope.previous_time_start == 90
        assert scope.previous_time_end == 95
    
    def test_compute_without_previous_chapter(self):
        """Compute time scope for first chapter (no previous)."""
        current_events = [
            {"global_id": "e1", "type": "action"},
            {"global_id": "e5", "type": "action"},
        ]
        
        scope = compute_time_scope(
            current_chapter=0,
            current_chapter_events=current_events,
            previous_chapter_events=None,
        )
        
        assert scope.current_chapter == 0
        assert scope.current_time_start == 1
        assert scope.current_time_end == 5
        assert scope.previous_time_start is None
        assert scope.previous_time_end is None
    
    def test_compute_empty_events(self):
        """Handle empty events list."""
        scope = compute_time_scope(
            current_chapter=3,
            current_chapter_events=[],
            previous_chapter_events=None,
        )
        
        assert scope.current_time_start == 1
        assert scope.current_time_end == 1


class TestFilterFactsByTimeScope:
    """Tests for filter_facts_by_time_scope function."""
    
    def test_filter_keeps_in_scope_time_facts(self):
        """Time facts in scope are kept."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=55,
        )
        facts = [
            "time(50).",
            "time(52).",
            "time(55).",
        ]
        
        result = filter_facts_by_time_scope(facts, scope)
        assert "time(50)." in result
        assert "time(52)." in result
        assert "time(55)." in result
    
    def test_filter_removes_out_of_scope_time_facts(self):
        """Time facts outside scope are removed."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=55,
        )
        facts = [
            "time(49).",  # Before scope
            "time(50).",  # In scope
            "time(56).",  # After scope
            "time(100).", # Way after scope
        ]
        
        result = filter_facts_by_time_scope(facts, scope)
        assert "time(50)." in result
        assert "time(49)." not in result
        assert "time(56)." not in result
        assert "time(100)." not in result
    
    def test_filter_keeps_comments(self):
        """Comments are preserved."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=55,
        )
        facts = [
            "% This is a comment",
            "time(50).",
        ]
        
        result = filter_facts_by_time_scope(facts, scope)
        assert "% This is a comment" in result
    
    def test_filter_keeps_non_time_facts(self):
        """Entity and other facts without time are kept."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=55,
        )
        facts = [
            "character(harry).",
            "item(wand).",
            "relationship(harry, ron, friend).",
            "time(50).",
        ]
        
        result = filter_facts_by_time_scope(facts, scope)
        assert "character(harry)." in result
        assert "item(wand)." in result
        assert "relationship(harry, ron, friend)." in result
    
    def test_filter_event_time_facts(self):
        """event_time/2 facts are filtered by time scope."""
        scope = TimeScope(
            current_chapter=3,
            current_time_start=50,
            current_time_end=55,
        )
        facts = [
            "event_time(e50, 50).",  # In scope
            "event_time(e55, 55).",  # In scope
            "event_time(e49, 49).",  # Out of scope
            "event_time(e100, 100).",  # Out of scope
        ]
        
        result = filter_facts_by_time_scope(facts, scope)
        assert "event_time(e50, 50)." in result
        assert "event_time(e55, 55)." in result
        assert "event_time(e49, 49)." not in result
        assert "event_time(e100, 100)." not in result