"""
Tests for scripts/precision_layer.py (see the module docstring there for the
documented approximation this deterministic layer makes). This layer is
diagnostic only (contradiction-episode clustering + breakpoint detection) --
it never suppresses candidates; see /memories/repo/kfold-eval-baselines.md
for the ablation results that led to removing the suppression stages.
"""

from scripts.precision_layer import (
    build_candidates,
    build_conflict_components,
    compute_component_features,
    compute_candidate_features,
    decide_candidates,
    apply_precision_layer,
    FEATURE_NAMES,
)


def _make_violation(category, vtype, chapter_id, *entities):
    """Build a minimal violation dict shaped like StructuredViolation.to_dict()."""
    return {
        "category": category,
        "type": vtype,
        "event_id": f"e{chapter_id}",
        "entities": list(entities),
        "args": [category, vtype, f"e{chapter_id}", *entities],
    }


def _signature_fn(v):
    """Minimal stand-in for the real _violation_signature: (category, type)
    plus the non-event-id entity tokens."""
    return (v["category"], v["type"]) + tuple(v.get("entities", []))


def _prepare(chapter_violations):
    """Run the feature-computation pipeline, returning (candidates, component_info)."""
    candidates = build_candidates("story", chapter_violations, _signature_fn)
    build_conflict_components(candidates)
    info = compute_component_features(candidates)
    compute_candidate_features(candidates, info)
    return candidates, info


class TestConflictEpisodeClustering:
    def test_two_candidates_sharing_rare_entity_merge(self):
        chapter_violations = {
            1: [_make_violation("emotional", "relationship_action_mismatch", 1, "harry", "ron")],
            2: [_make_violation("emotional", "learned_relationship_action_mismatch", 2, "harry", "ron")],
        }
        candidates, _ = _prepare(chapter_violations)
        assert candidates[0].component_id == candidates[1].component_id

    def test_unrelated_candidates_do_not_merge(self):
        chapter_violations = {
            1: [_make_violation("emotional", "relationship_action_mismatch", 1, "harry", "ron")],
            2: [_make_violation("emotional", "relationship_action_mismatch", 2, "bella", "edward")],
        }
        candidates, _ = _prepare(chapter_violations)
        assert candidates[0].component_id != candidates[1].component_id


class TestBreakpointDetection:
    def test_first_occurrence_is_breakpoint_and_downstream_are_not(self):
        chapter_violations = {
            10: [_make_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_make_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_make_violation("causality", "interacting_with_dead", 12, "x")],
        }
        candidates, _ = _prepare(chapter_violations)
        by_chapter = {c.chapter: c for c in candidates}
        assert by_chapter[10].features["is_breakpoint"] == 1.0
        assert by_chapter[11].features["is_breakpoint"] == 0.0
        assert by_chapter[12].features["is_breakpoint"] == 0.0
        assert by_chapter[12].features["distance_from_first_conflict"] == 2.0


class TestIndependentEvidenceProvenanceRoots:
    def test_repeats_of_the_same_rule_count_as_one_provenance_root(self):
        chapter_violations = {
            5: [_make_violation("causality", "interacting_with_dead", 5, "x")],
            6: [_make_violation("causality", "interacting_with_dead", 6, "x")],
            7: [_make_violation("causality", "interacting_with_dead", 7, "x")],
        }
        candidates, info = _prepare(chapter_violations)
        cid = candidates[0].component_id
        assert info[cid]["n_types"] == 1
        assert all(c.features["independent_evidence"] == 1.0 for c in candidates)

    def test_different_rule_types_count_as_separate_provenance_roots(self):
        chapter_violations = {
            5: [_make_violation("causality", "interacting_with_dead", 5, "x")],
            6: [_make_violation("causality", "chekhov_gun", 6, "x")],
        }
        candidates, info = _prepare(chapter_violations)
        cid = candidates[0].component_id
        assert info[cid]["n_types"] == 2
        assert all(c.features["independent_evidence"] == 2.0 for c in candidates)


class TestDecisionsAreDiagnosticOnly:
    def test_no_candidate_is_ever_suppressed(self):
        chapter_violations = {
            ch: [_make_violation("causality", "interacting_with_dead", ch, "x")]
            for ch in range(1, 12)
        }
        candidates, info = _prepare(chapter_violations)
        decide_candidates(candidates, info)
        assert all(c.decision == "RETAIN" for c in candidates)

    def test_episode_role_is_recorded_in_reason(self):
        chapter_violations = {
            1: [_make_violation("causality", "interacting_with_dead", 1, "x")],
            5: [_make_violation("causality", "interacting_with_dead", 5, "x")],
        }
        candidates, info = _prepare(chapter_violations)
        decide_candidates(candidates, info)
        by_chapter = {c.chapter: c for c in candidates}
        assert "breakpoint" in by_chapter[1].reason
        assert "downstream_repeat" in by_chapter[5].reason


class TestDeterminism:
    def test_repeated_runs_produce_identical_decisions(self):
        chapter_violations = {
            ch: [_make_violation("temporal", "prerequisite_not_met", ch, "learn", "realize")]
            for ch in range(1, 6)
        }
        decisions_runs = []
        for _ in range(3):
            candidates, info = _prepare(chapter_violations)
            decide_candidates(candidates, info)
            decisions_runs.append(tuple(c.decision for c in candidates))
        assert decisions_runs[0] == decisions_runs[1] == decisions_runs[2]


class TestUnknownNumberOfErrors:
    def test_zero_candidates_does_not_crash(self):
        new_violations, candidates, info = apply_precision_layer(
            "story", {1: [], 2: []}, [], _signature_fn,
        )
        assert candidates == []
        assert new_violations == {1: [], 2: []}

    def test_single_candidate_story(self):
        chapter_violations = {1: [_make_violation("coherence", "solo_communication", 1, "harry")]}
        new_violations, candidates, info = apply_precision_layer(
            "story", chapter_violations, [], _signature_fn,
        )
        assert len(candidates) == 1


class TestFullDriver:
    def test_apply_precision_layer_never_removes_candidates(self):
        chapter_violations = {
            1: [_make_violation("causality", "interacting_with_dead", 1, "x")],
            2: [_make_violation("causality", "interacting_with_dead", 2, "x")],
            3: [_make_violation("coherence", "impossible_self_action", 3, "harry")],
        }
        new_violations, candidates, info = apply_precision_layer(
            "story", chapter_violations, [], _signature_fn,
        )
        assert set(new_violations.keys()) == {1, 2, 3}
        assert all(isinstance(v, list) for v in new_violations.values())
        for chapter, violations in chapter_violations.items():
            assert len(new_violations[chapter]) == len(violations)

