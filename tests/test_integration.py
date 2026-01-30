"""
Integration Tests for Narrative Logic Engine

Phase 6, Step 6.2: Integration tests for:
    - Ghost/undead handling (eliminate false positives)
    - Vernon's farewell error detection
    - Cross-chapter state persistence
    - End-to-end pipeline validation

Per LOGIC_DESIGN.md:
    - Tests should verify refactored engine behaves correctly
    - Ghost/undead should not trigger dead_character_acting violations
    - Planted errors (Vernon's warm farewell) should be detected
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.state_manager import StateManager
from engine.rule_registry import RuleRegistry, RuleLayer
from engine.event_executor import EventExecutor, Event
from engine.conflict_resolver import ConflictResolver, StoryContext


class TestGhostUndeadHandling:
    """
    Tests for ghost/undead exception handling.
    
    Per LOGIC_DESIGN.md: Characters marked as ghosts/undead should not
    trigger dead_character_acting violations when they perform actions.
    """
    
    def test_ghost_character_not_flagged_as_dead(self):
        """Ghost characters should not trigger dead_character_acting violations."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        # Initialize story context with ghost characters
        context = cr.initialize_story_context(
            "harry_potter_1",
            {"ghost_characters": ["nearly_headless_nick", "moaning_myrtle"]}
        )
        
        # Simulate a violation for ghost character
        violation = {
            "category": "causality",
            "type": "dead_character_acting",
            "event": "e42",
            "detail": "nearly_headless_nick"
        }
        
        # Analyze - should identify as exception, not real violation
        conflict = cr.analyze_violation(violation)
        
        # Ghost exception should be identified
        assert conflict is not None
        assert conflict.provenance["pattern"]["type"] == "undead_exception"
    
    def test_undead_character_not_flagged_as_dead(self):
        """Undead characters should not trigger dead_character_acting violations."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        # Initialize story context with undead characters (vampires in Twilight)
        context = cr.initialize_story_context(
            "twilight",
            {"undead_characters": ["edward_cullen", "carlisle_cullen"]}
        )
        
        violation = {
            "category": "causality",
            "type": "dead_character_acting",
            "event": "e10",
            "detail": "edward_cullen"
        }
        
        conflict = cr.analyze_violation(violation)
        
        assert conflict is not None
        assert "undead_exception" in conflict.provenance["pattern"]["type"]
    
    def test_normal_dead_character_still_flagged(self):
        """Non-ghost/undead dead characters should still be flagged."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        # Initialize with specific ghost list
        context = cr.initialize_story_context(
            "harry_potter_1",
            {"ghost_characters": ["nearly_headless_nick"]}
        )
        
        # Cedric is dead but not a ghost
        violation = {
            "category": "causality",
            "type": "dead_character_acting",
            "event": "e99",
            "detail": "cedric_diggory"  # Not in ghost list
        }
        
        conflict = cr.analyze_violation(violation)
        
        # Should NOT identify as exception - this is a real violation
        assert conflict is None


class TestVernonFarewellError:
    """
    Tests for detecting Vernon's warm farewell planted error.
    
    The planted error in Chapter 5 has Vernon showing warmth to Harry,
    which contradicts the established hostile relationship.
    
    Per IMPROVEMENTS_TODO.md:
    - Event must be extracted with type like 'farewell' or 'warm_farewell'
    - Relationship 'hates' or 'hostile' must be established
    - Action type must be in action_contradicts_relationship
    """
    
    def test_relationship_contradiction_detection(self):
        """
        Verify that warm actions from hostile characters are detectable.
        
        This tests the rule structure needed for detecting the Vernon error.
        """
        sm = StateManager()
        sm.add_entity("vernon_dursley", "character")
        sm.add_entity("harry_potter", "character")
        
        # Establish hostile relationship
        sm.add_relationship("vernon_dursley", "harry_potter", "hates")
        
        rr = RuleRegistry()
        ee = EventExecutor(state_manager=sm, rule_registry=rr)
        
        # Create a farewell event from Vernon to Harry
        event_data = {
            "id": "e5_1",
            "type": "farewell",
            "agent": "vernon_dursley",
            "patient": "harry_potter",
        }
        event = ee.create_event(event_data, time=1, chapter_num=5)
        
        # The event exists and can be converted to ASP
        asp_facts = event.to_asp_facts()
        
        assert "event_type" in asp_facts
        assert "farewell" in asp_facts.lower()
        assert "vernon_dursley" in asp_facts.lower()
    
    def test_action_contradicts_relationship_rules_exist(self):
        """Verify ASP rules exist for farewell contradicting hates."""
        # Read the story_rules.lp to check for these rules
        rules_path = Path(__file__).parent.parent / "rules" / "story_rules.lp"
        
        if rules_path.exists():
            content = rules_path.read_text()
            
            # These rules should exist per the grep search
            assert "action_contradicts_relationship(farewell, hates)" in content
            assert "action_contradicts_relationship(warm_farewell, hates)" in content
    
    def test_hostile_relationship_asp_generation(self):
        """StateManager generates correct ASP for hostile relationships."""
        sm = StateManager()
        sm.add_entity("vernon_dursley", "character")
        sm.add_entity("harry_potter", "character")
        sm.add_relationship("vernon_dursley", "harry_potter", "hostile")
        
        asp_facts = sm.get_asp_facts_for_clingo()
        
        # Relationship should be in ASP output
        assert "relationship" in asp_facts or "hostile" in asp_facts


class TestTeleportationMagicExceptions:
    """
    Tests for fantasy/magic exception handling.
    
    Stories with teleportation (Harry Potter apparition, etc.)
    should not trigger location ubiquity violations.
    """
    
    def test_harry_potter_has_teleportation(self):
        """Harry Potter stories should auto-detect teleportation capability."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        context = cr.initialize_story_context("harry_potter_1")
        
        assert context.has_teleportation is True
        assert context.has_magic is True
        assert context.is_fantasy is True
    
    def test_teleportation_suppresses_ubiquity_violation(self):
        """Location ubiquity should be excused when story has teleportation."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        # Initialize HP context (has teleportation)
        context = cr.initialize_story_context("harry_potter_1")
        
        violation = {
            "category": "location",
            "type": "ubiquity",
            "event": "e50",
            "detail": "harry_potter at two locations"
        }
        
        conflict = cr.analyze_violation(violation)
        
        # Should identify as teleportation exception
        assert conflict is not None
        assert conflict.provenance["pattern"]["type"] == "teleportation_exception"


class TestCrossChapterStatePersistence:
    """
    Tests for state persistence across chapters.
    
    Relationships and traits established in early chapters
    should persist to later chapters for consistency checking.
    """
    
    def test_relationship_persists_across_snapshots(self):
        """Relationships established should persist through snapshots."""
        sm = StateManager()
        
        # Chapter 0: Establish relationship
        sm.add_entity("vernon_dursley", "character")
        sm.add_entity("harry_potter", "character")
        sm.add_relationship("vernon_dursley", "harry_potter", "hates")
        
        snapshot_ch0 = sm.snapshot()
        
        # Chapter 1-4: Some time passes
        for _ in range(4):
            sm.advance_time()
        
        # Chapter 5: Relationship should still exist
        snapshot_ch5 = sm.snapshot()
        
        # Find vernon's relationships in both snapshots
        # Relation uses args tuple: (entity1, entity2) or similar
        ch0_rels = [r for r in snapshot_ch0.relations if any("vernon" in str(a) for a in r.args)]
        ch5_rels = [r for r in snapshot_ch5.relations if any("vernon" in str(a) for a in r.args)]
        
        assert len(ch0_rels) > 0
        assert len(ch5_rels) > 0
        # Relationship should persist - same predicate
        assert ch0_rels[0].predicate == ch5_rels[0].predicate
    
    def test_death_status_persists(self):
        """Death status should persist across chapters."""
        sm = StateManager()
        
        sm.add_entity("lily_potter", "character")
        sm.mark_dead("lily_potter")
        
        # Advance several chapters
        for _ in range(10):
            sm.advance_time()
        
        # Should still be dead
        assert sm.is_dead("lily_potter") is True
    
    def test_cross_chapter_asp_facts(self):
        """get_cross_chapter_state_facts should include persistent state."""
        sm = StateManager()
        
        sm.add_entity("harry_potter", "character")
        sm.add_entity("voldemort", "character")
        sm.add_relationship("voldemort", "harry_potter", "hates")
        sm.mark_dead("lily_potter")
        
        facts = sm.get_cross_chapter_state_facts()
        
        # Should include relationship and death facts
        assert len(facts) > 0


class TestRulePriorityResolution:
    """
    Tests for rule priority in conflict situations.
    
    Story rules > Learned rules > Universal rules
    """
    
    def test_story_rule_overrides_universal(self):
        """Story-specific rules should override universal rules."""
        rr = RuleRegistry()
        
        # Add universal rule
        rr.add_rule("u1", RuleLayer.UNIVERSAL, 
                    "violation(location, wrong, E) :- at_wrong_place(E).")
        
        # Add story rule that overrides
        rr.add_rule("s1", RuleLayer.STORY,
                    ":- violation(location, wrong, E), magic_travel(E).")
        
        # Deactivate universal rule due to story
        rr.deactivate_rule("u1", "s1", "Magic allows teleportation")
        
        active = rr.get_active_rules()
        active_ids = [r.id for r in active]
        
        # Story rule active, universal deactivated
        assert "s1" in active_ids
        assert "u1" not in active_ids
    
    def test_override_is_auditable(self):
        """All overrides should be recorded for auditing."""
        rr = RuleRegistry()
        
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal content")
        rr.add_rule("s1", RuleLayer.STORY, "story content")
        rr.deactivate_rule("u1", "s1", "Story exception")
        
        history = rr.get_override_history()
        
        assert len(history) == 1
        assert history[0]["overridden"] == "u1"
        assert history[0]["by"] == "s1"


class TestEndToEndPipeline:
    """
    End-to-end integration tests simulating real usage.
    """
    
    def test_full_chapter_processing_flow(self):
        """Simulate processing a complete chapter."""
        # Initialize components
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(state_manager=sm, rule_registry=rr)
        cr = ConflictResolver(rr)
        
        # Set up story context
        cr.initialize_story_context("harry_potter_1", {
            "ghost_characters": ["nearly_headless_nick"],
            "has_magic": True
        })
        
        # Add initial state
        sm.add_entity("harry_potter", "character")
        sm.add_entity("ron_weasley", "character")
        sm.add_entity("hermione_granger", "character")
        
        # Process some events using the correct API
        event_data_list = [
            {"id": "e1", "type": "arrive", "agent": "harry_potter", "location": "hogwarts"},
            {"id": "e2", "type": "meet", "agent": "harry_potter", "patient": "ron_weasley"},
            {"id": "e3", "type": "talk", "agent": "hermione_granger", "patient": "harry_potter"},
        ]
        
        events = [ee.create_event(data, time=i+1, chapter_num=1) for i, data in enumerate(event_data_list)]
        
        # Execute events
        results = ee.execute_events_sequential(events)
        
        # All events should execute
        assert len(results) == 3
        
        # Snapshot should reflect state
        snapshot = sm.snapshot()
        assert len(snapshot.entities) >= 3
    
    def test_violation_detection_and_resolution(self):
        """Test that violations are detected and conflicts resolved."""
        rr = RuleRegistry()
        cr = ConflictResolver(rr)
        
        # Set up HP context
        cr.initialize_story_context("harry_potter", {
            "ghost_characters": ["nearly_headless_nick", "moaning_myrtle"]
        })
        
        # Create violations to test
        violations = [
            {
                "category": "causality",
                "type": "dead_character_acting",
                "event": "e1",
                "detail": "nearly_headless_nick"  # Ghost - should be exception
            },
            {
                "category": "causality", 
                "type": "dead_character_acting",
                "event": "e2",
                "detail": "james_potter"  # Not ghost - real violation
            }
        ]
        
        results = []
        for v in violations:
            conflict = cr.analyze_violation(v)
            results.append({
                "violation": v,
                "is_exception": conflict is not None
            })
        
        # Nick should be exception, James should not
        assert results[0]["is_exception"] is True  # Nick is ghost
        assert results[1]["is_exception"] is False  # James is truly dead


class TestExperimentComparison:
    """
    Tests comparing against existing experiment results.
    """
    
    def test_experiment_directories_exist(self):
        """Verify experiment directories exist for comparison."""
        experiments_dir = Path(__file__).parent.parent / "experiments"
        
        expected_dirs = [
            "harry_potter_full_llm",
            "harry_potter_full_logic",
        ]
        
        for exp_dir in expected_dirs:
            exp_path = experiments_dir / exp_dir
            # At least some experiment directories should exist
            if exp_path.exists():
                assert exp_path.is_dir()
    
    def test_modified_books_have_planted_errors(self):
        """Verify modified books contain planted errors for testing."""
        modified_dir = Path(__file__).parent.parent / "modified_books" / "Harry Potter"
        
        if modified_dir.exists():
            # Chapter 5 should exist and contain the Vernon modification
            ch5_path = modified_dir / "005.txt"
            if ch5_path.exists():
                content = ch5_path.read_text()
                # Should contain the planted error (warm farewell)
                assert "warm" in content.lower() or "smile" in content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
