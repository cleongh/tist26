"""
Tests for scripts/chapter_cap.py: confidence-ranked per-chapter cap with
diversity-first selection.
"""

import inspect

import scripts.chapter_cap as chapter_cap_module
from scripts.chapter_cap import (
    violation_tier,
    select_top_n_per_chapter,
    apply_chapter_cap,
)
from scripts.confidence_verifier import Tier


def _violation(category, vtype, event_id="e1", provenance=None):
    v = {"category": category, "type": vtype, "event_id": event_id, "entities": [], "args": [category, vtype, event_id]}
    if provenance is not None:
        v["provenance"] = provenance
    return v


class TestViolationTier:
    def test_absence_profile_is_low(self):
        assert violation_tier(_violation("causality", "chekhov_gun")) == Tier.LOW

    def test_explicit_contradiction_with_two_facts_is_high(self):
        v = _violation("coherence", "contradictory_state", provenance={"triggering_facts": ["a", "b"]})
        assert violation_tier(v) == Tier.HIGH


class TestSelectTopNPerChapter:
    def test_chapter_at_or_under_cap_is_unchanged(self):
        violations = [_violation("causality", "chekhov_gun", "e1"), _violation("causality", "chekhov_gun", "e2")]
        assert select_top_n_per_chapter(violations, 3) == violations

    def test_caps_to_exactly_n(self):
        violations = [_violation("causality", "chekhov_gun", f"e{i}") for i in range(5)]
        result = select_top_n_per_chapter(violations, 2)
        assert len(result) == 2

    def test_high_tier_always_beats_low_tier_for_a_slot(self):
        low = _violation("causality", "chekhov_gun", "e1")
        high = _violation("coherence", "contradictory_state", "e2", provenance={"triggering_facts": ["a", "b"]})
        result = select_top_n_per_chapter([low, low, high], 1)
        assert result == [high]

    def test_diversity_pass_prefers_distinct_types_over_repeats(self):
        # Two LOW candidates of the SAME type vs one LOW candidate of a
        # DIFFERENT type -- with cap=2, diversity should keep one of each
        # type rather than two of the first type.
        type_a_1 = _violation("causality", "chekhov_gun", "e1")
        type_a_2 = _violation("causality", "chekhov_gun", "e2")
        type_b = _violation("temporal", "prerequisite_not_met", "e3")
        result = select_top_n_per_chapter([type_a_1, type_a_2, type_b], 2)
        types = {(v["category"], v["type"]) for v in result}
        assert types == {("causality", "chekhov_gun"), ("temporal", "prerequisite_not_met")}

    def test_fill_pass_allows_repeats_when_too_few_distinct_types(self):
        # Only ONE distinct type exists but cap=2 -- fill pass must top up
        # with a second occurrence of that same type rather than under-fill.
        violations = [_violation("causality", "chekhov_gun", "e1"), _violation("causality", "chekhov_gun", "e2")]
        result = select_top_n_per_chapter(violations, 2)
        assert len(result) == 2

    def test_ties_within_same_tier_keep_original_relative_order(self):
        violations = [_violation("causality", "chekhov_gun", f"e{i}") for i in range(3)]
        result = select_top_n_per_chapter(violations, 3)
        assert [v["event_id"] for v in result] == ["e0", "e1", "e2"]

    def test_result_preserves_original_chapter_order_not_tier_order(self):
        low = _violation("causality", "chekhov_gun", "e_low")
        high = _violation("coherence", "contradictory_state", "e_high", provenance={"triggering_facts": ["a", "b"]})
        result = select_top_n_per_chapter([low, high], 2)
        assert [v["event_id"] for v in result] == ["e_low", "e_high"]

    def test_cap_of_zero_returns_all(self):
        violations = [_violation("causality", "chekhov_gun", "e1")]
        assert select_top_n_per_chapter(violations, 0) == violations


class TestApplyChapterCap:
    def test_applies_cap_to_every_chapter_independently(self):
        chapter_violations = {
            1: [_violation("causality", "chekhov_gun", f"e{i}") for i in range(4)],
            2: [_violation("causality", "chekhov_gun", "e5")],
        }
        result = apply_chapter_cap(chapter_violations, 2)
        assert len(result[1]) == 2
        assert len(result[2]) == 1


class TestNeverReadsGroundTruth:
    def test_module_has_no_ground_truth_imports(self):
        source = inspect.getsource(chapter_cap_module)
        assert "import errors_checklist" not in source
        assert "ERRORS_CHECKLIST_DIR" not in source
        assert "GroundTruthError" not in source
        assert "load_ground_truth" not in source
