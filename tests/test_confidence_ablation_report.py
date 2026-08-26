"""
Tests for scripts/confidence_ablation_report.py using synthetic caches
(no real engine evaluation -- keeps this fast and independent of the
OpenAI dataset being present on disk).
"""

import json

from scripts.confidence_ablation_report import (
    ConfigSpec,
    CONFIGS,
    BASELINE_CONTROL,
    _compute_per_category,
    _run_config,
    _check_pairing,
    _write_reports,
)
from scripts.kfold_experiment_runner_conflict_resolver import GroundTruthError, ALL_STORIES


def _gt(story, chapter, error_type):
    return GroundTruthError(
        chunk_id=chapter, chapter=f"{chapter:03d}.txt", error_type=error_type,
        description="", sentence="", story=story,
    )


def _violation(category, vtype, entities=None):
    entities = entities or []
    return {
        "category": category, "type": vtype, "event_id": "e1",
        "entities": entities, "args": [category, vtype, "e1", *entities],
    }


def _minimal_cache_and_gt():
    """One TP-eligible chapter (coherence) per story, everything else empty."""
    cache = {story: {1: [_violation("coherence", "contradictory_state")]} for story in ALL_STORIES}
    ground_truth = {story: [_gt(story, 1, "Basic Coherence")] for story in ALL_STORIES}
    return cache, ground_truth


class TestComputePerCategory:
    def test_tp_and_gt_counted_per_category(self):
        cache, ground_truth = _minimal_cache_and_gt()
        result = _compute_per_category(cache, ground_truth)
        assert result["coherence"]["gt"] == len(ALL_STORIES)
        assert result["coherence"]["tp"] == len(ALL_STORIES)
        assert result["emotional"]["gt"] == 0

    def test_total_row_aggregates_all_categories(self):
        cache, ground_truth = _minimal_cache_and_gt()
        result = _compute_per_category(cache, ground_truth)
        assert result["total"]["gt"] == len(ALL_STORIES)
        assert result["total"]["tp"] == len(ALL_STORIES)


class TestRunConfig:
    def test_baseline_config_without_gate_is_reference_status(self):
        cache, ground_truth = _minimal_cache_and_gt()
        modified_by_story = {story: [] for story in ALL_STORIES}
        original_by_story = {story: [] for story in ALL_STORIES}
        spec = ConfigSpec("A_baseline", use_confidence=False)
        result, decisions = _run_config(spec, cache, modified_by_story, original_by_story, ground_truth)
        assert decisions == []
        assert result["tp"] == len(ALL_STORIES)
        # No tp_gate/recall_gate passed -- _run_config can't judge
        # acceptance on its own; main() supplies the gate from A_baseline's
        # own observed result. See test_gate_rejects_low_recall_configuration
        # for the gated path.
        assert result["gate_pass"] is None
        assert result["status"] == "REFERENCE"

    def test_annotate_config_produces_decisions_but_no_metric_change(self):
        cache, ground_truth = _minimal_cache_and_gt()
        modified_by_story = {story: [] for story in ALL_STORIES}
        original_by_story = {story: [] for story in ALL_STORIES}
        baseline_spec = ConfigSpec("A_baseline", use_confidence=False)
        annotate_spec = ConfigSpec("B_tiers_annotate", use_confidence=True, policy="annotate")
        baseline_result, _ = _run_config(baseline_spec, cache, modified_by_story, original_by_story, ground_truth)
        annotate_result, decisions = _run_config(annotate_spec, cache, modified_by_story, original_by_story, ground_truth)
        assert len(decisions) == len(ALL_STORIES)
        assert annotate_result["tp"] == baseline_result["tp"]
        assert annotate_result["fp"] == baseline_result["fp"]
        assert annotate_result["fn"] == baseline_result["fn"]

    def test_gate_rejects_low_recall_configuration(self):
        # Absence-profile-only candidates (chekhov_gun) with no ground truth
        # match -- support-only will suppress them all, driving recall to 0.
        cache = {story: {1: [_violation("causality", "chekhov_gun", ["item"])]} for story in ALL_STORIES}
        ground_truth = {story: [_gt(story, 1, "Causality")] for story in ALL_STORIES}
        modified_by_story = {story: [] for story in ALL_STORIES}
        original_by_story = {story: [] for story in ALL_STORIES}
        spec = ConfigSpec("C_tiers_support_only", use_confidence=True, policy="support-only")
        result, _ = _run_config(
            spec, cache, modified_by_story, original_by_story, ground_truth,
            tp_gate=len(ALL_STORIES), recall_gate=1.0,
        )
        assert result["status"] == "REJECTED"
        assert result["micro_recall"] < 1.0


class TestPairingCheck:
    def test_missing_original_chapter_is_reported(self):
        modified_by_story = {ALL_STORIES[0]: [{"chapter": 5}], **{s: [] for s in ALL_STORIES[1:]}}
        original_by_story = {s: [] for s in ALL_STORIES}
        warnings = _check_pairing(modified_by_story, original_by_story)
        assert any(ALL_STORIES[0] in w for w in warnings)

    def test_full_coverage_has_no_warnings(self):
        modified_by_story = {s: [{"chapter": 1}] for s in ALL_STORIES}
        original_by_story = {s: [{"chapter": 1}] for s in ALL_STORIES}
        assert _check_pairing(modified_by_story, original_by_story) == []


class TestConfigsDefinition:
    def test_configs_defined(self):
        assert len(CONFIGS) == 9

    def test_first_config_is_baseline_without_confidence(self):
        assert CONFIGS[0].name == "A_baseline"
        assert CONFIGS[0].use_confidence is False

    def test_historical_reference_is_documented_not_asserted(self):
        # BASELINE_CONTROL is informational only now (the acceptance gate is
        # derived from each run's own A_baseline result, see _run_config) --
        # this just guards the constant's shape hasn't silently changed.
        assert set(BASELINE_CONTROL) == {"candidates", "tp", "fp", "fn"}


class TestWriteReports:
    def test_writes_all_expected_files(self, tmp_path):
        cache, ground_truth = _minimal_cache_and_gt()
        modified_by_story = {story: [] for story in ALL_STORIES}
        original_by_story = {story: [] for story in ALL_STORIES}
        results = []
        all_decisions = []
        for spec in CONFIGS[:2]:
            result, decisions = _run_config(spec, cache, modified_by_story, original_by_story, ground_truth)
            results.append(result)
            all_decisions.extend(decisions)

        _write_reports(tmp_path, results, all_decisions, warnings=[])

        for filename in (
            "ablation_summary.json", "candidate_decisions.jsonl",
            "per_story.csv", "per_category.csv", "per_rule.csv", "REPORT.md",
        ):
            assert (tmp_path / filename).exists()

        with open(tmp_path / "ablation_summary.json", encoding="utf-8") as f:
            summary = json.load(f)
        assert summary["configurations"][0]["config"] == "A_baseline"
        assert "delta_vs_baseline" in summary["configurations"][1]
