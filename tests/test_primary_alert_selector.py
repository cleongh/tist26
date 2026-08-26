"""
Tests for scripts/primary_alert_selector.py.

All synthetic -- no ground truth, no original-story data, no story/chapter
names beyond generic placeholders. Verifies the primary/supporting
disposition invariants required by the modified-only precision pipeline.
"""

import inspect

from scripts.primary_alert_selector import select_primary_alerts, primary_only


def _v(category, vtype, event_id="e1", entities=None, source_text=None):
    return {
        "category": category,
        "type": vtype,
        "event_id": event_id,
        "entities": entities or [],
        "source_text": source_text,
    }


class TestOnePrimaryPerChapterCategory:
    def test_single_violation_becomes_primary(self):
        cache = {1: [_v("coherence", "contradictory_state")]}
        annotated = select_primary_alerts(cache)
        assert [v["disposition"] for v in annotated[1]] == ["primary"]

    def test_multiple_same_category_yields_exactly_one_primary(self):
        cache = {1: [
            _v("coherence", "a"),
            _v("coherence", "b"),
            _v("coherence", "c"),
        ]}
        annotated = select_primary_alerts(cache)
        dispositions = [v["disposition"] for v in annotated[1]]
        assert dispositions.count("primary") == 1
        assert dispositions.count("supporting") == 2

    def test_different_categories_each_get_own_primary(self):
        cache = {1: [
            _v("coherence", "a"),
            _v("temporal", "b"),
            _v("location", "c"),
        ]}
        annotated = select_primary_alerts(cache)
        primaries = [v for v in annotated[1] if v["disposition"] == "primary"]
        assert {v["category"] for v in primaries} == {"coherence", "temporal", "location"}

    def test_separate_chapters_are_independent_groups(self):
        cache = {
            1: [_v("coherence", "a"), _v("coherence", "b")],
            2: [_v("coherence", "c")],
        }
        annotated = select_primary_alerts(cache)
        assert sum(v["disposition"] == "primary" for v in annotated[1]) == 1
        assert sum(v["disposition"] == "primary" for v in annotated[2]) == 1


class TestRankingPrefersAnchoredEvidence:
    def test_anchored_event_beats_chapter_aggregate(self):
        cache = {1: [
            _v("temporal", "sequence_anomaly", event_id="chapter"),
            _v("temporal", "explicit_order_violated", event_id="e5"),
        ]}
        annotated = select_primary_alerts(cache)
        primary = next(v for v in annotated[1] if v["disposition"] == "primary")
        assert primary["type"] == "explicit_order_violated"

    def test_aggregate_can_be_primary_if_sole_candidate(self):
        cache = {1: [_v("temporal", "sequence_anomaly", event_id="chapter")]}
        annotated = select_primary_alerts(cache)
        assert annotated[1][0]["disposition"] == "primary"
        assert annotated[1][0]["rank_reason"] == "sole_candidate_aggregate"

    def test_source_text_preferred_over_missing(self):
        cache = {1: [
            _v("coherence", "a", event_id="e1", source_text=None),
            _v("coherence", "b", event_id="e2", source_text="he smiled"),
        ]}
        annotated = select_primary_alerts(cache)
        primary = next(v for v in annotated[1] if v["disposition"] == "primary")
        assert primary["type"] == "b"

    def test_more_entities_preferred(self):
        cache = {1: [
            _v("coherence", "a", event_id="e1", entities=["x"]),
            _v("coherence", "b", event_id="e2", entities=["x", "y"]),
        ]}
        annotated = select_primary_alerts(cache)
        primary = next(v for v in annotated[1] if v["disposition"] == "primary")
        assert primary["type"] == "b"

    def test_deterministic_stable_tie_break(self):
        cache = {1: [_v("coherence", "a"), _v("coherence", "b")]}
        first_run = select_primary_alerts(cache)
        second_run = select_primary_alerts(cache)
        assert first_run == second_run
        primary = next(v for v in first_run[1] if v["disposition"] == "primary")
        assert primary["type"] == "a"


class TestNoCandidatesLost:
    def test_primary_plus_supporting_equals_input(self):
        cache = {1: [_v("coherence", "a"), _v("coherence", "b"), _v("temporal", "c")]}
        annotated = select_primary_alerts(cache)
        assert len(annotated[1]) == 3

    def test_primary_only_never_exceeds_input(self):
        cache = {1: [_v("coherence", "a"), _v("coherence", "b"), _v("temporal", "c")]}
        result = primary_only(cache)
        assert sum(len(v) for v in result.values()) == 2  # one per category


class TestSourceIsolation:
    """Static checks that the selector never references ground truth or
    original-story data."""

    def test_no_ground_truth_or_original_references(self):
        import scripts.primary_alert_selector as mod
        source = inspect.getsource(mod)
        for forbidden in ("ground_truth", "GroundTruth", "original_extractions", "errors_checklist"):
            assert forbidden not in source
