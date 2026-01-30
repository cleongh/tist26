"""
Unit Tests for RuleRegistry

Phase 6, Step 6.1: Test RuleRegistry priority resolution

Tests:
    - Rule layer priorities (story > learned > universal)
    - Rule activation/deactivation
    - Override tracking and audit
    - Rule file loading
"""

import pytest
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.rule_registry import RuleRegistry, RuleLayer, Rule, RuleOverride


class TestRuleRegistryBasics:
    """Basic RuleRegistry functionality."""
    
    def test_initialization(self):
        """RuleRegistry initializes with empty rules."""
        rr = RuleRegistry()
        
        assert len(rr.rules) == 0
        assert len(rr.overrides) == 0
        assert len(rr.learned_rules_content) == 0
    
    def test_add_rule(self):
        """add_rule adds a rule to the registry."""
        rr = RuleRegistry()
        
        rule = rr.add_rule(
            rule_id="test:rule1",
            layer=RuleLayer.UNIVERSAL,
            content="violation(test, test, E, D) :- event(E), bad(D).",
            source="test"
        )
        
        assert rule.id == "test:rule1"
        assert rule.layer == RuleLayer.UNIVERSAL
        assert rule.active is True
        assert "test:rule1" in rr.rules


class TestRuleLayerPriority:
    """Rule layer priority tests (story > learned > universal)."""
    
    def test_priority_values(self):
        """Story has highest priority, universal has lowest."""
        assert RuleLayer.STORY.value > RuleLayer.LEARNED.value
        assert RuleLayer.LEARNED.value > RuleLayer.UNIVERSAL.value
    
    def test_rule_get_priority(self):
        """Rule.get_priority returns layer value."""
        story_rule = Rule(id="s1", layer=RuleLayer.STORY, content="test")
        learned_rule = Rule(id="l1", layer=RuleLayer.LEARNED, content="test")
        universal_rule = Rule(id="u1", layer=RuleLayer.UNIVERSAL, content="test")
        
        assert story_rule.get_priority() > learned_rule.get_priority()
        assert learned_rule.get_priority() > universal_rule.get_priority()
    
    def test_get_active_rules_sorted_by_priority(self):
        """get_active_rules returns rules sorted by priority (highest first)."""
        rr = RuleRegistry()
        
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal rule")
        rr.add_rule("l1", RuleLayer.LEARNED, "learned rule")
        rr.add_rule("s1", RuleLayer.STORY, "story rule")
        
        active = rr.get_active_rules()
        
        assert len(active) == 3
        assert active[0].layer == RuleLayer.STORY
        assert active[1].layer == RuleLayer.LEARNED
        assert active[2].layer == RuleLayer.UNIVERSAL
    
    def test_get_active_rules_filtered_by_layer(self):
        """get_active_rules can filter by layer."""
        rr = RuleRegistry()
        
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal rule 1")
        rr.add_rule("u2", RuleLayer.UNIVERSAL, "universal rule 2")
        rr.add_rule("l1", RuleLayer.LEARNED, "learned rule")
        
        universal_only = rr.get_active_rules(RuleLayer.UNIVERSAL)
        
        assert len(universal_only) == 2
        for rule in universal_only:
            assert rule.layer == RuleLayer.UNIVERSAL


class TestRuleActivation:
    """Rule activation/deactivation tests."""
    
    def test_deactivate_rule(self):
        """deactivate_rule marks rule as inactive."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "test rule")
        
        result = rr.deactivate_rule(
            rule_id="u1",
            overriding_rule_id="s1",
            reason="Story overrides this"
        )
        
        assert result is True
        assert rr.rules["u1"].active is False
        assert rr.rules["u1"].overridden_by == "s1"
    
    def test_deactivate_nonexistent_rule(self):
        """deactivate_rule returns False for nonexistent rule."""
        rr = RuleRegistry()
        
        result = rr.deactivate_rule("nonexistent", "s1", "test")
        
        assert result is False
    
    def test_reactivate_rule(self):
        """reactivate_rule makes rule active again."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "test rule")
        rr.deactivate_rule("u1", "s1", "test")
        
        result = rr.reactivate_rule("u1")
        
        assert result is True
        assert rr.rules["u1"].active is True
        assert rr.rules["u1"].overridden_by is None
    
    def test_get_deactivated_rules(self):
        """get_deactivated_rules returns only inactive rules."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "active rule")
        rr.add_rule("u2", RuleLayer.UNIVERSAL, "will deactivate")
        rr.deactivate_rule("u2", "s1", "test")
        
        deactivated = rr.get_deactivated_rules()
        
        assert len(deactivated) == 1
        assert deactivated[0].id == "u2"


class TestRuleOverrides:
    """Override tracking tests (for auditing per LOGIC_DESIGN.md)."""
    
    def test_override_recorded(self):
        """Overrides are recorded when rules are deactivated."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "test rule")
        
        rr.deactivate_rule("u1", "s1", "Story requires exception")
        
        assert len(rr.overrides) == 1
        assert rr.overrides[0].overridden_rule_id == "u1"
        assert rr.overrides[0].overriding_rule_id == "s1"
        assert rr.overrides[0].reason == "Story requires exception"
    
    def test_get_override_history(self):
        """get_override_history returns all overrides as dicts."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "rule 1")
        rr.add_rule("u2", RuleLayer.UNIVERSAL, "rule 2")
        
        rr.deactivate_rule("u1", "s1", "reason 1")
        rr.deactivate_rule("u2", "s2", "reason 2")
        
        history = rr.get_override_history()
        
        assert len(history) == 2
        assert history[0]["overridden"] == "u1"
        assert history[1]["overridden"] == "u2"


class TestLearnedRules:
    """ILASP learned rule tests."""
    
    def test_add_learned_rule(self):
        """add_learned_rule adds to registry and content list."""
        rr = RuleRegistry()
        
        rule_id = rr.add_learned_rule(
            "violation(learned, test, E, D) :- event(E), pattern(D).",
            source="ILASP chapter 3"
        )
        
        assert "learned:" in rule_id
        assert rule_id in rr.rules
        assert rr.rules[rule_id].layer == RuleLayer.LEARNED
        assert len(rr.learned_rules_content) == 1
    
    def test_get_learned_rules_content(self):
        """get_learned_rules_content returns content strings."""
        rr = RuleRegistry()
        
        rr.add_learned_rule("rule1 :- condition1.")
        rr.add_learned_rule("rule2 :- condition2.")
        
        content = rr.get_learned_rules_content()
        
        assert len(content) == 2
        assert "rule1 :- condition1." in content
        assert "rule2 :- condition2." in content
    
    def test_learned_rules_no_duplicates(self):
        """Duplicate learned rules are not added twice."""
        rr = RuleRegistry()
        
        rr.add_learned_rule("rule1 :- condition1.")
        rr.add_learned_rule("rule1 :- condition1.")  # duplicate
        
        content = rr.get_learned_rules_content()
        
        assert len(content) == 1


class TestRuleAudit:
    """Audit functionality tests (per LOGIC_DESIGN.md Section 6)."""
    
    def test_audit_summary(self):
        """audit_summary provides complete overview."""
        rr = RuleRegistry()
        
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal 1")
        rr.add_rule("u2", RuleLayer.UNIVERSAL, "universal 2")
        rr.add_learned_rule("learned 1")
        rr.add_rule("s1", RuleLayer.STORY, "story 1")
        
        rr.deactivate_rule("u1", "s1", "story override")
        
        summary = rr.audit_summary()
        
        assert summary["total_rules"] == 4
        assert summary["active_rules"] == 3
        assert summary["deactivated_rules"] == 1
        assert summary["override_count"] == 1
        assert summary["active_by_layer"]["UNIVERSAL"] == 1
        assert summary["active_by_layer"]["LEARNED"] == 1
        assert summary["active_by_layer"]["STORY"] == 1


class TestRuleReset:
    """Reset functionality tests."""
    
    def test_reset_clears_learned_and_story(self):
        """reset removes learned and story rules, keeps universal."""
        rr = RuleRegistry()
        
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal")
        rr.add_learned_rule("learned")
        rr.add_rule("s1", RuleLayer.STORY, "story")
        rr.deactivate_rule("u1", "s1", "test")
        
        rr.reset()
        
        # Universal should remain and be active
        assert "u1" in rr.rules
        assert rr.rules["u1"].active is True
        
        # Learned and story should be gone
        learned_rules = [r for r in rr.rules.values() if r.layer == RuleLayer.LEARNED]
        story_rules = [r for r in rr.rules.values() if r.layer == RuleLayer.STORY]
        assert len(learned_rules) == 0
        assert len(story_rules) == 0
        
        # Overrides and learned content cleared
        assert len(rr.overrides) == 0
        assert len(rr.learned_rules_content) == 0


class TestRulePersistence:
    """Save/load functionality tests."""
    
    def test_save_and_load(self):
        """Rules can be saved and loaded from file."""
        rr = RuleRegistry()
        rr.add_rule("u1", RuleLayer.UNIVERSAL, "universal rule")
        rr.add_learned_rule("learned rule")
        rr.deactivate_rule("u1", "l1", "test override")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            save_path = Path(f.name)
        
        try:
            rr.save(save_path)
            
            # Load into new registry
            rr2 = RuleRegistry()
            rr2.load(save_path)
            
            assert "u1" in rr2.rules
            assert rr2.rules["u1"].active is False
            assert len(rr2.overrides) == 1
        finally:
            save_path.unlink()


class TestLegacyRules:
    """Legacy rule file loading tests."""
    
    def test_load_legacy_rules_default(self):
        """load_legacy_rules loads default rule files if they exist."""
        rr = RuleRegistry()
        
        # This may or may not load rules depending on whether files exist
        count = rr.load_legacy_rules()
        
        # At minimum, should not error
        assert count >= 0
    
    def test_legacy_rule_files_tracked(self):
        """Loaded legacy files are tracked in legacy_rule_files."""
        rr = RuleRegistry()
        rr.load_legacy_rules()
        
        # legacy_rule_files should contain paths
        assert isinstance(rr.legacy_rule_files, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
