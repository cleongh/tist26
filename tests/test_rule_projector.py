"""
Tests for Rule Projector (Phase 8.11).

Tests that story-specific rules are projected into ASP only when
at least one entity referenced by the rule is in the active universe.
"""

import pytest
from engine.managers import RuleManager
from engine.domain import ProjectedRule, RuleProjectionResult
from engine.config import RESERVED_WORDS
from engine.preprocessors import AspConverter
from engine.registries import RuleRegistry
from engine.domain import RuleLayer
from engine.active_universe import ActiveUniverseResult

# Module-level converter for tests
_asp_converter = AspConverter()


class TestExtractEntitiesFromRule:
    """Test entity extraction from ASP rule content."""
    
    def test_extracts_from_story_exception(self):
        """Extract entity from story_exception(type, entity)."""
        rule = "story_exception(dead_character_acting, nearly_headless_nick)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "nearly_headless_nick" in entities
    
    def test_extracts_from_is_ghost(self):
        """Extract entity from is_ghost(entity)."""
        rule = "is_ghost(nearly_headless_nick)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "nearly_headless_nick" in entities
    
    def test_extracts_from_relationship_rule(self):
        """Extract entities from relationship_rule(subj, pred, obj, event)."""
        rule = "relationship_rule(harry_potter, loves, ginny_weasley, e10)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "harry_potter" in entities
        assert "ginny_weasley" in entities
        # Event IDs should be filtered
        assert "e10" not in entities
    
    def test_extracts_from_trait_rule(self):
        """Extract entity from trait_rule(subj, trait, event)."""
        rule = "trait_rule(hermione_granger, intelligent, e5)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "hermione_granger" in entities
    
    def test_extracts_from_location_rule(self):
        """Extract entities from location_rule(subj, loc, event)."""
        rule = "location_rule(harry_potter, hogwarts, e20)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "harry_potter" in entities
        assert "hogwarts" in entities
    
    def test_extracts_from_possession_rule(self):
        """Extract entities from possession_rule(subj, item, event)."""
        rule = "possession_rule(harry_potter, elder_wand, e50)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "harry_potter" in entities
        assert "elder_wand" in entities
    
    def test_extracts_multiple_entities(self):
        """Extract multiple entities from complex rule."""
        rule = """
        is_ghost(nearly_headless_nick).
        is_ghost(fat_friar).
        story_exception(dead_character_acting, nearly_headless_nick).
        story_exception(dead_character_acting, fat_friar).
        """
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "nearly_headless_nick" in entities
        assert "fat_friar" in entities
    
    def test_filters_reserved_words(self):
        """Reserved words should be filtered out."""
        rule = "story_override(dead_character_acting)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "story_override" not in entities
        assert "violation" not in entities
    
    def test_filters_single_letter_variables(self):
        """Single letters (variables) should be filtered."""
        rule = "trait(C, brave)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "c" not in entities
        assert "C" not in entities
    
    def test_filters_uppercase_variables(self):
        """ASP variables (uppercase) should be filtered."""
        rule = "-violation(Category, dead_character_acting, E, D) :- story_override(dead_character_acting), violation(Category, dead_character_acting, E, D)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "Category" not in entities
        assert "E" not in entities
        assert "D" not in entities
    
    def test_filters_event_ids(self):
        """Event IDs (e0, e1, e123) should be filtered."""
        rule = "relationship_rule(harry_potter, loves, ginny_weasley, e123)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert "e123" not in entities
        assert "e0" not in entities
    
    def test_empty_rule_returns_empty_set(self):
        """Empty rule returns empty set."""
        entities = _asp_converter.extract_entities_from_rule("")
        assert entities == set()
    
    def test_comment_only_rule(self):
        """Comment-only rule should return empty set."""
        rule = "% This is a comment with no facts"
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert entities == set()


class TestIsRuleInUniverse:
    """Test universe membership checking."""
    
    def test_no_universe_returns_true(self):
        """When no universe provided, all rules are included."""
        entities = {"harry_potter", "ron_weasley"}
        in_universe, reason = RuleManager.is_rule_in_universe(entities, None)
        assert in_universe is True
        assert reason == ""
    
    def test_empty_entities_returns_true(self):
        """Rules with no entities are included by default."""
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        in_universe, reason = RuleManager.is_rule_in_universe(set(), universe)
        assert in_universe is True
    
    def test_entity_in_universe_returns_true(self):
        """At least one entity in universe -> include."""
        universe = ActiveUniverseResult(
            characters={"harry_potter", "ron_weasley"},
            items=set(),
            locations=set(),
        )
        entities = {"harry_potter", "voldemort"}
        in_universe, reason = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is True
    
    def test_no_entity_in_universe_returns_false(self):
        """No entities in universe -> filter."""
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        entities = {"voldemort", "bellatrix"}
        in_universe, reason = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is False
        assert "no_entities_in_universe" in reason
    
    def test_location_in_universe(self):
        """Location entities count for universe membership."""
        universe = ActiveUniverseResult(
            characters=set(),
            items=set(),
            locations={"hogwarts"},
        )
        entities = {"hogwarts", "ministry_of_magic"}
        in_universe, reason = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is True
    
    def test_item_in_universe(self):
        """Item entities count for universe membership."""
        universe = ActiveUniverseResult(
            characters=set(),
            items={"elder_wand"},
            locations=set(),
        )
        entities = {"elder_wand", "resurrection_stone"}
        in_universe, reason = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is True


class TestProjectStoryRules:
    """Test full story rule projection."""
    
    def test_no_universe_all_rules_projected(self):
        """Without universe, all active story rules are projected."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost_exception",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=None)
        assert result.projected_count == 1
        assert result.filtered_count == 0
    
    def test_with_universe_filters_inactive_entities(self):
        """Rules with no active entities are filtered."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost_exception",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=universe)
        assert result.projected_count == 0
        assert result.filtered_count == 1
    
    def test_with_universe_includes_active_entities(self):
        """Rules with active entities are included."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost_exception",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        universe = ActiveUniverseResult(
            characters={"nearly_headless_nick", "harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=universe)
        assert result.projected_count == 1
        assert result.filtered_count == 0
    
    def test_multiple_rules_mixed_filtering(self):
        """Multiple rules with mixed universe membership."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost_exception",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        registry.add_rule(
            "story:harry_magic",
            RuleLayer.STORY,
            "can_use_magic(harry_potter).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=universe)
        # harry_potter rule included, ghost rule filtered
        assert result.projected_count == 1
        assert result.filtered_count == 1
        assert result.projected_rules[0].rule_id == "story:harry_magic"
    
    def test_deactivated_rules_not_projected(self):
        """Deactivated rules are not included in projection."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:old_rule",
            RuleLayer.STORY,
            "is_ghost(peeves).",
        )
        registry.deactivate_rule(
            "story:old_rule",
            "story:new_rule",
            "Replaced by new rule",
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=None)
        assert result.projected_count == 0
    
    def test_entities_referenced_populated(self):
        """Projected rules have entities_referenced populated."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:relationship",
            RuleLayer.STORY,
            "relationship_rule(harry_potter, loves, ginny_weasley, e10).",
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=None)
        assert result.projected_count == 1
        entities = result.projected_rules[0].entities_referenced
        assert "harry_potter" in entities
        assert "ginny_weasley" in entities
    
    def test_empty_registry_returns_empty_result(self):
        """Empty registry returns empty result."""
        registry = RuleRegistry()
        result = RuleManager.project_story_rules(registry, active_universe=None)
        assert result.projected_count == 0
        assert result.filtered_count == 0
        assert result.total_story_rules == 0
    
    def test_universal_and_learned_rules_not_projected(self):
        """Only STORY layer rules are projected."""
        registry = RuleRegistry()
        registry.add_rule(
            "universal:physics",
            RuleLayer.UNIVERSAL,
            "cannot_fly(human).",
        )
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_friendly(hogwarts_student).",
        )
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=None)
        # Only story rule is included
        assert result.total_story_rules == 1
        assert result.projected_count == 1


class TestGetProjectedRulesContent:
    """Test content generation from projected rules."""
    
    def test_generates_asp_content(self):
        """Generates valid ASP content."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        content = RuleManager.get_projected_rules_content(registry, active_universe=None)
        assert "is_ghost(nearly_headless_nick)." in content
        assert "PROJECTED STORY RULES" in content
    
    def test_includes_rule_id_comment(self):
        """Rule IDs are included as comments."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        content = RuleManager.get_projected_rules_content(registry, active_universe=None)
        assert "story:ghost" in content
    
    def test_filtered_rules_not_in_content(self):
        """Filtered rules are not in content."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        content = RuleManager.get_projected_rules_content(registry, active_universe=universe)
        assert "nearly_headless_nick" not in content


class TestGetAllProjectedRulesContent:
    """Test combined content generation for all rule layers."""
    
    def test_includes_all_layers(self):
        """Content includes universal, learned, and story layers."""
        registry = RuleRegistry()
        registry.add_rule(
            "universal:physics",
            RuleLayer.UNIVERSAL,
            "gravity_applies(object).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "friends_help_friends(X, Y).",
        )
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        
        content = RuleManager.get_all_projected_rules_content(registry, active_universe=None)
        assert "UNIVERSAL RULES" in content
        assert "LEARNED RULES" in content
        assert "STORY RULES" in content
    
    def test_story_rules_filtered_by_universe(self):
        """Story rules are filtered but universal/learned are not."""
        registry = RuleRegistry()
        registry.add_rule(
            "universal:physics",
            RuleLayer.UNIVERSAL,
            "gravity_applies(object).",
        )
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(voldemort).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        content = RuleManager.get_all_projected_rules_content(registry, active_universe=universe)
        assert "gravity_applies" in content  # Universal included
        assert "voldemort" not in content  # Story filtered


class TestRuleProjectionResult:
    """Test RuleProjectionResult dataclass."""
    
    def test_to_dict_serialization(self):
        """Result can be serialized to dict."""
        result = RuleProjectionResult(
            projected_rules=[
                ProjectedRule(
                    rule_id="story:test",
                    content="test content",
                    layer="STORY",
                    entities_referenced={"harry_potter"},
                )
            ],
            filtered_rules=[],
            total_story_rules=1,
        )
        
        d = result.to_dict()
        assert d["total_story_rules"] == 1
        assert d["projected_count"] == 1
        assert d["filtered_count"] == 0
        assert len(d["projected"]) == 1
    
    def test_get_projected_content(self):
        """get_projected_content generates ASP string."""
        result = RuleProjectionResult(
            projected_rules=[
                ProjectedRule(
                    rule_id="story:test",
                    content="is_ghost(nick).",
                    layer="STORY",
                )
            ],
        )
        
        content = result.get_projected_content()
        assert "is_ghost(nick)." in content


class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_complex_rule_with_negation(self):
        """Complex rule with negation is handled."""
        rule = """
        -violation(Category, dead_character_acting, E, Entity) :- 
            story_exception(dead_character_acting, Entity),
            violation(Category, dead_character_acting, E, Entity).
        """
        entities = _asp_converter.extract_entities_from_rule(rule)
        # Category, E, Entity are variables -> filtered
        # dead_character_acting is a violation type -> might be filtered as reserved
        assert "Category" not in entities
        assert "Entity" not in entities
    
    def test_rule_with_only_generic_predicates(self):
        """Rule with only generic predicates has no entities."""
        rule = "story_override(dead_character_acting)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        # No entity-like values
        assert "story_override" not in entities
    
    def test_case_sensitivity_in_matching(self):
        """Entity matching is case-sensitive."""
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        # Lowercase entity
        entities = {"harry_potter"}
        in_universe, _ = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is True
        
        # Different case - not in universe
        entities = {"Harry_Potter"}
        in_universe, _ = RuleManager.is_rule_in_universe(entities, universe)
        assert in_universe is False
    
    def test_empty_universe_filters_all(self):
        """Empty universe filters all entity-referencing rules."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:ghost",
            RuleLayer.STORY,
            "is_ghost(nearly_headless_nick).",
        )
        
        empty_universe = ActiveUniverseResult(
            characters=set(),
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_story_rules(registry, active_universe=empty_universe)
        assert result.projected_count == 0
        assert result.filtered_count == 1
    
    def test_self_referencing_rule(self):
        """Rule mentioning same entity multiple times."""
        rule = "relationship_rule(harry_potter, knows, harry_potter, e0)."
        entities = _asp_converter.extract_entities_from_rule(rule)
        assert entities == {"harry_potter"}


class TestProjectLearnedRules:
    """Tests for learned rule projection (Phase 8.11.1)."""
    
    def test_no_universe_all_learned_rules_projected(self):
        """Without universe, all active learned rules are projected."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_friendly(harry_potter, ron_weasley).",
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=None)
        assert result.projected_count == 1
        assert result.filtered_count == 0
        assert result.total_learned_rules == 1
    
    def test_with_universe_filters_inactive_entities(self):
        """Learned rules with no active entities are filtered."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_friendly(voldemort, bellatrix).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=universe)
        assert result.projected_count == 0
        assert result.filtered_count == 1
    
    def test_with_universe_includes_active_entities(self):
        """Learned rules with active entities are included."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_friendly(harry_potter, ron_weasley).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter", "hermione_granger"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=universe)
        assert result.projected_count == 1
        assert result.filtered_count == 0
    
    def test_multiple_learned_rules_mixed_filtering(self):
        """Multiple learned rules with mixed universe membership."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_hostile(voldemort, harry_potter).",
        )
        registry.add_rule(
            "learned:pattern2",
            RuleLayer.LEARNED,
            "typically_friendly(draco_malfoy, crabbe).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter", "ron_weasley"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=universe)
        # Only pattern1 includes harry_potter
        assert result.projected_count == 1
        assert result.filtered_count == 1
        assert result.projected_rules[0].rule_id == "learned:pattern1"
    
    def test_generic_learned_rule_included(self):
        """Learned rules with no identifiable entities are included."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:generic",
            RuleLayer.LEARNED,
            # Generic rule with variables, no entity constants
            "friends_help(X, Y) :- relationship(X, Y, friend, T).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=universe)
        # Generic rules are included by default
        assert result.projected_count == 1
    
    def test_deactivated_learned_rules_not_projected(self):
        """Deactivated learned rules are not projected."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:old_pattern",
            RuleLayer.LEARNED,
            "old_pattern(harry_potter).",
        )
        registry.deactivate_rule(
            "learned:old_pattern",
            "learned:new_pattern",
            "Superseded",
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=None)
        assert result.projected_count == 0
    
    def test_story_rules_not_in_learned_projection(self):
        """Story rules are not included in learned rule projection."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        
        result = RuleManager.project_learned_rules(registry, active_universe=None)
        assert result.total_learned_rules == 1
        assert result.projected_count == 1
        assert result.projected_rules[0].rule_id == "learned:pattern"


class TestProjectRulesUnified:
    """Tests for unified rule projection function."""
    
    def test_projects_both_story_and_learned(self):
        """Unified projection includes both story and learned rules."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(ron_weasley).",
        )
        
        result = RuleManager.project_rules(registry, active_universe=None)
        assert result.total_story_rules == 1
        assert result.total_learned_rules == 1
        assert result.projected_count == 2
    
    def test_filters_both_layers_by_universe(self):
        """Both story and learned rules are filtered by universe."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(voldemort).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(bellatrix).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        result = RuleManager.project_rules(registry, active_universe=universe)
        assert result.projected_count == 0
        assert result.filtered_count == 2
    
    def test_layer_filter_story_only(self):
        """Can project only story layer."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        
        result = RuleManager.project_rules(registry, layers=['STORY'])
        assert result.total_story_rules == 1
        assert result.total_learned_rules == 0
        assert result.projected_count == 1
    
    def test_layer_filter_learned_only(self):
        """Can project only learned layer."""
        registry = RuleRegistry()
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        
        result = RuleManager.project_rules(registry, layers=['LEARNED'])
        assert result.total_story_rules == 0
        assert result.total_learned_rules == 1
        assert result.projected_count == 1


class TestGetProjectedLearnedRulesContent:
    """Tests for learned rule content generation."""
    
    def test_generates_asp_content(self):
        """Generates valid ASP content for learned rules."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        
        content = RuleManager.get_projected_learned_rules_content(registry, active_universe=None)
        assert "typically_brave(harry_potter)." in content
        assert "learned:pattern" in content
    
    def test_filtered_rules_not_in_content(self):
        """Filtered learned rules are not in content."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_friendly(voldemort, bellatrix).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        content = RuleManager.get_projected_learned_rules_content(registry, active_universe=universe)
        assert "voldemort" not in content
        assert "bellatrix" not in content


class TestGetAllProjectedRulesContentWithLearnedFiltering:
    """Tests for combined content with learned rule filtering."""
    
    def test_learned_rules_filtered_in_combined_content(self):
        """Learned rules are filtered in combined content (Phase 8.11.1)."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:inactive_pattern",
            RuleLayer.LEARNED,
            "typically_hostile(voldemort, bellatrix).",
        )
        registry.add_rule(
            "learned:active_pattern",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        registry.add_rule(
            "story:magic",
            RuleLayer.STORY,
            "can_fly(harry_potter).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        content = RuleManager.get_all_projected_rules_content(registry, active_universe=universe)
        
        # Active learned rule included
        assert "typically_brave(harry_potter)" in content
        # Inactive learned rule filtered
        assert "voldemort" not in content
        assert "bellatrix" not in content
        # Active story rule included
        assert "can_fly(harry_potter)" in content
    
    def test_universal_rules_not_filtered(self):
        """Universal rules are not filtered by entity."""
        registry = RuleRegistry()
        registry.add_rule(
            "universal:physics",
            RuleLayer.UNIVERSAL,
            "gravity_applies(object).",
        )
        registry.add_rule(
            "learned:pattern",
            RuleLayer.LEARNED,
            "typically_hostile(voldemort).",
        )
        
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        
        content = RuleManager.get_all_projected_rules_content(registry, active_universe=universe)
        
        # Universal rule included (not entity-filtered)
        assert "gravity_applies" in content
        # Learned rule filtered (references voldemort, not harry_potter)
        assert "voldemort" not in content


class TestLearnedRuleStorageUnchanged:
    """Tests that learned rule storage and history are not modified."""
    
    def test_projection_does_not_modify_registry(self):
        """Projection does not modify the rule registry."""
        registry = RuleRegistry()
        registry.add_rule(
            "learned:pattern1",
            RuleLayer.LEARNED,
            "typically_hostile(voldemort).",
        )
        registry.add_rule(
            "learned:pattern2",
            RuleLayer.LEARNED,
            "typically_brave(harry_potter).",
        )
        
        # Get initial state
        initial_learned_count = len(registry.get_active_rules(RuleLayer.LEARNED))
        
        # Project with filtering
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        result = RuleManager.project_learned_rules(registry, active_universe=universe)
        
        # Registry unchanged
        assert len(registry.get_active_rules(RuleLayer.LEARNED)) == initial_learned_count
        
        # Projection filtered correctly
        assert result.projected_count == 1
        assert result.filtered_count == 1
    
    def test_learned_rules_content_list_unchanged(self):
        """learned_rules_content list in registry is not modified."""
        registry = RuleRegistry()
        registry.add_learned_rule("typically_hostile(voldemort).", source="ILASP")
        registry.add_learned_rule("typically_brave(harry_potter).", source="ILASP")
        
        # Get initial content
        initial_content = registry.get_learned_rules_content()
        
        # Project with filtering
        universe = ActiveUniverseResult(
            characters={"harry_potter"},
            items=set(),
            locations=set(),
        )
        RuleManager.project_learned_rules(registry, active_universe=universe)
        
        # Content list unchanged
        assert registry.get_learned_rules_content() == initial_content
        assert len(registry.get_learned_rules_content()) == 2
