"""
Tests for FinalAnalyzer - Final Story Analysis & Chekhov Detection

Phase 5: Make logic reason about items correctly
Phase 7: Diagnostics & JSON Output
"""

import pytest
from engine.final_analysis import (
    FinalAnalyzer,
    FinalAnalysisResult,
    LooseEnd,
    LongRangeInconsistency,
)
from engine.event_executor import EntityDiagnosticInfo
from engine.state_manager import StateManager
from engine.rule_registry import RuleRegistry
from engine.item_tracker import ItemTracker, ItemRelevance, ItemLifecycleState
from pathlib import Path


class TestFinalAnalyzerBasics:
    """Tests for basic FinalAnalyzer functionality."""
    
    def test_initialization_without_item_tracker(self):
        """Test FinalAnalyzer initializes without ItemTracker."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        
        analyzer = FinalAnalyzer(state_manager, rule_registry)
        
        assert analyzer.state_manager is state_manager
        assert analyzer.rule_registry is rule_registry
        assert analyzer.item_tracker is None
    
    def test_initialization_with_item_tracker(self):
        """Test FinalAnalyzer initializes with ItemTracker."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        
        assert analyzer.item_tracker is item_tracker
    
    def test_set_item_tracker(self):
        """Test setting ItemTracker after initialization."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        
        analyzer = FinalAnalyzer(state_manager, rule_registry)
        assert analyzer.item_tracker is None
        
        item_tracker = ItemTracker()
        analyzer.set_item_tracker(item_tracker)
        
        assert analyzer.item_tracker is item_tracker


class TestChekhovDetectionFromItemTracker:
    """Tests for Chekhov's Gun detection from ItemTracker."""
    
    def test_no_chekhov_violations_without_item_tracker(self):
        """Test that no Chekhov violations are added without ItemTracker."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        
        analyzer = FinalAnalyzer(state_manager, rule_registry)
        result = analyzer.analyze("test_story", total_chapters=3)
        
        # Should have no chekhov_latent loose ends
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 0
    
    def test_chekhov_violations_for_unused_latent_items(self):
        """Test that unused latent items are detected as Chekhov violations."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        # Simulate processing extractions with latent items
        extraction = {
            "entities": {
                "items": [
                    {"id": "mysterious_key", "relevance": "latent", "name": "Mysterious Key"},
                    {"id": "letter", "relevance": "latent", "name": "Old Letter"},
                ],
            },
            "events": []  # No events that use the items
        }
        item_tracker.process_extraction(extraction, chapter_num=1)
        
        # Process another chapter where items are still not used
        extraction2 = {
            "entities": {"items": []},
            "events": []
        }
        item_tracker.process_extraction(extraction2, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=2)
        
        # Should detect both latent items as Chekhov violations
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 2
        
        chekhov_item_ids = {e.entity_id for e in chekhov_ends}
        assert "mysterious_key" in chekhov_item_ids
        assert "letter" in chekhov_item_ids
    
    def test_no_chekhov_violation_for_used_latent_items(self):
        """Test that latent items that are activated don't trigger Chekhov violation."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        # Introduce latent item
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "wand", "relevance": "latent", "name": "Magic Wand"},
                ],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction1, chapter_num=1)
        
        # Use the item in a later chapter
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"event_id": "e1", "type": "use", "patient": "wand"}
            ]
        }
        item_tracker.process_extraction(extraction2, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=2)
        
        # Wand should NOT appear as a Chekhov violation
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 0
    
    def test_chekhov_violation_attributed_to_introduction_chapter(self):
        """Test that Chekhov violations are attributed to the correct chapter."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        # Introduce item in chapter 3
        for chapter in range(1, 6):
            if chapter == 3:
                extraction = {
                    "entities": {
                        "items": [
                            {"id": "ring", "relevance": "latent", "name": "Golden Ring"},
                        ],
                    },
                    "events": []
                }
            else:
                extraction = {
                    "entities": {"items": []},
                    "events": []
                }
            item_tracker.process_extraction(extraction, chapter_num=chapter)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=5)
        
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 1
        assert chekhov_ends[0].entity_id == "ring"
        assert chekhov_ends[0].introduced_chapter == 3
    
    def test_chekhov_violation_added_to_chapter_violations(self):
        """Test that Chekhov violations are added to chapter_violations dict."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "dagger", "relevance": "latent", "name": "Hidden Dagger"},
                ],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=3)
        
        # Check chapter_violations has the Chekhov error
        assert 2 in analyzer.chapter_violations
        violations = analyzer.chapter_violations[2]
        
        chekhov_violations = [v for v in violations if v.get("type") == "chekhov_gun"]
        assert len(chekhov_violations) == 1
        assert chekhov_violations[0]["entity"] == "dagger"
        assert chekhov_violations[0]["category"] == "causality"
        assert chekhov_violations[0]["severity"] == "soft"


class TestChekhovWithMixedItems:
    """Tests for Chekhov detection with mixed causal/latent/background items."""
    
    def test_only_latent_items_trigger_chekhov(self):
        """Test that only latent items trigger Chekhov violations."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [
                    {"id": "sword", "relevance": "causal", "name": "Magic Sword"},
                    {"id": "map", "relevance": "latent", "name": "Treasure Map"},
                    {"id": "rock", "relevance": "background", "name": "Random Rock"},
                ],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction, chapter_num=1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=3)
        
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        
        # Only the latent item (map) should trigger Chekhov violation
        assert len(chekhov_ends) == 1
        assert chekhov_ends[0].entity_id == "map"
    
    def test_latent_item_activated_by_give_event(self):
        """Test that latent items activated by give events don't trigger Chekhov."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "gem", "relevance": "latent", "name": "Enchanted Gem"},
                ],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction1, chapter_num=1)
        
        # Use "item" field for give event (as expected by ItemTracker)
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"event_id": "e1", "type": "give", "agent": "wizard", "item": "gem", "recipient": "hero"}
            ]
        }
        item_tracker.process_extraction(extraction2, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=2)
        
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 0
    
    def test_latent_item_activated_by_take_event(self):
        """Test that latent items activated by take events don't trigger Chekhov."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction1 = {
            "entities": {
                "items": [
                    {"id": "book", "relevance": "latent", "name": "Ancient Book"},
                ],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [
                {"event_id": "e1", "type": "take", "agent": "hero", "patient": "book"}
            ]
        }
        item_tracker.process_extraction(extraction2, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=2)
        
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 0


class TestLooseEndDataclass:
    """Tests for LooseEnd dataclass."""
    
    def test_loose_end_creation(self):
        """Test creating a LooseEnd instance."""
        end = LooseEnd(
            loose_end_type="chekhov_latent",
            entity_id="sword",
            entity_type="item",
            introduced_chapter=1,
            introduced_event=None,
            last_referenced_chapter=3,
            expected_resolution="Latent item 'sword' was introduced but never used",
        )
        
        assert end.loose_end_type == "chekhov_latent"
        assert end.entity_id == "sword"
        assert end.entity_type == "item"
        assert end.introduced_chapter == 1
        assert end.last_referenced_chapter == 3
    
    def test_loose_end_with_phase7_fields(self):
        """Phase 7: Test LooseEnd with enhanced diagnostics."""
        end = LooseEnd(
            loose_end_type="chekhov_latent",
            entity_id="magic_wand",
            entity_type="item",
            introduced_chapter=1,
            aliases=["the_wand", "harrys_wand"],
            item_relevance="latent",
            item_lifecycle="introduced",
            item_original_relevance="latent",
        )
        
        assert end.aliases == ["the_wand", "harrys_wand"]
        assert end.item_relevance == "latent"
        assert end.item_lifecycle == "introduced"
        assert end.item_original_relevance == "latent"
    
    def test_loose_end_to_dict_includes_phase7_fields(self):
        """Phase 7: Test to_dict includes enhanced diagnostics."""
        end = LooseEnd(
            loose_end_type="chekhov_latent",
            entity_id="ring",
            entity_type="item",
            introduced_chapter=2,
            aliases=["the_ring", "one_ring"],
            item_relevance="latent",
            item_lifecycle="introduced",
        )
        
        d = end.to_dict()
        assert d["entity_id"] == "ring"
        assert d["aliases"] == ["the_ring", "one_ring"]
        assert d["item_relevance"] == "latent"
        assert d["item_lifecycle"] == "introduced"


class TestFinalAnalysisResultDataclass:
    """Tests for FinalAnalysisResult dataclass."""
    
    def test_result_creation(self):
        """Test creating FinalAnalysisResult with loose ends."""
        loose_end = LooseEnd(
            loose_end_type="chekhov_latent",
            entity_id="ring",
            entity_type="item",
            introduced_chapter=2,
            introduced_event=None,
            last_referenced_chapter=2,
            expected_resolution="Test",
        )
        
        result = FinalAnalysisResult(
            story_id="test",
            total_chapters=3,
            total_events=10,
            total_violations=0,
            loose_ends=[loose_end],
        )
        
        assert len(result.loose_ends) == 1
        assert result.loose_ends[0].entity_id == "ring"


class TestPhase7DiagnosticEnhancements:
    """Phase 7: Tests for enhanced diagnostic output."""
    
    def test_chekhov_violation_includes_item_diagnostics(self):
        """Phase 7: Test that Chekhov violations include item lifecycle info."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [{"id": "dagger", "relevance": "latent", "name": "Hidden Dagger"}],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction, chapter_num=1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        result = analyzer.analyze("test_story", total_chapters=2)
        
        chekhov_ends = [e for e in result.loose_ends if e.loose_end_type == "chekhov_latent"]
        assert len(chekhov_ends) == 1
        
        end = chekhov_ends[0]
        assert end.entity_id == "dagger"
        assert end.item_relevance == "latent"
        assert end.item_lifecycle == "introduced"
        assert end.item_original_relevance == "latent"
    
    def test_chapter_violation_includes_item_diagnostics(self):
        """Phase 7: Test that chapter violations include item info."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [{"id": "key", "relevance": "latent"}],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction, chapter_num=1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        analyzer.analyze("test_story", total_chapters=2)
        
        # Check chapter_violations has item diagnostics
        assert 1 in analyzer.chapter_violations
        violations = analyzer.chapter_violations[1]
        chekhov_v = [v for v in violations if v.get("type") == "chekhov_gun"]
        assert len(chekhov_v) == 1
        
        v = chekhov_v[0]
        assert v["entity"] == "key"
        assert v["item_relevance"] == "latent"
        assert v["item_lifecycle"] == "introduced"
    
    def test_finalanalyzer_with_alias_resolver(self):
        """Phase 7: Test FinalAnalyzer with AliasResolver."""
        from engine.alias_resolver import AliasResolver
        
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        alias_resolver = AliasResolver()
        
        # Register some character aliases
        alias_resolver.register_character("harry_potter", ["harry", "the_boy_who_lived"], 1)
        alias_resolver.register_character("voldemort", ["he_who_must_not_be_named", "tom_riddle"], 1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)
        
        # Test get_entity_aliases
        harry_aliases = analyzer.get_entity_aliases("harry_potter")
        assert "harry" in harry_aliases
        assert "the_boy_who_lived" in harry_aliases
        assert "harry_potter" not in harry_aliases  # Canonical ID excluded
        
        voldemort_aliases = analyzer.get_entity_aliases("voldemort")
        assert "he_who_must_not_be_named" in voldemort_aliases
        assert "tom_riddle" in voldemort_aliases
    
    def test_get_item_diagnostics(self):
        """Phase 7: Test get_item_diagnostics helper."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction = {
            "entities": {
                "items": [{"id": "wand", "relevance": "latent", "name": "Magic Wand"}],
            },
            "events": []
        }
        item_tracker.process_extraction(extraction, chapter_num=1)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        
        diagnostics = analyzer.get_item_diagnostics("wand")
        assert diagnostics["relevance"] == "latent"
        assert diagnostics["lifecycle"] == "introduced"
        assert diagnostics["original_relevance"] == "latent"
        assert diagnostics["carrier"] is None
    
    def test_get_item_diagnostics_after_promotion(self):
        """Phase 7: Test get_item_diagnostics shows promoted relevance."""
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        item_tracker = ItemTracker()
        
        extraction1 = {
            "entities": {"items": [{"id": "gem", "relevance": "latent"}]},
            "events": []
        }
        item_tracker.process_extraction(extraction1, chapter_num=1)
        
        extraction2 = {
            "entities": {"items": []},
            "events": [{"id": "e1", "type": "take", "patient": "gem"}]
        }
        item_tracker.process_extraction(extraction2, chapter_num=2)
        
        analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker)
        
        diagnostics = analyzer.get_item_diagnostics("gem")
        assert diagnostics["relevance"] == "causal"  # Promoted
        assert diagnostics["original_relevance"] == "latent"
        assert diagnostics["promoted_chapter"] == 2
    
    def test_set_alias_resolver(self):
        """Phase 7: Test set_alias_resolver method."""
        from engine.alias_resolver import AliasResolver
        
        state_manager = StateManager()
        rule_registry = RuleRegistry(Path("rules"))
        
        analyzer = FinalAnalyzer(state_manager, rule_registry)
        assert analyzer.alias_resolver is None
        
        alias_resolver = AliasResolver()
        alias_resolver.register_character("hermione", ["granger"], 1)
        
        analyzer.set_alias_resolver(alias_resolver)
        assert analyzer.alias_resolver is alias_resolver
        
        aliases = analyzer.get_entity_aliases("hermione")
        assert "granger" in aliases


class TestEntityDiagnosticInfo:
    """Tests for EntityDiagnosticInfo dataclass."""
    
    def test_entity_diagnostic_info_creation(self):
        """Test basic EntityDiagnosticInfo creation."""
        info = EntityDiagnosticInfo(
            canonical_id="wand",
            entity_type="item"
        )
        assert info.canonical_id == "wand"
        assert info.entity_type == "item"
        assert info.aliases == []  # Default
        assert info.item_relevance is None
        assert info.item_lifecycle is None
        assert info.item_carrier is None
    
    def test_entity_diagnostic_info_with_all_fields(self):
        """Test EntityDiagnosticInfo with all optional fields."""
        info = EntityDiagnosticInfo(
            canonical_id="sword",
            entity_type="item",
            aliases=["blade", "weapon"],
            item_relevance="causal",
            item_lifecycle="active",
            item_carrier="hero"
        )
        assert info.canonical_id == "sword"
        assert info.entity_type == "item"
        assert info.aliases == ["blade", "weapon"]
        assert info.item_relevance == "causal"
        assert info.item_lifecycle == "active"
        assert info.item_carrier == "hero"
    
    def test_entity_diagnostic_info_to_dict(self):
        """Test EntityDiagnosticInfo to_dict method."""
        info = EntityDiagnosticInfo(
            canonical_id="ring",
            entity_type="item",
            aliases=["precious"],
            item_relevance="plot-critical",
            item_lifecycle="introduced",
            item_carrier="frodo"
        )
        d = info.to_dict()
        
        assert d["canonical_id"] == "ring"
        assert d["entity_type"] == "item"
        assert d["aliases"] == ["precious"]
        # Note: to_dict uses shortened key names
        assert d["relevance"] == "plot-critical"
        assert d["lifecycle"] == "introduced"
        assert d["carrier"] == "frodo"
    
    def test_entity_diagnostic_info_character(self):
        """Test EntityDiagnosticInfo for character entities."""
        info = EntityDiagnosticInfo(
            canonical_id="harry",
            entity_type="character",
            aliases=["potter", "the_boy_who_lived"]
        )
        d = info.to_dict()
        
        assert d["canonical_id"] == "harry"
        assert d["entity_type"] == "character"
        assert d["aliases"] == ["potter", "the_boy_who_lived"]
        # Item fields are omitted (not None) when not set for characters
        assert "relevance" not in d
        assert "lifecycle" not in d
        assert "carrier" not in d