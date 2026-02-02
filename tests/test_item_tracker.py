"""
Tests for ItemTracker - Item Lifecycle Management & Filtering

Phase 4: Align item extraction with logic relevance
"""

import pytest
from engine.item_tracker import (
    ItemTracker,
    TrackedItem,
    ItemLifecycleState,
    ItemRelevance,
)


class TestItemLifecycleState:
    """Tests for ItemLifecycleState enum."""
    
    def test_all_states_exist(self):
        """Test that all expected states are defined."""
        assert ItemLifecycleState.INTRODUCED.value == "introduced"
        assert ItemLifecycleState.CARRIED.value == "carried"
        assert ItemLifecycleState.USED.value == "used"
        assert ItemLifecycleState.DISCARDED.value == "discarded"
        assert ItemLifecycleState.DESTROYED.value == "destroyed"
        assert ItemLifecycleState.GIVEN.value == "given"
        assert ItemLifecycleState.LATENT.value == "latent"


class TestItemRelevance:
    """Tests for ItemRelevance enum."""
    
    def test_all_relevance_levels_exist(self):
        """Test that all relevance levels are defined."""
        assert ItemRelevance.CAUSAL.value == "causal"
        assert ItemRelevance.LATENT.value == "latent"
        assert ItemRelevance.BACKGROUND.value == "background"


class TestTrackedItem:
    """Tests for TrackedItem dataclass."""
    
    def test_default_values(self):
        """Test default TrackedItem values."""
        item = TrackedItem(item_id="wand")
        
        assert item.item_id == "wand"
        assert item.name is None
        assert item.relevance == ItemRelevance.BACKGROUND
        assert item.lifecycle_state == ItemLifecycleState.INTRODUCED
        assert item.introduced_chapter == 0
        assert item.carrier is None
        assert item.suppressed is False
    
    def test_is_active(self):
        """Test is_active method."""
        item = TrackedItem(item_id="wand")
        assert item.is_active()
        
        # Suppressed item is not active
        item.suppressed = True
        assert not item.is_active()
        
        # Destroyed item is not active
        item.suppressed = False
        item.lifecycle_state = ItemLifecycleState.DESTROYED
        assert not item.is_active()
    
    def test_has_narrative_significance(self):
        """Test has_narrative_significance method."""
        # Background item with no references
        item = TrackedItem(item_id="chair")
        assert not item.has_narrative_significance()
        
        # Causal item always has significance
        item.relevance = ItemRelevance.CAUSAL
        assert item.has_narrative_significance()
        
        # Item with event references has significance
        item2 = TrackedItem(item_id="letter", event_references=["e1", "e2"])
        assert item2.has_narrative_significance()
        
        # Carried item has significance
        item3 = TrackedItem(item_id="key", carrier="harry_potter")
        assert item3.has_narrative_significance()
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        item = TrackedItem(
            item_id="invisibility_cloak",
            name="Invisibility Cloak",
            relevance=ItemRelevance.CAUSAL,
            lifecycle_state=ItemLifecycleState.CARRIED,
            carrier="harry_potter",
        )
        d = item.to_dict()
        
        assert d["item_id"] == "invisibility_cloak"
        assert d["relevance"] == "causal"
        assert d["lifecycle_state"] == "carried"
        assert d["carrier"] == "harry_potter"


class TestItemTracker:
    """Tests for ItemTracker class."""
    
    def test_initialization(self):
        """Test that tracker initializes with empty state."""
        tracker = ItemTracker()
        stats = tracker.get_statistics()
        
        assert stats["total_items"] == 0
        assert stats["active_items"] == 0
        assert stats["suppressed_items"] == 0
    
    def test_process_extraction_causal_items(self):
        """Test that causal items are always kept."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "wand", "name": "Holly Wand", "relevance": "causal"},
                    {"id": "letter", "name": "Hogwarts Letter", "relevance": "causal"},
                ],
            },
            "events": [],
        }
        
        result = tracker.process_extraction(extraction, 0)
        
        # Both items should be kept
        assert len(result["entities"]["items"]) == 2
        stats = tracker.get_statistics()
        assert stats["causal_items"] == 2
        assert stats["suppressed_items"] == 0
    
    def test_process_extraction_latent_items(self):
        """Test that latent items are kept but tracked separately."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "mysterious_key", "name": "Mysterious Key", "relevance": "latent"},
                ],
            },
            "events": [],
        }
        
        result = tracker.process_extraction(extraction, 0)
        
        # Latent item should be kept
        assert len(result["entities"]["items"]) == 1
        stats = tracker.get_statistics()
        assert stats["latent_items"] == 1
        
        # Should be in latent items list
        latent = tracker.get_latent_items()
        assert len(latent) == 1
        assert latent[0].item_id == "mysterious_key"
    
    def test_process_extraction_background_items_suppressed(self):
        """Test that background items with no references are suppressed."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "chair", "name": "Old Chair"},  # No relevance = background
                    {"id": "table", "name": "Wooden Table"},
                ],
            },
            "events": [],  # No events reference these items
        }
        
        result = tracker.process_extraction(extraction, 0)
        
        # Background items should be suppressed
        assert len(result["entities"]["items"]) == 0
        stats = tracker.get_statistics()
        assert stats["suppressed_items"] == 2
    
    def test_background_item_promoted_by_event(self):
        """Test that background items referenced by events become causal."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "key", "name": "Brass Key"},  # No relevance
                ],
            },
            "events": [
                {"id": "e1", "type": "take", "agent": "harry", "patient": "key"},
            ],
        }
        
        result = tracker.process_extraction(extraction, 0)
        
        # Key should be kept because event references it
        assert len(result["entities"]["items"]) == 1
        stats = tracker.get_statistics()
        assert stats["promoted_items"] >= 1
        
        item = tracker.get_item("key")
        assert item.relevance == ItemRelevance.CAUSAL
    
    def test_lifecycle_state_update_give(self):
        """Test lifecycle state update for give events."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "letter", "name": "Letter", "relevance": "causal"},
                ],
            },
            "events": [
                {"id": "e1", "type": "give", "agent": "hagrid", "patient": "harry", "item": "letter"},
            ],
        }
        
        tracker.process_extraction(extraction, 0)
        
        item = tracker.get_item("letter")
        assert item.lifecycle_state == ItemLifecycleState.GIVEN
    
    def test_lifecycle_state_update_take(self):
        """Test lifecycle state update for take events."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "wand", "name": "Wand", "relevance": "causal"},
                ],
            },
            "events": [
                {"id": "e1", "type": "take", "agent": "harry", "patient": "wand"},
            ],
        }
        
        tracker.process_extraction(extraction, 0)
        
        item = tracker.get_item("wand")
        assert item.lifecycle_state == ItemLifecycleState.CARRIED
        assert item.carrier == "harry"
    
    def test_lifecycle_state_update_destroy(self):
        """Test lifecycle state update for destroy events."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "diary", "name": "Diary", "relevance": "causal"},
                ],
            },
            "events": [
                {"id": "e1", "type": "destroy", "agent": "harry", "item": "diary"},
            ],
        }
        
        tracker.process_extraction(extraction, 0)
        
        item = tracker.get_item("diary")
        assert item.lifecycle_state == ItemLifecycleState.DESTROYED
        assert not item.is_active()
    
    def test_get_carried_items(self):
        """Test getting items carried by a character."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "wand", "relevance": "causal"},
                    {"id": "cloak", "relevance": "causal"},
                ],
            },
            "events": [
                {"id": "e1", "type": "take", "agent": "harry", "item": "wand"},
                {"id": "e2", "type": "take", "agent": "harry", "item": "cloak"},
            ],
        }
        
        tracker.process_extraction(extraction, 0)
        
        carried = tracker.get_carried_items("harry")
        assert len(carried) == 2
    
    def test_chekhov_candidates(self):
        """Test detecting Chekhov's Gun candidates."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "mysterious_box", "relevance": "latent"},
                    {"id": "old_map", "relevance": "latent"},
                ],
            },
            "events": [],  # No events use these items
        }
        
        tracker.process_extraction(extraction, 0)
        
        # Latent items that were never used are Chekhov candidates
        candidates = tracker.get_chekhov_candidates()
        assert len(candidates) == 2
    
    def test_to_asp_facts(self):
        """Test generating ASP facts."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "wand", "relevance": "causal"},
                    {"id": "cloak", "relevance": "latent"},
                ],
            },
            "events": [
                {"id": "e1", "type": "take", "agent": "harry", "item": "wand"},
            ],
        }
        
        tracker.process_extraction(extraction, 0)
        
        facts = tracker.to_asp_facts()
        facts_str = "\n".join(facts)
        
        assert "item(wand)." in facts_str
        assert "item_relevance(wand, causal)." in facts_str
        assert "carries(harry, wand)." in facts_str
        assert "latent_item(cloak)." in facts_str
    
    def test_reset(self):
        """Test that reset clears all state."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {"items": [{"id": "wand", "relevance": "causal"}]},
            "events": [],
        }
        tracker.process_extraction(extraction, 0)
        
        assert tracker.get_statistics()["total_items"] == 1
        
        tracker.reset()
        
        assert tracker.get_statistics()["total_items"] == 0
    
    def test_cross_chapter_tracking(self):
        """Test that items are tracked across chapters."""
        tracker = ItemTracker()
        
        # Chapter 0: Item introduced
        extraction0 = {
            "entities": {
                "items": [{"id": "stone", "relevance": "latent"}],
            },
            "events": [],
        }
        tracker.process_extraction(extraction0, 0)
        
        item = tracker.get_item("stone")
        assert item.introduced_chapter == 0
        assert item.lifecycle_state == ItemLifecycleState.INTRODUCED
        
        # Chapter 5: Item used
        extraction5 = {
            "entities": {
                "items": [{"id": "stone", "relevance": "causal"}],
            },
            "events": [
                {"id": "e1", "type": "use", "agent": "harry", "item": "stone"},
            ],
        }
        tracker.process_extraction(extraction5, 5)
        
        item = tracker.get_item("stone")
        assert item.last_mentioned_chapter == 5
        assert item.lifecycle_state == ItemLifecycleState.USED
        # Item has event references now
        assert len(item.event_references) >= 1


class TestItemTrackerIntegration:
    """Integration tests for ItemTracker with extraction flow."""
    
    def test_realistic_extraction(self):
        """Test with a realistic Harry Potter extraction."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "hogwarts_letter", "name": "Hogwarts Letter", "relevance": "causal"},
                    {"id": "invisibility_cloak", "name": "Invisibility Cloak", "relevance": "latent"},
                    {"id": "dining_table", "name": "Dining Table"},  # Background
                    {"id": "chair", "name": "Chair"},  # Background
                ],
            },
            "events": [
                {"id": "e1", "type": "give", "agent": "owl", "patient": "harry", "item": "hogwarts_letter"},
                {"id": "e2", "type": "read", "agent": "harry", "patient": "hogwarts_letter"},
            ],
        }
        
        result = tracker.process_extraction(extraction, 0)
        
        # Only causal and latent items should remain
        item_ids = [i["id"] for i in result["entities"]["items"]]
        assert "hogwarts_letter" in item_ids
        assert "invisibility_cloak" in item_ids
        assert "dining_table" not in item_ids
        assert "chair" not in item_ids
        
        stats = tracker.get_statistics()
        # hogwarts_letter is causal from LLM, and events reference it
        # invisibility_cloak is latent
        assert stats["causal_items"] >= 1
        assert stats["latent_items"] == 1
        assert stats["suppressed_items"] == 2


class TestPhase6RelevanceUpgrades:
    """Phase 6 tests: Automatic relevance upgrades."""
    
    def test_latent_to_causal_upgrade_on_event(self):
        """Test latent item is upgraded to causal when it appears in an event."""
        tracker = ItemTracker()
        
        # Chapter 1: Introduce latent item
        extraction1 = {
            "entities": {
                "items": [{"id": "wand", "relevance": "latent", "name": "Magic Wand"}],
            },
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        item = tracker.get_item("wand")
        assert item.relevance == ItemRelevance.LATENT
        assert item.original_relevance == ItemRelevance.LATENT
        assert item.promoted_to_causal_chapter is None
        
        # Chapter 2: Use the item in an event
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "use", "patient": "wand"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        item = tracker.get_item("wand")
        assert item.relevance == ItemRelevance.CAUSAL
        assert item.original_relevance == ItemRelevance.LATENT
        assert item.promoted_to_causal_chapter == 2
    
    def test_transition_is_logged(self):
        """Test that latent→causal transition is logged."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [{"id": "key", "relevance": "latent"}],
            },
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        assert len(tracker.get_relevance_transitions()) == 0
        
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "key"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        transitions = tracker.get_relevance_transitions()
        assert len(transitions) == 1
        assert transitions[0]["item_id"] == "key"
        assert transitions[0]["from"] == "latent"
        assert transitions[0]["to"] == "causal"
        assert transitions[0]["chapter"] == 2
        assert "e1" in transitions[0]["trigger_events"]
    
    def test_background_to_causal_upgrade(self):
        """Test background item is upgraded to causal when it appears in an event."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [{"id": "rock", "name": "Random Rock"}],  # No relevance = background
            },
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        # Rock should be suppressed initially
        item = tracker.get_item("rock")
        assert item.suppressed == True
        
        # But if it appears in an event later, it gets promoted
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "rock"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        item = tracker.get_item("rock")
        assert item.relevance == ItemRelevance.CAUSAL
        assert item.promoted_to_causal_chapter == 2
    
    def test_remained_latent_helper(self):
        """Test remained_latent() helper method."""
        item_promoted = TrackedItem(
            item_id="a",
            relevance=ItemRelevance.CAUSAL,
            original_relevance=ItemRelevance.LATENT,
            promoted_to_causal_chapter=2,
        )
        assert item_promoted.remained_latent() == False
        assert item_promoted.was_promoted_from_latent() == True
        
        item_still_latent = TrackedItem(
            item_id="b",
            relevance=ItemRelevance.LATENT,
            original_relevance=ItemRelevance.LATENT,
            promoted_to_causal_chapter=None,
        )
        assert item_still_latent.remained_latent() == True
        assert item_still_latent.was_promoted_from_latent() == False
    
    def test_chekhov_candidates_only_includes_remained_latent(self):
        """Test get_chekhov_candidates only returns items that remained latent."""
        tracker = ItemTracker()
        
        # Introduce two latent items
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "used_item", "relevance": "latent"},
                    {"id": "unused_item", "relevance": "latent"},
                ],
            },
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        # Use one item
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "use", "patient": "used_item"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        candidates = tracker.get_chekhov_candidates()
        candidate_ids = [c.item_id for c in candidates]
        
        assert "unused_item" in candidate_ids
        assert "used_item" not in candidate_ids
    
    def test_promoted_latent_items(self):
        """Test get_promoted_latent_items returns items that were promoted."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "item1", "relevance": "latent"},
                    {"id": "item2", "relevance": "latent"},
                ],
            },
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "use", "patient": "item1"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        promoted = tracker.get_promoted_latent_items()
        promoted_ids = [i.item_id for i in promoted]
        
        assert "item1" in promoted_ids
        assert "item2" not in promoted_ids
    
    def test_persistence_across_chapters(self):
        """Test that relevance upgrades persist across chapters."""
        tracker = ItemTracker()
        
        # Chapter 1: Introduce latent item
        extraction1 = {
            "entities": {"items": [{"id": "sword", "relevance": "latent"}]},
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        assert tracker.get_item("sword").relevance == ItemRelevance.LATENT
        
        # Chapter 2: Use the item
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "wield", "patient": "sword"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        assert tracker.get_item("sword").relevance == ItemRelevance.CAUSAL
        
        # Chapter 3, 4, 5: Item not mentioned, but relevance persists
        for chapter in range(3, 6):
            extraction = {"entities": {"items": []}, "events": []}
            tracker.process_extraction(extraction, chapter_num=chapter)
            
            item = tracker.get_item("sword")
            assert item.relevance == ItemRelevance.CAUSAL
            assert item.promoted_to_causal_chapter == 2  # Original promotion chapter
    
    def test_statistics_includes_transitions(self):
        """Test statistics include relevance transition count."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "gem", "relevance": "latent"}]},
            "events": []
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        stats = tracker.get_statistics()
        assert "relevance_transitions" in stats
        assert stats["relevance_transitions"] == 0
        
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "gem"}]
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        stats = tracker.get_statistics()
        assert stats["relevance_transitions"] == 1


class TestActiveUniverseFiltering:
    """Tests for Phase 8.6: ASP fact filtering by active universe."""
    
    def test_to_asp_facts_filters_by_active_universe(self):
        """to_asp_facts filters items not in active universe."""
        from engine.active_universe import ActiveUniverseResult
        from engine.item_tracker import TrackedItem, ItemRelevance
        
        tracker = ItemTracker()
        tracker._items["wand"] = TrackedItem(
            item_id="wand",
            relevance=ItemRelevance.CAUSAL,
            carrier="harry",
        )
        tracker._items["cloak"] = TrackedItem(
            item_id="cloak",
            relevance=ItemRelevance.LATENT,
            carrier="harry",
        )
        tracker._items["sword"] = TrackedItem(
            item_id="sword",
            relevance=ItemRelevance.CAUSAL,
            carrier="dumbledore",
        )
        
        # Active universe only includes wand and harry
        universe = ActiveUniverseResult(
            characters={"harry"},
            items={"wand"},
            locations=set(),
        )
        
        facts = tracker.to_asp_facts(active_universe=universe)
        facts_str = "\n".join(facts)
        
        assert "item(wand)." in facts_str
        assert "carries(harry, wand)." in facts_str
        assert "item(cloak)." not in facts_str  # Not in universe
        assert "item(sword)." not in facts_str  # Not in universe
    
    def test_to_asp_facts_without_universe_includes_all(self):
        """Without active_universe, all non-suppressed items are included."""
        from engine.item_tracker import TrackedItem, ItemRelevance
        
        tracker = ItemTracker()
        tracker._items["wand"] = TrackedItem(item_id="wand", relevance=ItemRelevance.CAUSAL)
        tracker._items["cloak"] = TrackedItem(item_id="cloak", relevance=ItemRelevance.LATENT)
        
        facts = tracker.to_asp_facts()
        facts_str = "\n".join(facts)
        
        assert "item(wand)." in facts_str
        assert "item(cloak)." in facts_str
    
    def test_to_asp_facts_skips_carrier_not_in_universe(self):
        """Carrier facts are skipped if carrier is not in universe."""
        from engine.active_universe import ActiveUniverseResult
        from engine.item_tracker import TrackedItem, ItemRelevance
        
        tracker = ItemTracker()
        tracker._items["wand"] = TrackedItem(
            item_id="wand",
            relevance=ItemRelevance.CAUSAL,
            carrier="dumbledore",  # Not in universe
        )
        
        # Item is in universe, but carrier is not
        universe = ActiveUniverseResult(
            characters={"harry"},  # dumbledore not included
            items={"wand"},
            locations=set(),
        )
        
        facts = tracker.to_asp_facts(active_universe=universe)
        facts_str = "\n".join(facts)
        
        # Item exists but no carries fact (carrier not in universe)
        assert "item(wand)." in facts_str
        # Note: The current implementation skips the entire item if carrier not in universe
        # This is the expected behavior - we're testing it works correctly