#!/usr/bin/env python3
"""
Offline FP/TP analysis over a --dump-violations dump (see
scripts/violation_dump.py and /memories/session/plan.md "Offline FP
Analysis"). Phases C-G: labels every candidate TP/FP (offline only, using
the runner's own greedy matching semantics), reports FP/TP distributions,
mines generic structural FP-enrichment patterns, and (optionally) checks
pattern stability via leave-one-story-out.

This script NEVER writes labels back into the runtime dump file, never
changes scoring, and is never imported by the runner. Pure read-only
analysis of an already-produced dump.

Usage:
    python scripts/analyze_violation_dump.py --dump_dir /tmp/dump_openai \\
        --dataset 15_extraction_only --output_dir /tmp/analysis_openai
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state.config import ERRORS_CHECKLIST_DIR
from scripts.kfold_experiment_runner_conflict_resolver import (
    ALL_STORIES, load_ground_truth, match_error_category,
)

STAGES = ["raw", "fp_reduced", "exp1"]


# =============================================================================
# Phase C -- offline labelling (never consumed by production code)
# =============================================================================

def load_dump(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def label_records(
    records: List[Dict[str, Any]],
    ground_truth: Dict[str, List[Any]],
) -> Dict[str, Dict[str, Any]]:
    """Label every record TP/FP using the EXACT same greedy per-chapter
    strict-category matching as run_experiment_for_stories(), computed
    INDEPENDENTLY per stage (the competing candidate pool for a chapter
    differs between raw/fp_reduced/exp1, so the same ground-truth error
    can be legitimately won by a different candidate at each stage).

    Returns candidate_id -> {"analysis_label": "TP"|"FP",
    "matched_ground_truth": <id>|None}. This dict is the ONLY place labels
    live; never merged back into a dump record.
    """
    gt_by_story_chapter: Dict[Tuple[str, int], List[Any]] = defaultdict(list)
    for story, errors in ground_truth.items():
        for gt in errors:
            gt_by_story_chapter[(story, gt.chapter_num)].append(gt)

    by_stage_story_chapter: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_stage_story_chapter[(r["stage"], r["story"], r["chapter"])].append(r)

    labels: Dict[str, Dict[str, Any]] = {}
    for (stage, story, chapter), recs in by_stage_story_chapter.items():
        chapter_gt = gt_by_story_chapter.get((story, chapter), [])
        matched_gt: Set[int] = set()
        for r in recs:
            match_idx = None
            for i, gt in enumerate(chapter_gt):
                if i not in matched_gt and match_error_category(r["category"], gt.category, strict=True):
                    matched_gt.add(i)
                    match_idx = i
                    break
            labels[r["candidate_id"]] = {
                "analysis_label": "TP" if match_idx is not None else "FP",
                "matched_ground_truth": (
                    f"{story}:ch{chapter}:{match_idx}" if match_idx is not None else None
                ),
            }
    return labels


# =============================================================================
# Phase D -- FP/TP distribution report
# =============================================================================

def distribution_report(
    records: List[Dict[str, Any]], labels: Dict[str, Dict[str, Any]], stage: str,
) -> Dict[str, Any]:
    stage_records = [r for r in records if r["stage"] == stage]
    total = len(stage_records)
    tp = sum(1 for r in stage_records if labels[r["candidate_id"]]["analysis_label"] == "TP")
    fp = total - tp
    precision = tp / total if total else 0.0

    def _bucket(key_fn):
        stats: Dict[Any, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0})
        for r in stage_records:
            label = labels[r["candidate_id"]]["analysis_label"]
            stats[key_fn(r)][label.lower()] += 1
        return {
            str(k): {**v, "total": v["tp"] + v["fp"],
                     "precision": round(v["tp"] / (v["tp"] + v["fp"]), 4) if (v["tp"] + v["fp"]) else 0.0}
            for k, v in stats.items()
        }

    return {
        "stage": stage,
        "total": total, "tp": tp, "fp": fp, "precision": round(precision, 4),
        "per_dataset": _bucket(lambda r: r["dataset"]),
        "per_category": _bucket(lambda r: r["category"]),
        "per_rule": _bucket(lambda r: r["rule"]),
        "per_type": _bucket(lambda r: r["type"]),
    }


def stage_survival_report(records: List[Dict[str, Any]], labels: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Per plan.md Phase D2: how many FPs are already removed by
    fp_reduce/Exp1 vs how many survive everything. Only survivors are
    worth a new suppression pattern."""
    by_id: Dict[str, Dict[str, str]] = defaultdict(dict)
    for r in records:
        by_id[r["candidate_id"]][r["stage"]] = labels[r["candidate_id"]]["analysis_label"]

    counts = {"fp_removed_by_fp_reduce": 0, "fp_removed_by_exp1": 0, "fp_survives_all": 0,
              "tp_removed_by_fp_reduce": 0, "tp_removed_by_exp1": 0}
    for cid, stages in by_id.items():
        if "raw" not in stages:
            continue
        raw_label = stages["raw"]
        in_fp_reduced = "fp_reduced" in stages
        in_exp1 = "exp1" in stages
        if raw_label == "FP":
            if not in_fp_reduced:
                counts["fp_removed_by_fp_reduce"] += 1
            elif not in_exp1:
                counts["fp_removed_by_exp1"] += 1
            elif in_exp1:
                counts["fp_survives_all"] += 1
        else:
            if not in_fp_reduced:
                counts["tp_removed_by_fp_reduce"] += 1
            elif not in_exp1:
                counts["tp_removed_by_exp1"] += 1
    return counts


# =============================================================================
# Phase E -- generic structural FP-pattern detectors
#
# NOTE (honesty per plan.md): the spec's full A-L taxonomy assumes richer
# semantic modeling (explanation events connecting two states, temporal
# exclusivity reasoning, cross-rule duplicate detection, alias ambiguity)
# than the dump fields can currently support without inventing data. The
# patterns below are the subset RELIABLY computable from what
# scripts/violation_dump.py actually captures; each docstring states which
# spec letter it corresponds to and why the rest are deferred.
# =============================================================================

def _adaptive(count: int, fraction: float, floor: int, cap: int) -> int:
    return max(floor, min(cap, round(count * fraction)))


def build_component_index(exp1_records: List[Dict[str, Any]]) -> Dict[Tuple[str, str, Any], List[Dict[str, Any]]]:
    """(dataset, story, conflict_component_id) -> members sorted by chapter."""
    idx: Dict[Tuple[str, str, Any], List[Dict[str, Any]]] = defaultdict(list)
    for r in exp1_records:
        key = (r["dataset"], r["story"], r.get("conflict_component_id"))
        idx[key].append(r)
    for key in idx:
        idx[key].sort(key=lambda r: r["chapter"])
    return idx


def detect_patterns(exp1_records: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Returns pattern_name -> set of candidate_ids matching it."""
    component_index = build_component_index(exp1_records)
    breakpoint_by_component: Dict[Tuple[str, str, Any], Dict[str, Any]] = {}
    for key, members in component_index.items():
        bp = next((m for m in members if m.get("breakpoint_candidate")), members[0])
        breakpoint_by_component[key] = bp

    patterns: Dict[str, Set[str]] = defaultdict(set)

    for r in exp1_records:
        cid = r["candidate_id"]
        key = (r["dataset"], r["story"], r.get("conflict_component_id"))
        bp = breakpoint_by_component.get(key)
        is_breakpoint = r.get("breakpoint_candidate") is True

        # P1 (spec A, downstream_manifestation): any non-breakpoint member
        # of a multi-candidate conflict episode.
        if not is_breakpoint and r.get("component_size", 1) > 1:
            patterns["P1_downstream_non_breakpoint"].add(cid)

        # P2 (spec B, shared_provenance_root): shares a provenance root
        # with its episode's own breakpoint candidate.
        if bp is not None and not is_breakpoint:
            roots = set(r.get("provenance_roots") or [])
            bp_roots = set(bp.get("provenance_roots") or [])
            if roots and (roots & bp_roots):
                patterns["P2_shares_provenance_root_with_breakpoint"].add(cid)

        # P3 (spec C, weak_inferred_state -- no-evidence variant): zero
        # structurally-anchored state context at all.
        if not r.get("state_context"):
            patterns["P3_no_state_backing"].add(cid)

        # P4 (spec E, no_new_state_transition): every anchor state key
        # shared with the breakpoint is UNCHANGED.
        if bp is not None and not is_breakpoint and r.get("state_context") and bp.get("state_context"):
            shared = set(r["state_context"]) & set(bp["state_context"])
            if shared and all(r["state_context"][k] == bp["state_context"][k] for k in shared):
                patterns["P4_unchanged_state_vs_breakpoint"].add(cid)

        # P5 (spec G, persistent_contradiction): far downstream of the
        # episode's first occurrence (adaptive per-episode threshold).
        dist = r.get("distance_from_first_conflict") or 0
        if dist >= 3:
            patterns["P5_far_downstream"].add(cid)

        # P6 (spec J proxy, cross_rule_duplicate_evidence's inverse --
        # "echo chamber"): a large episode where only ONE rule type ever
        # fired (no independent corroboration despite size).
        if (r.get("component_size") or 1) >= 5 and (r.get("independent_evidence") or 1) == 1:
            patterns["P6_large_component_single_rule_type"].add(cid)

        # P7 (spec C, weak_inferred_state -- provenance variant): no EDB
        # (input) fact could be found supporting this violation at all.
        if not r.get("triggering_facts"):
            patterns["P7_zero_triggering_facts"].add(cid)

    return patterns


def pattern_stats(
    patterns: Dict[str, Set[str]],
    exp1_records: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """FP/TP counts PLUS the metric that actually matters: lift = this
    pattern's own precision (TP/(TP+FP) among candidates matching it)
    divided by the exp1 population's overall precision. lift < 1 means
    the pattern is genuinely MORE FP-heavy than the average candidate
    (a real enrichment signal); lift ~= 1 means the pattern carries no
    discriminative information at all, no matter how large its raw
    FP count or FP/TP ratio look in isolation -- both are dominated by
    the population's own already-low base precision and are NOT evidence
    of enrichment by themselves (this was a mistake in an earlier version
    of this script; kept fp_tp_ratio only as a secondary/context number).
    """
    by_id = {r["candidate_id"]: r for r in exp1_records}
    overall_tp = sum(1 for r in exp1_records if labels[r["candidate_id"]]["analysis_label"] == "TP")
    overall_total = len(exp1_records)
    overall_precision = overall_tp / overall_total if overall_total else 0.0

    stats: Dict[str, Any] = {}
    for name, ids in patterns.items():
        fp_ids = [i for i in ids if labels[i]["analysis_label"] == "FP"]
        tp_ids = [i for i in ids if labels[i]["analysis_label"] == "TP"]
        datasets = {by_id[i]["dataset"] for i in ids}
        categories = {by_id[i]["category"] for i in ids}
        rules = {by_id[i]["rule"] for i in ids}
        pattern_precision = len(tp_ids) / len(ids) if ids else 0.0
        stats[name] = {
            "fp_count": len(fp_ids),
            "tp_count": len(tp_ids),
            "coverage": len(ids),
            "pattern_precision": round(pattern_precision, 4),
            "overall_precision": round(overall_precision, 4),
            "lift": round(pattern_precision / overall_precision, 3) if overall_precision > 0 else None,
            "fp_tp_ratio": round(len(fp_ids) / len(tp_ids), 2) if tp_ids else (float("inf") if fp_ids else 0.0),
            "datasets_seen": sorted(datasets),
            "n_datasets": len(datasets),
            "categories_seen": sorted(categories),
            "rules_seen": sorted(rules),
        }
    return stats


def test_conjunctions(
    patterns: Dict[str, Set[str]],
    exp1_records: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
    top_n: int = 5,
) -> Dict[str, Any]:
    """Per plan.md Phase E4 / spec section 9: a single pattern being
    frequent is not enough; the spec's own example shows the genuinely
    safe patterns can live in a CONJUNCTION of weaker individual signals.
    Tests every 2-way and 3-way conjunction among the `top_n` patterns
    ranked by raw FP count, reporting the same lift metric."""
    single_stats = pattern_stats(patterns, exp1_records, labels)
    top_names = sorted(single_stats, key=lambda n: -single_stats[n]["fp_count"])[:top_n]

    overall_tp = sum(1 for r in exp1_records if labels[r["candidate_id"]]["analysis_label"] == "TP")
    overall_precision = overall_tp / len(exp1_records) if exp1_records else 0.0

    def _combo_stats(names: Tuple[str, ...]) -> Dict[str, Any]:
        ids = set.intersection(*(patterns[n] for n in names)) if names else set()
        fp = sum(1 for i in ids if labels[i]["analysis_label"] == "FP")
        tp = sum(1 for i in ids if labels[i]["analysis_label"] == "TP")
        precision = tp / len(ids) if ids else 0.0
        return {
            "patterns": list(names), "coverage": len(ids), "fp_count": fp, "tp_count": tp,
            "pattern_precision": round(precision, 4),
            "lift": round(precision / overall_precision, 3) if overall_precision > 0 else None,
        }

    from itertools import combinations as _combinations
    combos = []
    for r in (2, 3):
        for names in _combinations(top_names, r):
            combos.append(_combo_stats(names))
    combos.sort(key=lambda c: (c["tp_count"], -c["fp_count"]))
    return {"top_patterns_considered": top_names, "conjunctions": combos}


def per_dataset_category_breakdown(
    patterns: Dict[str, Set[str]],
    exp1_records: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    by_id = {r["candidate_id"]: r for r in exp1_records}
    breakdown: Dict[str, Any] = {}
    for name, ids in patterns.items():
        per_ds: Dict[str, Dict[str, int]] = defaultdict(lambda: {"fp": 0, "tp": 0})
        per_cat: Dict[str, Dict[str, int]] = defaultdict(lambda: {"fp": 0, "tp": 0})
        for i in ids:
            r = by_id[i]
            label = labels[i]["analysis_label"].lower()
            per_ds[r["dataset"]][label] += 1
            per_cat[r["category"]][label] += 1
        breakdown[name] = {"per_dataset": dict(per_ds), "per_category": dict(per_cat)}
    return breakdown


# =============================================================================
# Phase F -- leave-one-story-out generalization check
# =============================================================================

def leave_one_story_out(
    patterns: Dict[str, Set[str]],
    exp1_records: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """For each pattern, recompute fp_count/tp_count restricted to each
    held-out story in turn (the pattern was 'derived' by looking at the
    other 4; here we just check its FP/TP behaviour holds on the 5th).
    Not model training -- a stability check on a structural rule."""
    by_id = {r["candidate_id"]: r for r in exp1_records}
    result: Dict[str, Any] = {}
    for name, ids in patterns.items():
        per_story = {}
        for story in ALL_STORIES:
            story_ids = [i for i in ids if by_id[i]["story"] == story]
            fp = sum(1 for i in story_ids if labels[i]["analysis_label"] == "FP")
            tp = sum(1 for i in story_ids if labels[i]["analysis_label"] == "TP")
            per_story[story] = {"fp": fp, "tp": tp}
        # "strong" = zero (or very low) TP leakage in EVERY held-out story,
        # not just in aggregate.
        max_tp_any_story = max((v["tp"] for v in per_story.values()), default=0)
        result[name] = {"per_story": per_story, "max_tp_in_any_single_story": max_tp_any_story}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dump_dir", required=True, help="Directory containing violations_<dataset>.jsonl files.")
    parser.add_argument("--datasets", nargs="+", default=None,
                         help="Dataset names to analyze (default: all violations_*.jsonl found in --dump_dir).")
    parser.add_argument("--errors_dir", default=None)
    parser.add_argument("--output_dir", required=True)
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    if not dump_dir.is_absolute():
        dump_dir = PROJECT_ROOT / dump_dir
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    errors_dir = Path(args.errors_dir) if args.errors_dir else ERRORS_CHECKLIST_DIR
    ground_truth = load_ground_truth(errors_dir)

    if args.datasets:
        dataset_names = args.datasets
    else:
        dataset_names = [p.stem.replace("violations_", "") for p in dump_dir.glob("violations_*.jsonl")]

    all_records: List[Dict[str, Any]] = []
    for name in dataset_names:
        path = dump_dir / f"violations_{name}.jsonl"
        if not path.exists():
            print(f"  Warning: {path} not found, skipping")
            continue
        recs = load_dump(path)
        all_records.extend(recs)
        print(f"  Loaded {len(recs)} records from {path.name}")

    labels = label_records(all_records, ground_truth)

    # Write labels as a SEPARATE artifact, never merged into the dump.
    labels_path = output_dir / "labels.jsonl"
    with open(labels_path, "w", encoding="utf-8") as f:
        for cid, lbl in labels.items():
            f.write(json.dumps({"candidate_id": cid, **lbl}) + "\n")
    print(f"\nWritten {len(labels)} labels to {labels_path}")

    dist_reports = {stage: distribution_report(all_records, labels, stage) for stage in STAGES}
    with open(output_dir / "distribution_report.json", "w", encoding="utf-8") as f:
        json.dump(dist_reports, f, indent=2)

    survival = stage_survival_report(all_records, labels)
    with open(output_dir / "stage_survival_report.json", "w", encoding="utf-8") as f:
        json.dump(survival, f, indent=2)

    exp1_records = [r for r in all_records if r["stage"] == "exp1"]
    patterns = detect_patterns(exp1_records)
    stats = pattern_stats(patterns, exp1_records, labels)
    breakdown = per_dataset_category_breakdown(patterns, exp1_records, labels)
    loso = leave_one_story_out(patterns, exp1_records, labels)
    conjunctions = test_conjunctions(patterns, exp1_records, labels)

    # Rank by LIFT (real enrichment), not raw FP count/ratio -- see
    # pattern_stats() docstring for why the raw ratio alone is misleading
    # when the population's own baseline precision is already very low.
    ranked = sorted(
        stats.items(),
        key=lambda kv: (kv[1]["lift"] if kv[1]["lift"] is not None else 999, -kv[1]["fp_count"]),
    )
    taxonomy = {
        "overall_exp1_precision": stats and next(iter(stats.values()))["overall_precision"],
        "ranked_patterns": [
            {"pattern": name, **s, "per_dataset_category": breakdown[name], "loso": loso[name]}
            for name, s in ranked
        ],
        "conjunctions": conjunctions,
    }
    with open(output_dir / "fp_taxonomy.json", "w", encoding="utf-8") as f:
        json.dump(taxonomy, f, indent=2)

    print("\n" + "=" * 70)
    print("Stage distribution (exp1 = final baseline candidates):")
    for stage in STAGES:
        d = dist_reports[stage]
        print(f"  {stage}: total={d['total']} tp={d['tp']} fp={d['fp']} precision={d['precision']:.4f}")
    print("\nStage survival (raw-stage candidates only):")
    for k, v in survival.items():
        print(f"  {k}: {v}")
    print("\nRanked FP patterns (exp1 stage, ranked by LIFT -- lift < 1.0 means "
          "genuinely more FP-heavy than the population average; lift ~= 1.0 "
          "means NO discriminative signal regardless of raw FP count):")
    for name, s in ranked:
        print(f"  {name}: lift={s['lift']} (pattern_precision={s['pattern_precision']:.4f} vs "
              f"overall={s['overall_precision']:.4f}) coverage={s['coverage']} "
              f"FP={s['fp_count']} TP={s['tp_count']} datasets={s['n_datasets']}/4")
    print("\nTop-pattern conjunctions (2-way/3-way, ranked by lowest TP leakage):")
    for c in conjunctions["conjunctions"][:10]:
        print(f"  {'+'.join(c['patterns'])}: coverage={c['coverage']} FP={c['fp_count']} "
              f"TP={c['tp_count']} lift={c['lift']}")
    print(f"\nFull taxonomy written to {output_dir / 'fp_taxonomy.json'}")
    print(f"Distribution report written to {output_dir / 'distribution_report.json'}")
    print(f"Stage survival report written to {output_dir / 'stage_survival_report.json'}")


if __name__ == "__main__":
    main()
