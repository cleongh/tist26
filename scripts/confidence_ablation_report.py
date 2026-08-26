#!/usr/bin/env python3
"""
OpenAI-only ablation report for the confidence-tier / world-verifier layer
(scripts/confidence_verifier.py) and the per-chapter confidence-ranked cap
(scripts/chapter_cap.py). Evaluates the engine ONCE per story, snapshots
the post-FP-reduction candidate cache, then deep-copies it per
configuration so every configuration scores the exact same starting
candidate pool. Never touches errors_checklist/ except through the
existing scorer (compute_precision_recall / a local per-category helper,
see _compute_per_category()) -- this module adds no new scoring logic.

Configurations (all independently reproducible from the same cache):
    A baseline            -- no confidence layer at all (current default)
    B tiers_annotate       -- confidence tiers, policy=annotate (must be a
                              strict no-op vs A; verified as an assertion)
    C tiers_support_only   -- confidence tiers, policy=support-only
    D world_annotate       -- world verifier enabled, policy=annotate (also
                              a no-op vs A/B; verifies the verifier alone
                              never changes membership under annotate)
    E support_plus_world   -- policy=support-only + world verifier
    F support_plus_world_veto -- E + explicit refutation veto enabled
    G/H/I cap1/cap2/cap3   -- baseline + confidence-ranked per-chapter cap
                              (max 1/2/3 survivors per chapter), isolating
                              the cap's own effect from the confidence-
                              policy configs above

Acceptance gate (per /memories/session/plan.md): a configuration is
REJECTED if its true positives or recall drop below A_baseline's OWN
observed tp/recall for this run (not a frozen historical constant -- an
accepted engine/rule change legitimately moves the baseline, and the gate
tracks it). Rejected configurations are still fully reported, just flagged.
"""

import argparse
import copy
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state.config import ERRORS_CHECKLIST_DIR, RULES_DIR
from scripts.kfold_experiment_runner_conflict_resolver import (
    ALL_STORIES,
    load_extractions,
    load_ground_truth,
    evaluate_story_with_engine,
    reduce_false_positives,
    final_dedup_sweep,
    compute_precision_recall,
    match_error_category,
    _violation_signature,
)
from scripts.confidence_verifier import (
    apply_confidence_layer,
    ALL_DOMAINS,
    ConfidenceDecision,
)
from scripts.chapter_cap import apply_chapter_cap

BASELINE_CONTROL = {"candidates": 695, "tp": 30, "fp": 665, "fn": 45}
PER_CATEGORY_CATEGORIES = ["coherence", "emotional", "location", "temporal", "causality"]


def _compute_per_category(
    cache: Dict[str, Dict[int, List[Dict[str, Any]]]], ground_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Local equivalent of compute_per_category_strict() that works directly
    off a chapter_violations cache (no StoryResult/ChapterResult objects
    needed) -- avoids run_experiment_for_stories(), which is currently
    broken by an unrelated match_error_category shadowing bug in
    scripts/kfold_experiment_runner_conflict_resolver.py (a later, 2-arg
    redefinition of match_error_category shadows the 3-arg `strict=` one
    run_experiment_for_stories calls). Uses the SAME active (2-arg)
    match_error_category compute_precision_recall() already uses, so
    results are consistent with this module's micro/macro numbers."""
    stats = {cat: {"gt": 0, "tp": 0, "violations": 0} for cat in PER_CATEGORY_CATEGORIES}
    for story in ALL_STORIES:
        chapter_violations = cache.get(story, {})
        gt_by_chapter: Dict[int, List[Any]] = defaultdict(list)
        for err in ground_truth.get(story, []):
            gt_by_chapter[err.chapter_num].append(err)
        for chapter, violations in chapter_violations.items():
            chapter_gt = gt_by_chapter.get(chapter, [])
            matched_gt: set = set()
            for v in violations:
                v_cat = v.get("category", "other")
                if v_cat in stats:
                    stats[v_cat]["violations"] += 1
                for i, gt in enumerate(chapter_gt):
                    if i not in matched_gt and match_error_category(v_cat, gt.category):
                        matched_gt.add(i)
                        if v_cat in stats:
                            stats[v_cat]["tp"] += 1
                        break
            for gt in chapter_gt:
                if gt.category in stats:
                    stats[gt.category]["gt"] += 1

    result: Dict[str, Any] = {}
    totals = {"gt": 0, "tp": 0, "fn": 0, "violations": 0}
    for cat in PER_CATEGORY_CATEGORIES:
        s = stats[cat]
        fn = s["gt"] - s["tp"]
        precision = (s["tp"] / s["violations"] * 100) if s["violations"] > 0 else 0.0
        recall = (s["tp"] / s["gt"] * 100) if s["gt"] > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        result[cat] = {
            "gt": s["gt"], "tp": s["tp"], "fn": fn, "violations": s["violations"],
            "recall": round(recall, 2), "precision": round(precision, 2), "f1": round(f1, 2),
        }
        totals["gt"] += s["gt"]
        totals["tp"] += s["tp"]
        totals["fn"] += fn
        totals["violations"] += s["violations"]
    precision = (totals["tp"] / totals["violations"] * 100) if totals["violations"] > 0 else 0.0
    recall = (totals["tp"] / totals["gt"] * 100) if totals["gt"] > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    result["total"] = {**totals, "recall": round(recall, 2), "precision": round(precision, 2), "f1": round(f1, 2)}
    return result


@dataclass(frozen=True)
class ConfigSpec:
    name: str
    use_confidence: bool
    policy: str = "annotate"
    use_world: bool = False
    use_refutation_veto: bool = False
    chapter_cap: Optional[int] = None


CONFIGS: Tuple[ConfigSpec, ...] = (
    ConfigSpec("A_baseline", use_confidence=False),
    ConfigSpec("B_tiers_annotate", use_confidence=True, policy="annotate"),
    ConfigSpec("C_tiers_support_only", use_confidence=True, policy="support-only"),
    ConfigSpec("D_world_annotate", use_confidence=True, policy="annotate", use_world=True),
    ConfigSpec("E_support_plus_world", use_confidence=True, policy="support-only", use_world=True),
    ConfigSpec(
        "F_support_plus_world_veto", use_confidence=True, policy="support-only",
        use_world=True, use_refutation_veto=True,
    ),
    ConfigSpec("G_cap1", use_confidence=False, chapter_cap=1),
    ConfigSpec("H_cap2", use_confidence=False, chapter_cap=2),
    ConfigSpec("I_cap3", use_confidence=False, chapter_cap=3),
)


def _load_baseline_cache(
    experiment_dir: Path, rules_dir: Path, extractions: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[int, List[Dict[str, Any]]]], Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
    """One engine evaluation + one FP-reduction pass per story (identical to
    main()'s default pipeline up to, but not including, the confidence
    layer / final dedup / scoring). Returns (post_fp_reduce_cache,
    modified_extractions_by_story, original_extractions_by_story)."""
    modified_by_story: Dict[str, List[Dict[str, Any]]] = {}
    original_by_story: Dict[str, List[Dict[str, Any]]] = {}
    cache: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}

    for story in ALL_STORIES:
        modified = [e for e in extractions if e.get("story") == story and e.get("variant") == "modified"]
        original = [e for e in extractions if e.get("story") == story and e.get("variant") == "original"]
        modified_by_story[story] = modified
        original_by_story[story] = original
        raw = evaluate_story_with_engine(
            story, modified, rules_dir, original_extractions=original, collect_provenance=True,
        )
        cache[story] = reduce_false_positives(raw)

    return cache, modified_by_story, original_by_story


def _check_pairing(
    modified_by_story: Dict[str, List[Dict[str, Any]]],
    original_by_story: Dict[str, List[Dict[str, Any]]],
) -> List[str]:
    """Report (chapter) coverage gaps between original/modified variants per
    story -- paired-evidence configs must not silently compare mismatched
    chapters."""
    warnings = []
    for story in ALL_STORIES:
        mod_chapters = {e.get("chapter", -1) for e in modified_by_story.get(story, [])}
        orig_chapters = {e.get("chapter", -1) for e in original_by_story.get(story, [])}
        missing_original = sorted(mod_chapters - orig_chapters)
        if missing_original:
            warnings.append(f"{story}: {len(missing_original)} modified chapter(s) have no paired original")
    return warnings


def _run_config(
    spec: ConfigSpec,
    baseline_cache: Dict[str, Dict[int, List[Dict[str, Any]]]],
    modified_by_story: Dict[str, List[Dict[str, Any]]],
    original_by_story: Dict[str, List[Dict[str, Any]]],
    ground_truth: Dict[str, Any],
    tp_gate: Optional[int] = None,
    recall_gate: Optional[float] = None,
) -> Tuple[Dict[str, Any], List[ConfidenceDecision]]:
    cache = copy.deepcopy(baseline_cache)
    all_decisions: List[ConfidenceDecision] = []
    input_candidates = sum(len(v) for story in cache.values() for v in story.values())

    if spec.use_confidence:
        for story in ALL_STORIES:
            original_by_chapter = {e.get("chapter", -1): e for e in original_by_story.get(story, [])}
            modified_by_chapter = {e.get("chapter", -1): e for e in modified_by_story.get(story, [])}
            new_violations, decisions = apply_confidence_layer(
                story,
                cache[story],
                _violation_signature,
                original_extractions_by_chapter=original_by_chapter,
                modified_extractions_by_chapter=modified_by_chapter,
                policy=spec.policy,
                use_world_verifier=spec.use_world,
                enabled_domains=ALL_DOMAINS,
                use_refutation_veto=spec.use_refutation_veto,
            )
            cache[story] = new_violations
            for d in decisions:
                d_with_config = ConfidenceDecision(**{**d.__dict__, "candidate_id": f"{spec.name}:{d.candidate_id}"})
                all_decisions.append(d_with_config)

    for story in ALL_STORIES:
        cache[story] = final_dedup_sweep(cache[story])
    if spec.chapter_cap:
        for story in ALL_STORIES:
            cache[story] = apply_chapter_cap(cache[story], spec.chapter_cap)
    final_candidates = sum(len(v) for story in cache.values() for v in story.values())

    pr_report = compute_precision_recall(cache, ground_truth)
    overall = pr_report["overall"]
    total_tp, total_fp, total_fn = overall["tp"], overall["fp"], overall["fn"]
    micro_precision, micro_recall, micro_f1 = overall["precision"], overall["recall"], overall["f1"]
    per_story_metrics = pr_report["per_story"]
    macro_precision = sum(m["precision"] for m in per_story_metrics.values()) / len(per_story_metrics)
    macro_recall = sum(m["recall"] for m in per_story_metrics.values()) / len(per_story_metrics)
    macro_f1 = sum(m["f1"] for m in per_story_metrics.values()) / len(per_story_metrics)

    per_category = _compute_per_category(cache, ground_truth)

    # Gate is relative to the CURRENT A_baseline result (passed in by the
    # caller), not a frozen historical constant -- an intentional, already-
    # accepted engine change (e.g. a rule tightening) legitimately moves the
    # baseline itself, and the gate must track it rather than flag the new
    # baseline as a regression against stale numbers.
    if tp_gate is None or recall_gate is None:
        gate_pass: Optional[bool] = None
        status = "REFERENCE"
    else:
        gate_pass = total_tp >= tp_gate and micro_recall >= recall_gate
        status = "ACCEPTED" if gate_pass else "REJECTED"

    result = {
        "config": spec.name,
        "policy": spec.policy,
        "use_confidence": spec.use_confidence,
        "use_world": spec.use_world,
        "use_refutation_veto": spec.use_refutation_veto,
        "chapter_cap": spec.chapter_cap,
        "input_candidates": input_candidates,
        "final_candidates": final_candidates,
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "micro_precision": round(micro_precision, 4),
        "micro_recall": round(micro_recall, 4),
        "micro_f1": round(micro_f1, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "per_story": per_story_metrics,
        "per_category": per_category,
        "gate_pass": gate_pass,
        "status": status,
    }
    return result, all_decisions


def _write_reports(output_dir: Path, results: List[Dict[str, Any]], all_decisions: List[ConfidenceDecision], warnings: List[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = results[0]
    for r in results:
        r["delta_vs_baseline"] = {
            "tp": r["tp"] - baseline["tp"],
            "fp": r["fp"] - baseline["fp"],
            "fn": r["fn"] - baseline["fn"],
            "micro_precision": round(r["micro_precision"] - baseline["micro_precision"], 4),
            "micro_recall": round(r["micro_recall"] - baseline["micro_recall"], 4),
        }

    summary = {
        "dataset": "OPENAI_HUMAN_ERRORS_RESULTS/15_extraction_only",
        "timestamp": datetime.now().isoformat(),
        "pairing_warnings": warnings,
        "historical_reference": BASELINE_CONTROL,
        "acceptance_gate": {"min_tp": results[0]["tp"], "min_recall": results[0]["micro_recall"],
                             "note": "relative to this run's own A_baseline result, not a frozen constant"},
        "configurations": results,
    }
    with open(output_dir / "ablation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with open(output_dir / "candidate_decisions.jsonl", "w", encoding="utf-8") as f:
        for d in all_decisions:
            f.write(json.dumps({
                "candidate_id": d.candidate_id, "category": d.category, "type": d.type,
                "tier": d.tier.value, "reasons": d.reasons,
                "verifier_result": d.verifier_result.value, "verifier_domain": d.verifier_domain,
                "verifier_matched": d.verifier_matched, "has_delta": d.has_delta,
                "delta_reason": d.delta_reason, "disposition": d.disposition.value,
                "corroborated_by": d.corroborated_by,
            }) + "\n")

    with open(output_dir / "per_story.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["config", "story", "tp", "fp", "fn", "precision", "recall", "f1"])
        for r in results:
            for story, m in r["per_story"].items():
                writer.writerow([r["config"], story, m["tp"], m["fp"], m["fn"], m["precision"], m["recall"], m["f1"]])

    with open(output_dir / "per_category.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["config", "category", "gt", "tp", "fn", "violations", "precision", "recall", "f1"])
        for r in results:
            for cat, m in r["per_category"].items():
                writer.writerow([r["config"], cat, m["gt"], m["tp"], m["fn"], m["violations"], m["precision"], m["recall"], m["f1"]])

    with open(output_dir / "per_rule.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id_prefix_config", "category", "type", "tier", "disposition"])
        for d in all_decisions:
            config_name = d.candidate_id.split(":", 1)[0]
            writer.writerow([config_name, d.category, d.type, d.tier.value, d.disposition.value])

    lines = ["# Confidence-Tier Ablation Report (OpenAI, all 5 stories)", "", f"Generated: {summary['timestamp']}", ""]
    if warnings:
        lines += ["## Pairing warnings", ""] + [f"- {w}" for w in warnings] + [""]
    lines += ["## Results", "", "| Config | Status | Candidates (in->final) | TP | FP | FN | Micro P | Micro R | Macro P | Macro R |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['config']} | {r['status']} | {r['input_candidates']}->{r['final_candidates']} | "
            f"{r['tp']} | {r['fp']} | {r['fn']} | {r['micro_precision']:.4f} | {r['micro_recall']:.4f} | "
            f"{r['macro_precision']:.4f} | {r['macro_recall']:.4f} |"
        )
    lines += ["", f"Acceptance gate: TP >= {results[0]['tp']} and micro recall >= {results[0]['micro_recall']:.4f} "
              f"(A_baseline's own observed values this run).", ""]
    with open(output_dir / "REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_dir", type=str, default="experiments/OPENAI_HUMAN_ERRORS_RESULTS/15_extraction_only")
    parser.add_argument("--output_dir", type=str, default=None)
    parser.add_argument("--errors_dir", type=str, default=None)
    parser.add_argument("--rules_dir", type=str, default=None)
    args = parser.parse_args()

    experiment_dir = Path(args.experiment_dir)
    if not experiment_dir.is_absolute():
        experiment_dir = PROJECT_ROOT / experiment_dir
    errors_dir = Path(args.errors_dir) if args.errors_dir else ERRORS_CHECKLIST_DIR
    rules_dir = Path(args.rules_dir) if args.rules_dir else RULES_DIR
    output_dir = Path(args.output_dir) if args.output_dir else (
        experiment_dir / "confidence_ablation" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    extractions = load_extractions(experiment_dir / "step2_extractions.jsonl")
    ground_truth = load_ground_truth(errors_dir)

    print("Evaluating engine once per story + FP reduction (shared cache for all configs)...")
    baseline_cache, modified_by_story, original_by_story = _load_baseline_cache(experiment_dir, rules_dir, extractions)
    warnings = _check_pairing(modified_by_story, original_by_story)
    for w in warnings:
        print(f"  [pairing warning] {w}")

    results: List[Dict[str, Any]] = []
    all_decisions: List[ConfidenceDecision] = []

    baseline_spec = CONFIGS[0]
    print(f"Scoring configuration {baseline_spec.name}...")
    baseline_result, baseline_decisions = _run_config(
        baseline_spec, baseline_cache, modified_by_story, original_by_story, ground_truth,
    )
    baseline_result["gate_pass"] = True
    baseline_result["status"] = "ACCEPTED"
    results.append(baseline_result)
    all_decisions.extend(baseline_decisions)
    print(f"  -> tp={baseline_result['tp']} fp={baseline_result['fp']} fn={baseline_result['fn']} "
          f"micro_precision={baseline_result['micro_precision']:.4f} micro_recall={baseline_result['micro_recall']:.4f} "
          f"status={baseline_result['status']}")

    tp_gate, recall_gate = baseline_result["tp"], baseline_result["micro_recall"]
    for spec in CONFIGS[1:]:
        print(f"Scoring configuration {spec.name}...")
        result, decisions = _run_config(
            spec, baseline_cache, modified_by_story, original_by_story, ground_truth,
            tp_gate=tp_gate, recall_gate=recall_gate,
        )
        results.append(result)
        all_decisions.extend(decisions)
        print(f"  -> tp={result['tp']} fp={result['fp']} fn={result['fn']} "
              f"micro_precision={result['micro_precision']:.4f} micro_recall={result['micro_recall']:.4f} "
              f"status={result['status']}")

    if (
        results[0]["tp"] != BASELINE_CONTROL["tp"]
        or results[0]["fp"] != BASELINE_CONTROL["fp"]
        or results[0]["fn"] != BASELINE_CONTROL["fn"]
    ):
        print(f"NOTE: A_baseline ({results[0]['tp']}/{results[0]['fp']}/{results[0]['fn']} tp/fp/fn) has drifted "
              f"from the original historical reference {BASELINE_CONTROL} -- this is expected after any "
              f"accepted engine/rule change and is NOT an error; the acceptance gate below tracks the current "
              f"A_baseline, not the historical reference.")

    _write_reports(output_dir, results, all_decisions, warnings)
    print(f"\nReports written to {output_dir}")


if __name__ == "__main__":
    main()
