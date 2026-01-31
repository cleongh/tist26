"""
Tests for Phase 8 - Final Safety Checks

Goal: Make sure nothing violates design principles (LOGIC_DESIGN.md)

Tests:
    1. Alias collision handling
    2. Latent item activation
    3. Background item suppression
    4. Determinism across runs
"""

import pytest
from pathlib import Path

from engine.alias_resolver import AliasResolver, AliasConflict
from engine.item_tracker import ItemTracker, ItemRelevance, ItemLifecycleState
from engine.state_manager import StateManager
from engine.rule_registry import RuleRegistry
from engine.final_analysis import FinalAnalyzer


# =============================================================================
# Alias Collision Tests
# =============================================================================

class TestAliasCollision:
    """Tests for alias collision detection and handling."""
    
    def test_collision_same_alias_different_characters(self):
        """Test that same alias for different characters creates conflict."""
        resolver = AliasResolver()
        
        # First character claims "the_chosen_one"
        conflicts1 = resolver.register_character(
            "harry_potter", ["the_chosen_one"], chapter_num=0
        )
        assert len(conflicts1) == 0
        
        # Second character tries to claim same alias
        conflicts2 = resolver.register_character(
            "neville_longbottom", ["the_chosen_one"], chapter_num=1
        )
        
        assert len(conflicts2) == 1
        conflict = conflicts2[0]
        assert conflict.alias == "the_chosen_one"
        assert "harry_potter" in conflict.canonical_ids
        assert "neville_longbottom" in conflict.canonical_ids
        assert conflict.first_seen_chapter == 0
        assert conflict.conflict_chapter == 1
    
    def test_collision_first_mapping_wins(self):
        """Test that first alias mapping is retained on conflict."""
        resolver = AliasResolver()
        
        resolver.register_character("harry_potter", ["the_boy"], chapter_num=0)
        resolver.register_character("draco_malfoy", ["the_boy"], chapter_num=1)
        
        # First mapping wins
        assert resolver.resolve("the_boy") == "harry_potter"
    
    def test_collision_accumulated_conflicts(self):
        """Test that all conflicts are accumulated."""
        resolver = AliasResolver()
        
        resolver.register_character("harry", ["hero", "protagonist"], chapter_num=0)
        resolver.register_character("frodo", ["hero", "protagonist"], chapter_num=1)
        
        stats = resolver.get_statistics()
        # Should have 2 conflicts (hero + protagonist)
        assert stats["conflicts_detected"] >= 2
    
    def test_collision_to_dict_serialization(self):
        """Test that AliasConflict can be serialized to dict."""
        conflict = AliasConflict(
            alias="the_dark_lord",
            canonical_ids={"voldemort", "sauron"},
            first_seen_chapter=0,
            conflict_chapter=5,
        )
        
        d = conflict.to_dict()
        assert d["alias"] == "the_dark_lord"
        assert set(d["canonical_ids"]) == {"voldemort", "sauron"}
        assert d["first_seen_chapter"] == 0
        assert d["conflict_chapter"] == 5
    
    def test_collision_during_extraction_normalization(self):
        """Test collision detection during normalize_extraction."""
        resolver = AliasResolver()
        
        # Chapter 0: Introduce Harry as "the_seeker"
        extraction0 = {
            "entities": {
                "characters": [
                    {"id": "harry_potter", "aliases": ["the_seeker"]},
                ],
            },
            "events": [],
        }
        resolver.normalize_extraction(extraction0, chapter_num=0)
        
        # Chapter 1: Introduce Draco also as "the_seeker"
        extraction1 = {
            "entities": {
                "characters": [
                    {"id": "draco_malfoy", "aliases": ["the_seeker"]},
                ],
            },
            "events": [{"id": "e1", "agent": "the_seeker", "type": "fly"}],
        }
        normalized, conflicts = resolver.normalize_extraction(extraction1, chapter_num=1)
        
        # Should detect conflict
        assert len(conflicts) >= 1
        assert any(c.alias == "the_seeker" for c in conflicts)
        
        # Event should resolve to first mapping (harry_potter)
        assert normalized["events"][0]["agent"] == "harry_potter"
    
    def test_no_collision_same_character_new_alias(self):
        """Test that adding new alias to same character is not a conflict."""
        resolver = AliasResolver()
        
        conflicts1 = resolver.register_character(
            "vernon_dursley", ["uncle_vernon"], chapter_num=0
        )
        conflicts2 = resolver.register_character(
            "vernon_dursley", ["mr_dursley"], chapter_num=1
        )
        
        assert len(conflicts1) == 0
        assert len(conflicts2) == 0
        
        # Both aliases should resolve to same canonical
        assert resolver.resolve("uncle_vernon") == "vernon_dursley"
        assert resolver.resolve("mr_dursley") == "vernon_dursley"


# =============================================================================
# Latent Item Activation Tests
# =============================================================================

class TestLatentItemActivation:
    """Tests for latent item promotion to causal when used in events."""
    
    def test_latent_item_promoted_on_take_event(self):
        """Test that latent item becomes causal when taken."""
        tracker = ItemTracker()
        
        # Chapter 1: Introduce latent item
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "mysterious_key", "relevance": "latent"},
                ],
            },
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        item = tracker.get_item("mysterious_key")
        assert item.relevance == ItemRelevance.LATENT
        
        # Chapter 3: Item is taken
        extraction3 = {
            "entities": {"items": []},
            "events": [
                {"id": "e1", "type": "take", "agent": "hero", "patient": "mysterious_key"},
            ],
        }
        tracker.process_extraction(extraction3, chapter_num=3)
        
        # Should be promoted to causal
        item = tracker.get_item("mysterious_key")
        assert item.relevance == ItemRelevance.CAUSAL
        assert item.was_promoted_from_latent()
    
    def test_latent_item_promoted_on_give_event(self):
        """Test that latent item becomes causal when given."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "amulet", "relevance": "latent"}]},
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"id": "e1", "type": "give", "agent": "wizard", "patient": "amulet", "recipient": "hero"},
            ],
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        item = tracker.get_item("amulet")
        assert item.relevance == ItemRelevance.CAUSAL
    
    def test_latent_item_promoted_on_use_event(self):
        """Test that latent item becomes causal when used."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "ancient_scroll", "relevance": "latent"}]},
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"id": "e1", "type": "use", "agent": "wizard", "patient": "ancient_scroll"},
            ],
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        item = tracker.get_item("ancient_scroll")
        assert item.relevance == ItemRelevance.CAUSAL
    
    def test_latent_item_tracks_promotion_chapter(self):
        """Test that promotion chapter is tracked."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "gem", "relevance": "latent"}]},
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction5 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "gem"}],
        }
        tracker.process_extraction(extraction5, chapter_num=5)
        
        item = tracker.get_item("gem")
        assert item.original_relevance == ItemRelevance.LATENT
        assert item.promoted_to_causal_chapter == 5
    
    def test_causal_item_not_promoted(self):
        """Test that already causal items are not marked as promoted."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "sword", "relevance": "causal"}]},
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "use", "patient": "sword"}],
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        # Should still be causal, not marked as promoted
        item = tracker.get_item("sword")
        assert item.relevance == ItemRelevance.CAUSAL
        assert not item.was_promoted_from_latent()
    
    def test_latent_items_remaining_for_chekhov(self):
        """Test that only truly unused latent items remain for Chekhov detection."""
        tracker = ItemTracker()
        
        # Introduce 3 latent items
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "item_a", "relevance": "latent"},
                    {"id": "item_b", "relevance": "latent"},
                    {"id": "item_c", "relevance": "latent"},
                ],
            },
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        # Use only item_b
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "item_b"}],
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        # Get candidates for Chekhov (unused latent)
        chekhov_candidates = tracker.get_chekhov_candidates()
        candidate_ids = [c.item_id for c in chekhov_candidates]
        
        assert "item_a" in candidate_ids
        assert "item_c" in candidate_ids
        assert "item_b" not in candidate_ids  # Was promoted


# =============================================================================
# Background Item Suppression Tests
# =============================================================================

class TestBackgroundItemSuppression:
    """Tests for background items not triggering Chekhov violations."""
    
    def test_background_item_no_chekhov_violation(self):
        """Test that background items don't trigger Chekhov violations."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "table", "relevance": "background"},
                    {"id": "chair", "relevance": "background"},
                    {"id": "mysterious_letter", "relevance": "latent"},
                ],
            },
            "events": [],
        }
        tracker.process_extraction(extraction, chapter_num=1)
        
        # Only latent items should be Chekhov candidates
        chekhov_candidates = tracker.get_chekhov_candidates()
        candidate_ids = [c.item_id for c in chekhov_candidates]
        
        assert "table" not in candidate_ids
        assert "chair" not in candidate_ids
        assert "mysterious_letter" in candidate_ids
    
    def test_background_item_not_in_loose_ends(self):
        """Test that background items don't appear in final loose ends."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        tracker = ItemTracker()
        
        # Introduce background and latent items
        extraction = {
            "entities": {
                "items": [
                    {"id": "curtain", "relevance": "background"},
                    {"id": "secret_map", "relevance": "latent"},
                ],
            },
            "events": [],
        }
        tracker.process_extraction(extraction, chapter_num=1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, tracker)
        result = analyzer.analyze(
            story_id="test_story",
            total_chapters=5
        )
        
        # Only latent item should be in loose ends
        loose_end_entities = [le.entity_id for le in result.loose_ends]
        
        assert "curtain" not in loose_end_entities
        assert "secret_map" in loose_end_entities
    
    def test_background_item_excluded_from_diagnostics(self):
        """Test that background items are excluded from item diagnostics."""
        tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "window", "relevance": "background"},
                ],
            },
            "events": [],
        }
        tracker.process_extraction(extraction, chapter_num=1)
        
        stats = tracker.get_statistics()
        # Background items should be tracked but not counted as narrative items
        assert stats["background_items"] >= 1 or "window" not in [
            c.item_id for c in tracker.get_chekhov_candidates()
        ]
    
    def test_background_to_causal_upgrade(self):
        """Test that background items CAN be promoted if they become plot-relevant."""
        tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [{"id": "ordinary_ring", "relevance": "background"}],
            },
            "events": [],
        }
        tracker.process_extraction(extraction1, chapter_num=1)
        
        item = tracker.get_item("ordinary_ring")
        assert item.relevance == ItemRelevance.BACKGROUND
        
        # Ring becomes plot-critical
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"id": "e1", "type": "take", "agent": "frodo", "patient": "ordinary_ring"},
            ],
        }
        tracker.process_extraction(extraction2, chapter_num=2)
        
        # Should be promoted to causal
        item = tracker.get_item("ordinary_ring")
        assert item.relevance == ItemRelevance.CAUSAL
        # Background items start with original_relevance=BACKGROUND, not LATENT
        assert item.original_relevance == ItemRelevance.BACKGROUND


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Tests that ensure deterministic behavior across runs."""
    
    def test_alias_resolution_deterministic(self):
        """Test that alias resolution produces identical results."""
        results = []
        
        for _ in range(5):
            resolver = AliasResolver()
            resolver.register_character("harry", ["potter", "the_boy"], 0)
            resolver.register_character("ron", ["weasley", "ginger"], 0)
            resolver.register_character("hermione", ["granger", "bookworm"], 0)
            
            result = {
                "potter": resolver.resolve("potter"),
                "weasley": resolver.resolve("weasley"),
                "granger": resolver.resolve("granger"),
                "the_boy": resolver.resolve("the_boy"),
            }
            results.append(result)
        
        # All runs should produce identical results
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Run {i} differs from run 0"
    
    def test_item_tracking_deterministic(self):
        """Test that item tracking produces identical results."""
        results = []
        
        for _ in range(5):
            tracker = ItemTracker()
            
            extraction1 = {
                "entities": {
                    "items": [
                        {"id": "sword", "relevance": "causal"},
                        {"id": "ring", "relevance": "latent"},
                        {"id": "table", "relevance": "background"},
                    ],
                },
                "events": [],
            }
            tracker.process_extraction(extraction1, chapter_num=1)
            
            extraction2 = {
                "entities": {"items": []},
                "events": [{"id": "e1", "type": "take", "patient": "ring"}],
            }
            tracker.process_extraction(extraction2, chapter_num=2)
            
            result = {
                "sword_relevance": tracker.get_item("sword").relevance.value,
                "ring_relevance": tracker.get_item("ring").relevance.value,
                "table_relevance": tracker.get_item("table").relevance.value,
                "ring_promoted": tracker.get_item("ring").was_promoted_from_latent(),
                "chekhov_count": len(tracker.get_chekhov_candidates()),
            }
            results.append(result)
        
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Run {i} differs from run 0"
    
    def test_final_analysis_deterministic(self):
        """Test that final analysis produces identical results."""
        results = []
        
        for _ in range(5):
            state_manager = StateManager()
            rule_registry = RuleRegistry(Path("rules"))
            tracker = ItemTracker()
            
            extraction = {
                "entities": {
                    "items": [
                        {"id": "chekhov_gun", "relevance": "latent"},
                        {"id": "used_item", "relevance": "latent"},
                    ],
                },
                "events": [],
            }
            tracker.process_extraction(extraction, chapter_num=1)
            
            extraction2 = {
                "entities": {"items": []},
                "events": [{"id": "e1", "type": "use", "patient": "used_item"}],
            }
            tracker.process_extraction(extraction2, chapter_num=2)
            
            analyzer = FinalAnalyzer(state_manager, rule_registry, tracker)
            result = analyzer.analyze(
                story_id="test_story",
                total_chapters=3
            )
            
            serialized = {
                "loose_end_count": len(result.loose_ends),
                "loose_end_entities": sorted([le.entity_id for le in result.loose_ends]),
                "total_violations": result.total_violations,
            }
            results.append(serialized)
        
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Run {i} differs from run 0"
    
    def test_extraction_normalization_deterministic(self):
        """Test that extraction normalization is deterministic."""
        results = []
        
        for _ in range(5):
            resolver = AliasResolver()
            resolver.register_character("harry_potter", ["the_boy_who_lived"], 0)
            
            extraction = {
                "entities": {
                    "characters": [
                        {"id": "ron_weasley", "aliases": ["ron", "weasley"]},
                    ],
                },
                "events": [
                    {"id": "e1", "agent": "the_boy_who_lived", "patient": "ron", "type": "talk"},
                    {"id": "e2", "agent": "weasley", "type": "leave"},
                ],
            }
            
            normalized, conflicts = resolver.normalize_extraction(extraction, chapter_num=1)
            
            result = {
                "e1_agent": normalized["events"][0]["agent"],
                "e1_patient": normalized["events"][0]["patient"],
                "e2_agent": normalized["events"][1]["agent"],
                "conflicts": len(conflicts),
            }
            results.append(result)
        
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Run {i} differs from run 0"
    
    def test_chekhov_candidates_order_deterministic(self):
        """Test that Chekhov candidate list order is deterministic."""
        results = []
        
        for _ in range(5):
            tracker = ItemTracker()
            
            extraction = {
                "entities": {
                    "items": [
                        {"id": "item_z", "relevance": "latent"},
                        {"id": "item_a", "relevance": "latent"},
                        {"id": "item_m", "relevance": "latent"},
                    ],
                },
                "events": [],
            }
            tracker.process_extraction(extraction, chapter_num=1)
            
            candidates = tracker.get_chekhov_candidates()
            candidate_ids = [c.item_id for c in candidates]
            results.append(candidate_ids)
        
        for i in range(1, len(results)):
            assert results[i] == results[0], f"Run {i} differs from run 0"
