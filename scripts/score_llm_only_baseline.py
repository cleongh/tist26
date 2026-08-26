#!/usr/bin/env python3
"""
Score a "full_only_llm_human" experiment's already-extracted LLM errors
(experiments/<name>/extracted_errors/*_extracted_errors.csv) against
errors_checklist/ ground truth, producing Precision/Recall/F1 in the same
shape as kfold_experiment_runner_conflict_resolver.py's k=1 output (overall
per-story + averaged, plus a per-category-strict breakdown) -- WITHOUT
running the logic engine at all. Pure LLM-only baseline scoring.

Uses the exact same strict chapter+category matching rule as the engine
scorer (`match_error_category(strict=True)`, direct-category-name or
same-category-group match) so numbers are directly comparable to
`kfold_experiment_runner_conflict_resolver.py`'s "Avg Precision/Recall/F1"
and `per_category_strict.json` output.

Usage:
    python scripts/score_llm_only_baseline.py \\
        --extracted_errors_dir experiments/20082026_claude_full_only_llm_human/extracted_errors \\
        --output_dir /tmp/claude_llm_only_scored
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state.config import ERRORS_CHECKLIST_DIR

ALL_STORIES = [
    "Harry Potter",
    "The Hunger Games",
    "Twilight",
    "Goosebumps",
    "The Lord of the Rings",
]

STORY_SLUG_MAP = {
    "Harry Potter": "harry_potter",
    "The Hunger Games": "the_hunger_games",
    "Twilight": "twilight",
    "Goosebumps": "goosebumps",
    "The Lord of the Rings": "the_lord_of_the_rings",
}

ERROR_TYPE_MAP = {
    "Basic Coherence": "coherence",
    "Emotional Relations": "emotional",
    "Location correctness": "location",
    "Temporal Order": "temporal",
    "Causality": "causality",
}

PER_CATEGORY_STRICT_CATEGORIES = ["coherence", "emotional", "location", "temporal", "causality"]

_CATEGORY_GROUPS = {
    "temporal": {"temporal", "time", "order"},
    "location": {"location", "spatial", "position"},
    "causality": {"causality", "causal", "cause"},
    "emotional": {"emotional", "emotion", "relationship"},
    "coherence": {"coherence", "basic", "logic"},
}


@dataclass
class GroundTruthError:
    chunk_id: int
    chapter: str
    error_type: str
    story: str

    @property
    def chapter_num(self) -> int:
        match = re.match(r'(\d+)\.txt', self.chapter)
        return int(match.group(1)) if match else -1

    @property
    def category(self) -> str:
        return ERROR_TYPE_MAP.get(self.error_type, "other")


def load_ground_truth(errors_dir: Path) -> Dict[str, List[GroundTruthError]]:
    """Mirrors kfold_experiment_runner_conflict_resolver.load_ground_truth,
    duplicated here so this script has no dependency on the engine-driven
    runner (this script never touches the engine/logic pipeline)."""
    ground_truth: Dict[str, List[GroundTruthError]] = {}
    for csv_file in errors_dir.glob("*.csv"):
        story_slug = csv_file.stem.replace("_errors", "")
        story_name = next((n for n, s in STORY_SLUG_MAP.items() if s == story_slug), None)
        if not story_name:
            continue
        errors = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                errors.append(GroundTruthError(
                    chunk_id=int(row.get("Chunk", -1)),
                    chapter=row.get("Chapter", ""),
                    error_type=row.get("Error Type", ""),
                    story=story_name,
                ))
        ground_truth[story_name] = errors
    return ground_truth


def match_error_category(detected_cat: str, ground_truth_cat: str) -> bool:
    """Strict-mode category match, mirrors kfold's match_error_category(strict=True)."""
    d_cat = detected_cat.lower()
    gt_cat = ground_truth_cat.lower()
    if d_cat == gt_cat:
        return True
    for group_name, members in _CATEGORY_GROUPS.items():
        if (d_cat in members or group_name == d_cat) and (gt_cat in members or group_name == gt_cat):
            return True
    return False


def load_extracted_errors(extracted_errors_dir: Path) -> Dict[str, Dict[int, List[Dict[str, Any]]]]:
    """Load `<story_slug>_extracted_errors.csv` files (Chapter, Category,
    Description columns) into story -> chapter_num -> [errors]."""
    by_story: Dict[str, Dict[int, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for story_name, slug in STORY_SLUG_MAP.items():
        csv_path = extracted_errors_dir / f"{slug}_extracted_errors.csv"
        if not csv_path.exists():
            continue
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                chapter_str = row.get("Chapter", "")
                match = re.match(r'(\d+)\.txt', chapter_str)
                if not match:
                    continue
                chapter_num = int(match.group(1))
                by_story[story_name][chapter_num].append({
                    "category": row.get("Category", "unknown"),
                    "description": row.get("Description", ""),
                })
    return by_story


def score(
    detected_by_story: Dict[str, Dict[int, List[Dict[str, Any]]]],
    ground_truth: Dict[str, List[GroundTruthError]],
) -> Dict[str, Any]:
    """Same greedy per-chapter strict-matching algorithm as
    run_experiment_for_stories()/compute_per_category_strict() in
    kfold_experiment_runner_conflict_resolver.py, applied to LLM-only
    extracted errors instead of engine violations."""
    story_metrics: Dict[str, Any] = {}
    cat_stats = {cat: {"gt": 0, "tp": 0, "violations": 0} for cat in PER_CATEGORY_STRICT_CATEGORIES}

    for story in ALL_STORIES:
        gt_errors = ground_truth.get(story, [])
        gt_by_chapter: Dict[int, List[GroundTruthError]] = defaultdict(list)
        for err in gt_errors:
            gt_by_chapter[err.chapter_num].append(err)

        chapters_by_story = detected_by_story.get(story, {})
        all_chapters = set(chapters_by_story.keys()) | set(gt_by_chapter.keys())

        story_tp = story_fp = story_fn = story_violations = 0
        for chapter in all_chapters:
            detected = chapters_by_story.get(chapter, [])
            chapter_gt = gt_by_chapter.get(chapter, [])

            matched_gt: Set[int] = set()
            tp = 0
            for v in detected:
                for i, gt in enumerate(chapter_gt):
                    if i not in matched_gt and match_error_category(v["category"], gt.category):
                        matched_gt.add(i)
                        tp += 1
                        break
            fp = len(detected) - tp
            fn = len(chapter_gt) - len(matched_gt)
            story_tp += tp
            story_fp += fp
            story_fn += fn
            story_violations += len(detected)

            gt_cats = [gt.category for gt in chapter_gt]
            cat_matched: Set[int] = set()
            for v in detected:
                v_cat = v["category"]
                if v_cat in cat_stats:
                    cat_stats[v_cat]["violations"] += 1
                for i, gt_cat in enumerate(gt_cats):
                    if i not in cat_matched and gt_cat == v_cat:
                        cat_matched.add(i)
                        if v_cat in cat_stats:
                            cat_stats[v_cat]["tp"] += 1
                        break
            for gt_cat in gt_cats:
                if gt_cat in cat_stats:
                    cat_stats[gt_cat]["gt"] += 1

        precision = story_tp / (story_tp + story_fp) if (story_tp + story_fp) > 0 else 0.0
        recall = story_tp / (story_tp + story_fn) if (story_tp + story_fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        story_metrics[story] = {
            "violations": story_violations, "gt": len(gt_errors),
            "true_positives": story_tp, "false_positives": story_fp, "false_negatives": story_fn,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        }

    avg_precision = sum(m["precision"] for m in story_metrics.values()) / len(story_metrics)
    avg_recall = sum(m["recall"] for m in story_metrics.values()) / len(story_metrics)
    avg_f1 = sum(m["f1"] for m in story_metrics.values()) / len(story_metrics)

    per_category: Dict[str, Any] = {}
    totals = {"gt": 0, "tp": 0, "fn": 0, "violations": 0}
    for cat in PER_CATEGORY_STRICT_CATEGORIES:
        s = cat_stats[cat]
        fn = s["gt"] - s["tp"]
        precision = (s["tp"] / s["violations"] * 100) if s["violations"] > 0 else 0.0
        recall = (s["tp"] / s["gt"] * 100) if s["gt"] > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_category[cat] = {
            "gt": s["gt"], "tp": s["tp"], "fn": fn, "violations": s["violations"],
            "precision": round(precision, 2), "recall": round(recall, 2), "f1": round(f1, 2),
        }
        totals["gt"] += s["gt"]
        totals["tp"] += s["tp"]
        totals["fn"] += fn
        totals["violations"] += s["violations"]

    total_precision = (totals["tp"] / totals["violations"] * 100) if totals["violations"] > 0 else 0.0
    total_recall = (totals["tp"] / totals["gt"] * 100) if totals["gt"] > 0 else 0.0
    total_f1 = (2 * total_precision * total_recall / (total_precision + total_recall)
                if (total_precision + total_recall) > 0 else 0.0)
    per_category["total"] = {
        "gt": totals["gt"], "tp": totals["tp"], "fn": totals["fn"], "violations": totals["violations"],
        "precision": round(total_precision, 2), "recall": round(total_recall, 2), "f1": round(total_f1, 2),
    }

    return {
        "story_results": story_metrics,
        "avg_precision": round(avg_precision, 4),
        "avg_recall": round(avg_recall, 4),
        "avg_f1": round(avg_f1, 4),
        "per_category_strict": per_category,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extracted_errors_dir", required=True,
                         help="Path to a full_only_llm_human experiment's extracted_errors/ folder.")
    parser.add_argument("--errors_dir", default=None,
                         help="Ground truth checklist dir (default: errors_checklist/).")
    parser.add_argument("--output_dir", default=None,
                         help="If given, write llm_only_results.json there.")
    args = parser.parse_args()

    extracted_errors_dir = Path(args.extracted_errors_dir)
    if not extracted_errors_dir.is_absolute():
        extracted_errors_dir = PROJECT_ROOT / extracted_errors_dir
    if not extracted_errors_dir.exists():
        print(f"Error: {extracted_errors_dir} does not exist")
        sys.exit(1)

    errors_dir = Path(args.errors_dir) if args.errors_dir else ERRORS_CHECKLIST_DIR
    if not errors_dir.is_absolute():
        errors_dir = PROJECT_ROOT / errors_dir

    print(f"Loading LLM-only extracted errors from {extracted_errors_dir} ...")
    detected_by_story = load_extracted_errors(extracted_errors_dir)
    for story in ALL_STORIES:
        n = sum(len(v) for v in detected_by_story.get(story, {}).values())
        print(f"  {story}: {n} extracted error(s)")

    print(f"\nLoading ground truth from {errors_dir} ...")
    ground_truth = load_ground_truth(errors_dir)
    for story, errors in ground_truth.items():
        print(f"  {story}: {len(errors)} ground truth error(s)")

    print("\nScoring (strict chapter+category matching, same rule as "
          "kfold_experiment_runner_conflict_resolver.py)...")
    results = score(detected_by_story, ground_truth)

    print("\nPer-story results:")
    for story, m in results["story_results"].items():
        print(f"  {story}: violations={m['violations']} gt={m['gt']} "
              f"tp={m['true_positives']} fp={m['false_positives']} fn={m['false_negatives']} "
              f"P={m['precision']:.4f} R={m['recall']:.4f} F1={m['f1']:.4f}")

    print(f"\nAvg Precision: {results['avg_precision']:.4f}")
    print(f"Avg Recall: {results['avg_recall']:.4f}")
    print(f"Avg F1: {results['avg_f1']:.4f}")

    print("\nPer-category (strict):")
    for cat, s in results["per_category_strict"].items():
        print(f"  {cat}: gt={s['gt']} tp={s['tp']} fn={s['fn']} violations={s['violations']} "
              f"P={s['precision']}% R={s['recall']}% F1={s['f1']}%")

    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "llm_only_results.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nWritten results to {out_path}")


if __name__ == "__main__":
    main()
