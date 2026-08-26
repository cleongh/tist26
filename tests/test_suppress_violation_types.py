"""
Tests for scripts/kfold_experiment_runner_conflict_resolver.py's
suppress_violation_types() and the --suppress-types/--suppress-tier1-zero-cost
CLI wiring.
"""

from scripts.kfold_experiment_runner_conflict_resolver import (
    suppress_violation_types,
    TIER1_ZERO_RECALL_COST_TYPES,
    TIER2_LOW_RECALL_COST_TYPES,
)


def _v(category, vtype):
    return {"category": category, "type": vtype, "event_id": "e1", "entities": []}


class TestSuppressViolationTypes:
    def test_removes_only_matching_keys(self):
        cache = {1: [_v("emotional", "relationship_action_mismatch"), _v("coherence", "a")]}
        result = suppress_violation_types(cache, {("emotional", "relationship_action_mismatch")})
        assert [v["type"] for v in result[1]] == ["a"]

    def test_no_matching_keys_is_a_no_op(self):
        cache = {1: [_v("coherence", "a"), _v("temporal", "b")]}
        result = suppress_violation_types(cache, {("emotional", "relationship_action_mismatch")})
        assert result == cache

    def test_empty_suppress_keys_is_a_no_op(self):
        cache = {1: [_v("coherence", "a")]}
        result = suppress_violation_types(cache, set())
        assert result == cache

    def test_removes_across_multiple_chapters(self):
        cache = {
            1: [_v("emotional", "relationship_action_mismatch")],
            2: [_v("emotional", "relationship_action_mismatch"), _v("coherence", "a")],
        }
        result = suppress_violation_types(cache, {("emotional", "relationship_action_mismatch")})
        assert result[1] == []
        assert [v["type"] for v in result[2]] == ["a"]


class TestTier1ZeroRecallCostTypes:
    def test_expected_membership(self):
        assert TIER1_ZERO_RECALL_COST_TYPES == {
            ("location", "impossible_travel"),
            ("coherence", "contradictory_state"),
            ("coherence", "abnormal_color"),
            ("emotional", "relationship_action_mismatch"),
            ("location", "item_ubiquity"),
            ("coherence", "impossible_self_action"),
            ("possession", "give_without_having"),
            ("temporal", "missing_prerequisite"),
        }

    def test_suppresses_all_tier1_types(self):
        cache = {1: [_v(cat, t) for cat, t in TIER1_ZERO_RECALL_COST_TYPES] + [_v("temporal", "sequence_anomaly")]}
        result = suppress_violation_types(cache, TIER1_ZERO_RECALL_COST_TYPES)
        assert [v["type"] for v in result[1]] == ["sequence_anomaly"]


class TestTier2LowRecallCostTypes:
    def test_expected_membership(self):
        assert TIER2_LOW_RECALL_COST_TYPES == {("emotional", "friendly_hostile_action")}

    def test_disjoint_from_tier1(self):
        assert TIER1_ZERO_RECALL_COST_TYPES.isdisjoint(TIER2_LOW_RECALL_COST_TYPES)

    def test_combines_with_tier1(self):
        cache = {1: [
            _v("emotional", "friendly_hostile_action"),
            _v("location", "impossible_travel"),
            _v("temporal", "sequence_anomaly"),
        ]}
        result = suppress_violation_types(cache, TIER1_ZERO_RECALL_COST_TYPES | TIER2_LOW_RECALL_COST_TYPES)
        assert [v["type"] for v in result[1]] == ["sequence_anomaly"]
