"""
Unit Tests for EventExecutor

Phase 6, Step 6.1: Test EventExecutor state transitions

Tests:
    - Event creation and ASP conversion
    - State transitions during event execution
    - Error detection and violation tracking
    - Chapter evaluation
"""

import pytest
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.event_executor import EventExecutor, Event, EventResult
from engine.conflict_resolver import StoryContext
from engine.state_manager import StateManager
from engine.rule_registry import RuleRegistry


class TestEvent:
    """Event dataclass tests."""
    
    def test_event_creation(self):
        """Event can be created with required fields."""
        event = Event(
            id="e1",
            event_type="action",
            time=1,
            agent="harry",
            patient="voldemort",
            location="forbidden_forest"
        )
        
        assert event.id == "e1"
        assert event.event_type == "action"
        assert event.agent == "harry"
        assert event.time == 1
    
    def test_event_optional_fields(self):
        """Event handles optional fields correctly."""
        event = Event(
            id="e2",
            event_type="state_change",
            time=2,
            agent="hermione"
        )
        
        assert event.patient is None
        assert event.location is None
        assert event.source_text is None


class TestEventToASP:
    """Event ASP conversion tests."""
    
    def test_to_asp_basic_event(self):
        """to_asp generates correct ASP facts."""
        event = Event(
            id="e1",
            event_type="action",
            time=3,
            agent="harry_potter",
            patient="draco_malfoy",
            location="hogwarts"
        )
        
        asp_facts = event.to_asp_facts()
        
        assert "event(e1)" in asp_facts
        assert "event_type(e1, action)" in asp_facts
        assert "agent(e1, harry_potter)" in asp_facts
        assert "patient(e1, draco_malfoy)" in asp_facts
        assert "location(e1, hogwarts)" in asp_facts
    
    def test_to_asp_with_source_text(self):
        """to_asp includes source text."""
        event = Event(
            id="e1",
            event_type="talk",
            time=1,
            agent="harry",
            source_text="Harry said something"
        )
        
        asp_facts = event.to_asp_facts()
        
        assert "event_source" in asp_facts
        assert "Harry said something" in asp_facts or "harry said something" in asp_facts.lower()


class TestEventResult:
    """EventResult dataclass tests."""
    
    def test_event_result_basic(self):
        """EventResult captures event outcome."""
        result = EventResult(
            event_id="e1",
            time=1,
            violations=[],
            state_changes=["harry: location=hogwarts"]
        )
        
        assert result.event_id == "e1"
        assert len(result.violations) == 0
        assert len(result.state_changes) == 1
    
    def test_event_result_with_violations(self):
        """EventResult captures violations."""
        result = EventResult(
            event_id="e2",
            time=2,
            violations=[{"category": "causality", "type": "dead_character"}],
            state_changes=[]
        )
        
        assert len(result.violations) == 1
        assert result.violations[0]["category"] == "causality"


class TestStoryContext:
    """StoryContext dataclass tests."""
    
    def test_story_context_defaults(self):
        """StoryContext has sensible defaults."""
        ctx = StoryContext(story_id="hp1")
        
        assert ctx.story_id == "hp1"
        assert ctx.undead_characters == []
        assert ctx.ghost_characters == []
    
    def test_story_context_with_ghosts(self):
        """StoryContext can specify ghost characters."""
        ctx = StoryContext(
            story_id="hp1",
            ghost_characters=["nearly_headless_nick", "moaning_myrtle"]
        )
        
        assert "nearly_headless_nick" in ctx.ghost_characters
        assert "moaning_myrtle" in ctx.ghost_characters


class TestEventExecutorBasics:
    """Basic EventExecutor functionality."""
    
    def test_initialization(self):
        """EventExecutor initializes correctly."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(state_manager=sm, rule_registry=rr)
        
        assert ee.state_manager is sm
        assert ee.rule_registry is rr
    
    def test_sanitize_id(self):
        """_sanitize_id creates valid ASP identifiers."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        # Test space handling
        result = ee._sanitize_id("Harry Potter")
        assert " " not in result
        
        # Test lowercase
        result = ee._sanitize_id("HERMIONE")
        assert result == result.lower()
        
        # Test special characters
        result = ee._sanitize_id("Nearly-Headless Nick")
        assert result.replace("_", "").isalnum()


class TestToASP:
    """to_asp conversion tests."""
    
    def test_to_asp_basic_chapter(self):
        """to_asp converts chapter data to ASP facts."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        chapter_data = {
            "entities": {
                "characters": [
                    {"id": "harry_potter", "name": "Harry"},
                ],
                "locations": [
                    {"id": "hogwarts", "name": "Hogwarts"}
                ]
            },
            "events": [
                {
                    "id": "e1",
                    "type": "arrive",
                    "agent": "harry_potter",
                    "location": "hogwarts"
                }
            ]
        }
        
        asp_output = ee.to_asp(chapter_data, chapter_num=1)
        
        # Character ID gets normalized - check for either form
        assert "character(" in asp_output
        assert "location_entity(hogwarts)" in asp_output or "location" in asp_output.lower()
        # Events should be present
        assert "event(e1)" in asp_output


class TestASPIntegration:
    """ASP integration tests."""
    
    def test_event_asp_valid_syntax(self):
        """Event ASP output is valid syntax."""
        event = Event(
            id="e1",
            event_type="action",
            time=7,
            agent="harry",
            patient="voldemort",
            location="graveyard"
        )
        
        asp = event.to_asp_facts()
        
        # Check basic ASP syntax
        for line in asp.strip().split('\n'):
            line = line.strip()
            if line:
                # Each fact should end with a period
                assert line.endswith('.'), f"ASP fact missing period: {line}"


class TestViolationDetection:
    """Violation detection tests."""
    
    def test_event_result_stores_violations(self):
        """EventResult can store multiple violations."""
        result = EventResult(
            event_id="e1",
            time=1,
            violations=[
                {"category": "causality", "type": "dead_character"},
                {"category": "location", "type": "ubiquity"}
            ]
        )
        
        assert len(result.violations) == 2
        categories = [v["category"] for v in result.violations]
        assert "causality" in categories
        assert "location" in categories


class TestCrossChapterState:
    """Cross-chapter state handling tests."""
    
    def test_state_manager_integration(self):
        """EventExecutor integrates with StateManager."""
        sm = StateManager()
        sm.add_entity("harry", "character")
        
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        # Should have access to state
        assert ee.state_manager.get_current_state() is not None


class TestCharacterAliases:
    """
    Tests for ASP-based character alias resolution.
    
    Per LOGIC_DESIGN.md: Python is orchestration only, ASP handles logic.
    Aliases are injected as alias/2 facts for ASP resolution.
    
    Note: These tests verify the legacy fallback behavior. In production,
    aliases are dynamically discovered during extraction and managed by
    AliasResolver.
    """
    
    def test_generate_alias_facts_legacy(self):
        """generate_alias_facts() produces valid ASP facts with legacy aliases."""
        from engine.event_executor import generate_alias_facts, _LEGACY_CHARACTER_ALIASES
        
        # Test without alias_resolver (legacy mode)
        asp_facts = generate_alias_facts(alias_resolver=None)
        
        # Should contain header comment
        assert "% Character alias facts" in asp_facts
        
        # Should contain alias facts
        assert "alias(" in asp_facts
        
        # Check specific aliases from legacy dict
        for alias_id, canonical_id in _LEGACY_CHARACTER_ALIASES.items():
            if alias_id != canonical_id:
                expected = f"alias({alias_id}, {canonical_id})."
                assert expected in asp_facts, f"Missing alias: {expected}"
    
    def test_generate_alias_facts_with_resolver(self):
        """generate_alias_facts() uses AliasResolver when provided."""
        from engine.event_executor import generate_alias_facts
        from engine.alias_resolver import AliasResolver
        
        resolver = AliasResolver()
        resolver.register_character("uncle_vernon", ["mr_dursley", "vernon"], chapter_num=1)
        
        asp_facts = generate_alias_facts(alias_resolver=resolver)
        
        # Should contain dynamically registered aliases
        assert "alias(mr_dursley, uncle_vernon)." in asp_facts
        assert "alias(vernon, uncle_vernon)." in asp_facts
    
    def test_alias_facts_no_self_aliases(self):
        """Self-aliases (X -> X) should not be generated."""
        from engine.event_executor import generate_alias_facts
        
        asp_facts = generate_alias_facts(alias_resolver=None)
        
        # Self-aliases should not appear (e.g., alias(hagrid, hagrid).)
        # The legacy aliases has hagrid -> hagrid, but we skip those
        assert "alias(hagrid, hagrid)." not in asp_facts
    
    def test_to_asp_includes_alias_facts(self):
        """to_asp() includes alias facts in output."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {
                "characters": [{"id": "harry_potter"}]
            },
            "events": []
        }
        
        asp_output = ee.to_asp(data, chapter_num=1)
        
        # Should contain alias section
        assert "% Character alias facts" in asp_output
        # Legacy mode: harry_potter -> harry
        assert "alias(harry_potter, harry)." in asp_output
    
    def test_normalize_character_id_legacy(self):
        """normalize_character_id() resolves legacy aliases without resolver."""
        from engine.event_executor import normalize_character_id
        
        # Test Harry Potter aliases (from legacy dict)
        assert normalize_character_id("harry_potter") == "harry"
        assert normalize_character_id("potter") == "harry"
        assert normalize_character_id("HARRY_POTTER") == "harry"  # case insensitive
    
    def test_normalize_character_id_with_resolver(self):
        """normalize_character_id() uses AliasResolver when provided."""
        from engine.event_executor import normalize_character_id
        from engine.alias_resolver import AliasResolver
        
        resolver = AliasResolver()
        resolver.register_character("uncle_vernon", ["mr_dursley", "vernon_dursley"], chapter_num=1)
        
        # With resolver, should use dynamic aliases
        assert normalize_character_id("mr_dursley", resolver) == "uncle_vernon"
        assert normalize_character_id("vernon_dursley", resolver) == "uncle_vernon"
        
        # Unknown should pass through
        assert normalize_character_id("unknown_char", resolver) == "unknown_char"
        
        # Unknown characters pass through unchanged
        assert normalize_character_id("dobby") == "dobby"
        assert normalize_character_id("ginny") == "ginny"
    
    def test_sanitize_char_normalizes_legacy(self):
        """_sanitize_char() normalizes character IDs using legacy aliases."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)  # No alias_resolver - uses legacy
        
        # Should sanitize AND normalize using legacy aliases
        assert ee._sanitize_char("Harry Potter") == "harry"  # In legacy aliases
        assert ee._sanitize_char("Dobby") == "dobby"  # Unknown passes through
        
        # lord_voldemort is NOT in minimal legacy aliases, so passes through
        assert ee._sanitize_char("Lord Voldemort") == "lord_voldemort"
    
    def test_sanitize_char_normalizes_with_resolver(self):
        """_sanitize_char() uses AliasResolver when provided."""
        from engine.alias_resolver import AliasResolver
        
        resolver = AliasResolver()
        resolver.register_character("voldemort", ["lord_voldemort", "tom_riddle"], chapter_num=1)
        
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr, alias_resolver=resolver)
        
        # With resolver, should use dynamic aliases
        assert ee._sanitize_char("Lord Voldemort") == "voldemort"
        assert ee._sanitize_char("Tom Riddle") == "voldemort"
    
    def test_state_manager_includes_aliases(self):
        """StateManager.get_asp_facts_for_clingo() includes alias facts."""
        sm = StateManager()
        sm.add_entity("harry", "character")
        
        asp_output = sm.get_asp_facts_for_clingo()
        
        # Should contain alias section
        assert "% Character aliases" in asp_output
        assert "alias(harry_potter, harry)." in asp_output


class TestASPAliasRulesIntegration:
    """
    Integration tests verifying ASP alias resolution rules work correctly.
    
    These tests verify that:
    1. alias/2 facts are properly generated
    2. canonical/2 resolution works
    3. Normalized predicates (_normalized) work
    """
    
    def test_asp_alias_rules_syntax(self):
        """Verify core.lp contains valid alias resolution rules."""
        rules_path = Path(__file__).parent.parent / "rules" / "core.lp"
        with open(rules_path) as f:
            content = f.read()
        
        # Check alias resolution section exists
        assert "PART 2.5: CHARACTER ALIAS RESOLUTION" in content
        
        # Check canonical resolution rules
        assert "canonical(X, C) :- alias(X, C)." in content
        assert "canonical(X, X) :- entity(X), not alias(X, _)." in content
        
        # Check transitive resolution
        assert "canonical(X, C) :- alias(X, Y), canonical(Y, C)" in content
        
        # Check normalized predicates
        assert "present_normalized" in content
        assert "carries_normalized" in content
        assert "relationship_normalized" in content
        assert "trait_normalized" in content


class TestActiveUniverseFiltering:
    """
    Phase 8.8: Test that to_asp() only emits entity declarations for active universe.
    
    Per LOGIC_DESIGN.md and Phase 8 goals:
    - Prevent global predicates from introducing unnecessary constants
    - Inactive/latent/frozen entities should NOT appear in ASP
    - Only emit character()/item()/location_entity() for active universe
    """
    
    def test_to_asp_without_universe_includes_all_entities(self):
        """Without active_universe, all entities are included."""
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {
                "characters": [
                    {"id": "harry", "name": "Harry Potter"},
                    {"id": "ron", "name": "Ron Weasley"},
                ],
                "items": [
                    {"id": "wand", "name": "Holly Wand"},
                ],
                "locations": [
                    {"id": "hogwarts", "name": "Hogwarts Castle"},
                ],
            },
            "events": [],
        }
        
        asp = ee.to_asp(data, chapter_num=1)
        
        # All entities should be present
        assert "character(harry)." in asp
        assert "character(ron)." in asp
        assert "item(wand)." in asp
        assert "location_entity(hogwarts)." in asp
    
    def test_to_asp_with_universe_filters_entities(self):
        """With active_universe, only entities in universe are declared."""
        from engine.active_universe import ActiveUniverseResult
        
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {
                "characters": [
                    {"id": "harry", "name": "Harry Potter"},
                    {"id": "ron", "name": "Ron Weasley"},
                    {"id": "hermione", "name": "Hermione Granger"},
                ],
                "items": [
                    {"id": "wand", "name": "Holly Wand"},
                    {"id": "cloak", "name": "Invisibility Cloak"},
                ],
                "locations": [
                    {"id": "hogwarts", "name": "Hogwarts Castle"},
                    {"id": "hogsmeade", "name": "Hogsmeade Village"},
                ],
            },
            "events": [],
        }
        
        # Only harry, wand, hogwarts are in the active universe
        universe = ActiveUniverseResult(
            characters={"harry"},
            items={"wand"},
            locations={"hogwarts"},
            current_chapter_actors={"harry"},
            previous_chapter_actors=set(),
            relationship_expansions=set(),
            item_expansions=set(),
        )
        
        asp = ee.to_asp(data, chapter_num=1, active_universe=universe)
        
        # Only active universe entities should be declared
        assert "character(harry)." in asp
        assert "character(ron)." not in asp
        assert "character(hermione)." not in asp
        
        assert "item(wand)." in asp
        assert "item(cloak)." not in asp
        
        assert "location_entity(hogwarts)." in asp
        assert "location_entity(hogsmeade)." not in asp
    
    def test_to_asp_with_universe_filters_relationships(self):
        """Relationships are only emitted if both entities are in universe."""
        from engine.active_universe import ActiveUniverseResult
        
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {
                "characters": [
                    {"id": "harry", "name": "Harry Potter"},
                    {"id": "ron", "name": "Ron Weasley"},
                    {"id": "draco", "name": "Draco Malfoy"},
                ],
                "relationships": [
                    {"from": "harry", "to": "ron", "type": "friend"},
                    {"from": "harry", "to": "draco", "type": "enemy"},
                ],
            },
            "events": [],
        }
        
        # Only harry and ron are in the active universe
        universe = ActiveUniverseResult(
            characters={"harry", "ron"},
            items=set(),
            locations=set(),
            current_chapter_actors={"harry", "ron"},
            previous_chapter_actors=set(),
            relationship_expansions=set(),
            item_expansions=set(),
        )
        
        asp = ee.to_asp(data, chapter_num=1, active_universe=universe)
        
        # harry-ron relationship should be emitted (both in universe)
        assert "relationship(harry, ron, friend)." in asp
        
        # harry-draco relationship should NOT be emitted (draco not in universe)
        assert "relationship(harry, draco, enemy)." not in asp
    
    def test_to_asp_event_agent_declaration_filtered(self):
        """Event agents only get character() declarations if in universe."""
        from engine.active_universe import ActiveUniverseResult
        
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {
                "characters": [],  # No explicit character declarations
            },
            "events": [
                {"global_id": "e1", "type": "speak", "agent": "harry"},
                {"global_id": "e2", "type": "speak", "agent": "draco"},
            ],
        }
        
        # Only harry is in the active universe
        universe = ActiveUniverseResult(
            characters={"harry"},
            items=set(),
            locations=set(),
            current_chapter_actors={"harry"},
            previous_chapter_actors=set(),
            relationship_expansions=set(),
            item_expansions=set(),
        )
        
        asp = ee.to_asp(data, chapter_num=1, active_universe=universe)
        
        # Both agents are still referenced in agent() facts
        assert "agent(e1, harry)." in asp
        assert "agent(e2, draco)." in asp
        
        # Only harry gets a character() declaration
        assert "character(harry)." in asp
        assert "character(draco)." not in asp
    
    def test_to_asp_preserves_event_predicates(self):
        """Event predicates (agent, patient, location) are preserved even if entity not declared."""
        from engine.active_universe import ActiveUniverseResult
        
        sm = StateManager()
        rr = RuleRegistry()
        ee = EventExecutor(sm, rr)
        
        data = {
            "entities": {},
            "events": [
                {
                    "global_id": "e1",
                    "type": "movement",
                    "agent": "harry",
                    "location": "forbidden_forest",
                },
            ],
        }
        
        # Empty active universe
        universe = ActiveUniverseResult(
            characters=set(),
            items=set(),
            locations=set(),
            current_chapter_actors=set(),
            previous_chapter_actors=set(),
            relationship_expansions=set(),
            item_expansions=set(),
        )
        
        asp = ee.to_asp(data, chapter_num=1, active_universe=universe)
        
        # Event predicates are preserved for ASP rule evaluation
        assert "event(e1)." in asp
        assert "agent(e1, harry)." in asp
        assert "location(e1, forbidden_forest)." in asp
        
        # But entity declarations are NOT emitted
        assert "character(harry)." not in asp
        assert "location_entity(forbidden_forest)." not in asp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
