"""
Tests for PostSalvageReconciler.

Tests the conservative post-salvage reconciliation step that runs AFTER JSON
salvage but BEFORE EventNormalizer validation.
"""

import pytest
from scripts.extraction.entity_registry import EntityRegistry
from scripts.extraction.relationship_normalizer import RelationshipNormalizer
from scripts.extraction.post_salvage_reconciler import (
    PostSalvageReconciler,
    ReconciliationResult,
    reconcile_salvaged_events,
)


@pytest.fixture
def dursley_registry():
    """Registry with the Dursley family characters."""
    registry = EntityRegistry()
    registry.register_characters([
        {"id": "uncle_vernon", "name": "Vernon Dursley", "aliases": ["uncle_vernon", "mr_dursley", "vernon"]},
        {"id": "aunt_petunia", "name": "Petunia Dursley", "aliases": ["aunt_petunia", "mrs_dursley", "petunia"]},
        {"id": "dudley", "name": "Dudley Dursley", "aliases": ["dudley", "big_d"]},
        {"id": "harry_potter", "name": "Harry Potter", "aliases": ["harry", "the_boy_who_lived"]},
    ])
    registry.register_locations([
        {"id": "privet_drive", "name": "4 Privet Drive", "aliases": ["privet_drive", "number_four"]},
        {"id": "kitchen", "name": "Kitchen"},
        {"id": "cupboard_under_stairs", "name": "Cupboard Under the Stairs", "aliases": ["cupboard"]},
    ])
    return registry


@pytest.fixture
def dursley_normalizer(dursley_registry):
    """RelationshipNormalizer with Dursley family groups."""
    normalizer = RelationshipNormalizer(dursley_registry)
    # Add the dursleys as a group
    normalizer.add_group("dursleys", ["uncle_vernon", "aunt_petunia", "dudley"])
    return normalizer


class TestAgentReconciliation:
    """Tests for agent/group reconciliation."""
    
    def test_valid_agent_unchanged(self, dursley_registry):
        """Valid agents should pass through unchanged."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "harry_potter", "location": "privet_drive"}]
        
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 1
        assert result.agent_remaps == 0
        assert result.events[0]["agent"] == "harry_potter"
    
    def test_agent_alias_normalized(self, dursley_registry):
        """Agent aliases should be resolved to canonical ID."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "vernon", "location": "privet_drive"}]
        
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 1
        assert result.events[0]["agent"] == "uncle_vernon"
    
    def test_group_agent_single_member(self, dursley_registry):
        """Group with only one valid member should map to that member."""
        # Create a registry with only one member of the "dursleys" family
        registry = EntityRegistry()
        registry.register_characters([
            {"id": "uncle_vernon", "name": "Vernon Dursley", "aliases": ["vernon"]},
        ])
        
        reconciler = PostSalvageReconciler(registry)
        # Manually add a group with one member
        reconciler._groups["dursleys"] = {"uncle_vernon"}
        
        events = [{"id": "e1", "type": "escape", "agent": "dursleys"}]
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 1
        assert result.agent_remaps == 1
        assert result.events[0]["agent"] == "uncle_vernon"
        assert result.events[0].get("_reconciled") is True
        assert result.events[0].get("_reconciliation_type") == "group_to_single"
    
    def test_group_agent_expansion(self, dursley_registry, dursley_normalizer):
        """Group agent should expand to multiple events (one per member)."""
        reconciler = PostSalvageReconciler(dursley_registry, dursley_normalizer)
        
        events = [{"id": "e1", "type": "escape", "agent": "dursleys", "location": "privet_drive"}]
        result = reconciler.reconcile(events)
        
        # Should expand to 3 events (one per Dursley family member)
        assert result.reconciled_count == 3
        assert result.expanded_count == 2  # 3 - 1 original
        
        agents = {e["agent"] for e in result.events}
        assert agents == {"uncle_vernon", "aunt_petunia", "dudley"}
        
        # All should have the same type and location
        for event in result.events:
            assert event["type"] == "escape"
            assert event["location"] == "privet_drive"
            assert event.get("_reconciled") is True
    
    def test_unknown_agent_unchanged(self, dursley_registry):
        """Unknown agents that aren't groups should pass through unchanged."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "unknown_person"}]
        
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 1
        assert result.agent_remaps == 0
        assert result.unchanged_count == 1
        assert result.events[0]["agent"] == "unknown_person"
    
    def test_the_prefix_group(self, dursley_registry, dursley_normalizer):
        """Groups with 'the_' prefix should also work."""
        reconciler = PostSalvageReconciler(dursley_registry, dursley_normalizer)
        # Add the_dursleys as a group
        reconciler._groups["the_dursleys"] = {"uncle_vernon", "aunt_petunia", "dudley"}
        
        events = [{"id": "e1", "type": "escape", "agent": "the_dursleys"}]
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 3
        assert result.expanded_count == 2


class TestLocationReconciliation:
    """Tests for location reconciliation."""
    
    def test_valid_location_unchanged(self, dursley_registry):
        """Valid locations should pass through unchanged."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "harry_potter", "location": "privet_drive"}]
        
        result = reconciler.reconcile(events)
        
        assert result.location_remaps == 0
        assert result.events[0]["location"] == "privet_drive"
    
    def test_location_alias_normalized(self, dursley_registry):
        """Location name should be resolved to canonical ID."""
        reconciler = PostSalvageReconciler(dursley_registry)
        # Use the name "4 Privet Drive" which should resolve to "privet_drive"
        events = [{"id": "e1", "type": "talk", "agent": "harry_potter", "location": "4 Privet Drive"}]
        
        result = reconciler.reconcile(events)
        
        assert result.events[0]["location"] == "privet_drive"
    
    def test_location_suffix_match(self, dursley_registry):
        """Locations matching as suffix should be remapped."""
        # Add a location that ends with _stairs
        dursley_registry.register_locations([
            {"id": "stairs", "name": "Stairs"},  # This won't match
        ])
        
        reconciler = PostSalvageReconciler(dursley_registry)
        # "stairs" is a suffix of "cupboard_under_stairs" but not unique
        events = [{"id": "e1", "type": "escape", "agent": "harry_potter", "location": "stairs"}]
        
        result = reconciler.reconcile(events)
        
        # "stairs" is now a registered location, should resolve directly
        assert result.events[0]["location"] == "stairs"
    
    def test_location_prefix_match(self, dursley_registry):
        """Locations matching as prefix should be remapped if unique."""
        reconciler = PostSalvageReconciler(dursley_registry)
        # "cupboard" is a prefix of "cupboard_under_stairs"
        events = [{"id": "e1", "type": "escape", "agent": "harry_potter", "location": "cupboard"}]
        
        result = reconciler.reconcile(events)
        
        # Should resolve via alias (cupboard is an alias of cupboard_under_stairs)
        assert result.events[0]["location"] == "cupboard_under_stairs"
    
    def test_unknown_location_unchanged(self, dursley_registry):
        """Unknown locations without matches should pass through unchanged."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "harry_potter", "location": "unknown_place"}]
        
        result = reconciler.reconcile(events)
        
        assert result.location_remaps == 0
        assert result.events[0]["location"] == "unknown_place"
    
    def test_null_location_unchanged(self, dursley_registry):
        """Null/missing locations should pass through unchanged."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [
            {"id": "e1", "type": "think", "agent": "harry_potter", "location": None},
            {"id": "e2", "type": "think", "agent": "harry_potter"},
        ]
        
        result = reconciler.reconcile(events)
        
        assert result.reconciled_count == 2
        assert result.events[0].get("location") is None
        assert "location" not in result.events[1] or result.events[1].get("location") is None


class TestContainmentResolution:
    """Tests for containment-based location resolution."""
    
    def test_containment_fallback(self, dursley_registry):
        """Sub-location should map to container via containment."""
        # Add a location with contains field
        dursley_registry.register_locations([
            {"id": "house", "name": "The House", "contains": ["hall", "living_room", "bedroom"]},
        ])
        
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "walk", "agent": "harry_potter", "location": "hall"}]
        
        result = reconciler.reconcile(events)
        
        assert result.location_remaps == 1
        assert result.events[0]["location"] == "house"
        assert result.events[0].get("_reconciliation_type") == "containment_fallback"


class TestCombinedReconciliation:
    """Tests for combined agent and location reconciliation."""
    
    def test_both_agent_and_location_reconciled(self, dursley_registry, dursley_normalizer):
        """Both agent and location should be reconciled in same event."""
        dursley_registry.register_locations([
            {"id": "house", "name": "The House", "contains": ["hall"]},
        ])
        
        reconciler = PostSalvageReconciler(dursley_registry, dursley_normalizer)
        events = [{"id": "e1", "type": "escape", "agent": "dursleys", "location": "hall"}]
        
        result = reconciler.reconcile(events)
        
        # 3 expanded events, each with location remapped
        assert result.reconciled_count == 3
        assert result.expanded_count == 2
        
        for event in result.events:
            assert event["location"] == "house"


class TestReconciliationResult:
    """Tests for ReconciliationResult dataclass."""
    
    def test_empty_events(self, dursley_registry):
        """Empty event list should return empty result."""
        reconciler = PostSalvageReconciler(dursley_registry)
        
        result = reconciler.reconcile([])
        
        assert result.original_count == 0
        assert result.reconciled_count == 0
        assert result.events == []
    
    def test_result_to_dict(self, dursley_registry):
        """Result should be serializable to dict."""
        reconciler = PostSalvageReconciler(dursley_registry)
        events = [{"id": "e1", "type": "talk", "agent": "harry_potter"}]
        
        result = reconciler.reconcile(events)
        result_dict = result.to_dict()
        
        assert "original_count" in result_dict
        assert "reconciled_count" in result_dict
        assert "expanded_count" in result_dict
        assert "agent_remaps" in result_dict
        assert "location_remaps" in result_dict


class TestConvenienceFunction:
    """Tests for reconcile_salvaged_events convenience function."""
    
    def test_convenience_function(self, dursley_registry, dursley_normalizer):
        """reconcile_salvaged_events should work as expected."""
        events = [{"id": "e1", "type": "escape", "agent": "dursleys"}]
        
        reconciled, result = reconcile_salvaged_events(events, dursley_registry, dursley_normalizer)
        
        assert len(reconciled) == 3
        assert result.expanded_count == 2


class TestFamilyGroupBuilding:
    """Tests for automatic family group detection."""
    
    def test_family_from_shared_surname(self):
        """Characters with shared surname should form family group."""
        registry = EntityRegistry()
        registry.register_characters([
            {"id": "james_potter", "name": "James Potter"},
            {"id": "lily_potter", "name": "Lily Potter"},
            {"id": "harry_potter", "name": "Harry Potter"},
            {"id": "sirius_black", "name": "Sirius Black"},
        ])
        
        reconciler = PostSalvageReconciler(registry)
        
        # potters should be detected as a family group
        assert "potters" in reconciler._groups or "the_potters" in reconciler._groups
        
        # Check members
        potter_group = reconciler._groups.get("potters") or reconciler._groups.get("the_potters")
        if potter_group:
            assert "james_potter" in potter_group
            assert "lily_potter" in potter_group
            assert "harry_potter" in potter_group
            assert "sirius_black" not in potter_group
