"""
Tests for scripts/conflict_episodes.py -- the experimental conflict-episode
layer built on top of Exp1 (scripts/precision_layer.py). See
/memories/session/plan.md for the full design. This layer is default-off
and must be a byte-identical no-op vs Exp1 when its flags are absent/off.
"""

from scripts.conflict_episodes import (
    build_state_timeline,
    state_value_at,
    apply_conflict_episode_layer,
)


def _violation(category, vtype, chapter_id, *entities):
    return {
        "category": category,
        "type": vtype,
        "event_id": f"e{chapter_id}",
        "entities": list(entities),
        "args": [category, vtype, f"e{chapter_id}", *entities],
    }


def _signature_fn(v):
    return (v["category"], v["type"]) + tuple(v.get("entities", []))


def _extraction(chapter, characters=None, items=None, relationships=None):
    return {
        "chapter": chapter,
        "extraction": {
            "entities": {
                "characters": characters or [],
                "items": items or [],
                "relationships": relationships or [],
            }
        },
    }


class TestStateTimeline:
    def test_state_value_at_returns_most_recent_at_or_before_chapter(self):
        extractions = [
            _extraction(1, characters=[{"id": "harry", "state": "alive"}]),
            _extraction(3, characters=[{"id": "harry", "state": "dead"}]),
        ]
        timeline = build_state_timeline(extractions)
        key = ("character_state", "harry")
        assert state_value_at(timeline, key, 1) == "alive"
        assert state_value_at(timeline, key, 2) == "alive"
        assert state_value_at(timeline, key, 3) == "dead"
        assert state_value_at(timeline, key, 0) is None


class TestGroupingIsNoOp:
    def test_multi_violation_single_episode_all_retained_when_lifecycle_off(self):
        """Experiment B: --no-episode-lifecycle => grouping only, no
        suppression -- must be a no-op vs Exp1 (all candidates retained)."""
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_violation("causality", "interacting_with_dead", 12, "x")],
        }
        extractions = [_extraction(c) for c in (10, 11, 12)]
        new_violations, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
            use_episode_lifecycle=False,
        )
        total_before = sum(len(v) for v in chapter_violations.values())
        total_after = sum(len(v) for v in new_violations.values())
        assert total_after == total_before
        assert stats["final_candidates"] == total_before


class TestUnrelatedEntitiesSeparateEpisodes:
    def test_unrelated_candidates_are_separate_episodes(self):
        chapter_violations = {
            1: [_violation("emotional", "relationship_action_mismatch", 1, "harry", "ron")],
            2: [_violation("emotional", "relationship_action_mismatch", 2, "bella", "edward")],
        }
        extractions = [_extraction(1), _extraction(2)]
        _, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert candidates[0].component_id != candidates[1].component_id
        assert stats["n_episodes"] == 2
        # No state backing for either -> both must remain PRIMARY (never
        # suppressed without positive evidence).
        assert stats["final_candidates"] == 2


class TestBreakpointPreservedAsPrimary:
    def test_breakpoint_candidate_is_primary(self):
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
        }
        extractions = [_extraction(10), _extraction(11)]
        _, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        by_chapter = {c.chapter: c for c in candidates}
        assert by_chapter[10].index in [e.primary_candidate_id for e in episodes]


class TestSupportingWithoutStateBacking:
    def test_repeated_violation_with_no_state_evidence_is_never_suppressed(self):
        """No character/item state is ever recorded for entity 'x' in any
        chapter's extraction -- there is no positive evidence available to
        call downstream repeats "the same unresolved conflict", so nothing
        may be demoted to SUPPORTING (recall safety)."""
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_violation("causality", "interacting_with_dead", 12, "x")],
        }
        extractions = [_extraction(c) for c in (10, 11, 12)]
        new_violations, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["n_supporting"] == 0
        assert stats["final_candidates"] == 3


class TestLaterManifestationBecomesSupporting:
    def test_unchanged_anchor_state_is_supporting(self):
        """Character state stays 'dead' throughout -- the breakpoint
        establishes the anchor; downstream candidates whose only shared
        anchor key is unchanged become SUPPORTING."""
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_violation("causality", "interacting_with_dead", 12, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "dead"}]),
            _extraction(12, characters=[{"id": "x", "state": "dead"}]),
        ]
        new_violations, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["n_supporting"] == 2
        assert stats["final_candidates"] == 1


class TestNewContradictionDetected:
    def test_changed_anchor_state_is_new_episode(self):
        """Character's state actually changes (dead -> alive -> dead) --
        the second and third occurrences are materially distinct
        contradictions, not consequences of the first."""
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "alive"}]),
        ]
        # Isolate the new-contradiction-detection mechanism from the
        # resolution-tracking one (both would otherwise fire on the same
        # state change; resolution-tracking runs first in the pipeline).
        new_violations, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
            use_resolution_tracking=False,
        )
        assert stats["n_new_episode"] == 1
        assert stats["final_candidates"] == 2


class TestResolutionSplitsEpisodes:
    def test_resolution_starts_new_episode(self):
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_violation("causality", "interacting_with_dead", 12, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "dead"}]),
            _extraction(12, characters=[{"id": "x", "state": "alive"}]),
        ]
        new_violations, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["n_episodes"] >= 2
        assert any(e.lifecycle in ("RESOLVED",) for e in episodes)


class TestUnresolvedStaysInEpisode:
    def test_unresolved_conflict_all_supporting_after_breakpoint(self):
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "dead"}]),
        ]
        _, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["n_episodes"] == 1
        assert episodes[0].lifecycle == "ACTIVE"


class TestNoRuleNameEquality:
    def test_different_rule_types_same_unchanged_state_still_supporting(self):
        """Two DIFFERENT violation types about the same entity, whose
        shared anchor state never changes, must still classify as
        SUPPORTING -- proves classification is state-based, not
        type-string-based."""
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "some_other_dead_related_rule", 11, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "dead"}]),
        ]
        _, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["n_supporting"] == 1
        assert stats["final_candidates"] == 1


class TestUniqueCandidateSurvives:
    def test_singleton_candidate_always_primary(self):
        chapter_violations = {
            5: [_violation("temporal", "some_rule", 5, "solo")],
        }
        extractions = [_extraction(5)]
        _, candidates, episodes, stats = apply_conflict_episode_layer(
            "story", chapter_violations, extractions, _signature_fn,
        )
        assert stats["final_candidates"] == 1


class TestDeterminism:
    def test_same_input_same_output(self):
        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
            12: [_violation("causality", "interacting_with_dead", 12, "x")],
        }
        extractions = [
            _extraction(10, characters=[{"id": "x", "state": "dead"}]),
            _extraction(11, characters=[{"id": "x", "state": "dead"}]),
            _extraction(12, characters=[{"id": "x", "state": "dead"}]),
        ]
        r1 = apply_conflict_episode_layer("story", chapter_violations, extractions, _signature_fn)
        r2 = apply_conflict_episode_layer("story", chapter_violations, extractions, _signature_fn)
        assert r1[3] == r2[3]  # stats identical


class TestExp1UnchangedWhenFlagAbsent:
    def test_precision_layer_module_not_mutated(self):
        """Exp1's own apply_precision_layer must remain a pure no-op
        regardless of anything this new module does -- it's called
        independently and its RETAIN decisions are never read by the new
        layer (the new layer makes its own decision per candidate)."""
        from scripts.precision_layer import apply_precision_layer

        chapter_violations = {
            10: [_violation("causality", "interacting_with_dead", 10, "x")],
            11: [_violation("causality", "interacting_with_dead", 11, "x")],
        }
        new_v, _, _ = apply_precision_layer(
            "story", chapter_violations, [], _signature_fn,
        )
        total_before = sum(len(v) for v in chapter_violations.values())
        total_after = sum(len(v) for v in new_v.values())
        assert total_after == total_before
