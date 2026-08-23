#!/usr/bin/env python3
"""
K-Fold Cross-Validation Experiment Runner -- Full Engine Variant.

Forked from kfold_experiment_runner.py. This variant replaces the ad-hoc
"to_asp() + raw Clingo" replay used by the original script with the actual
engine orchestration used by the live LLM pipeline
(scripts/experiment/runners.py::run_step2_engine), replayed offline against
already-extracted step2_extractions.jsonl data (no LLM calls).

Per story: StateManager, RuleRegistry(rules_dir).load_legacy_rules(),
AliasResolver, ItemTracker, EventExecutor, FinalAnalyzer, LearningAdapter are
built exactly as run_step2_engine builds them. Chapters are replayed in
chronological order through the same per-chapter steps: alias normalization,
item tracking, EventExecutor.evaluate_chapter_structured() (which internally
does active-universe computation, to_asp(), and the real Clingo call), and
final_analyzer bookkeeping.

engine.conflict_resolver.ConflictResolver is intentionally NOT used here: it
is not part of the live pipeline (run_step2_engine never instantiates it), so
this script does not either. engine/conflict_resolver.py itself is untouched.

This script intentionally forks kfold_experiment_runner.py instead of
modifying it in place, per project convention: the original stays a faithful
reproduction of the paper's static-rules pipeline.

For each k from 1 to 4:
- k=1: Train on 4 stories, test on 1 (5 combinations)
- k=2: Train on 3 stories, test on 2 (10 combinations)
- k=3: Train on 2 stories, test on 3 (10 combinations)
- k=4: Train on 1 story, test on 4 (5 combinations)

Output:
- JSON files with detailed results per experiment
- Aggregate statistics and metrics
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state.config import ERRORS_CHECKLIST_DIR, RULES_DIR
from engine import (
    StateManager,
    RuleRegistry,
    EventExecutor,
    FinalAnalyzer,
    LearningAdapter,
    AliasResolver,
    ItemTracker,
)


# =============================================================================
# Debug instrumentation (temporary, controlled by --debug)
# =============================================================================

DEBUG = False


def dbg(msg: str, indent: int = 0) -> None:
    """Print a debug trace line if --debug is enabled. No effect on results."""
    if DEBUG:
        prefix = "  " * indent
        print(f"[DEBUG] {prefix}{msg}")


# =============================================================================
# Configuration
# =============================================================================

ALL_STORIES = [
    "Harry Potter",
    "The Hunger Games", 
    "Twilight",
    "Goosebumps",
    "The Lord of the Rings"
]

STORY_SLUG_MAP = {
    "Harry Potter": "harry_potter",
    "The Hunger Games": "the_hunger_games",
    "Twilight": "twilight",
    "Goosebumps": "goosebumps",
    "The Lord of the Rings": "the_lord_of_the_rings"
}

ERROR_TYPE_MAP = {
    "Basic Coherence": "coherence",
    "Emotional Relations": "emotional",
    "Location correctness": "location",
    "Temporal Order": "temporal",
    "Causality": "causality"
}


# =============================================================================
# Ground Truth Loading
# =============================================================================

@dataclass
class GroundTruthError:
    """Represents a ground truth error from CSV."""
    chunk_id: int
    chapter: str
    error_type: str
    description: str
    sentence: str
    story: str
    
    @property
    def chapter_num(self) -> int:
        """Extract chapter number from filename like '001.txt'."""
        match = re.match(r'(\d+)\.txt', self.chapter)
        if match:
            return int(match.group(1))
        return -1
    
    @property
    def category(self) -> str:
        """Map error type to category."""
        return ERROR_TYPE_MAP.get(self.error_type, "other")


def load_ground_truth(errors_dir: Path) -> Dict[str, List[GroundTruthError]]:
    """Load ground truth errors from all CSV files."""
    ground_truth = {}
    
    for csv_file in errors_dir.glob("*.csv"):
        story_slug = csv_file.stem.replace("_errors", "")
        # Find matching story name
        story_name = None
        for name, slug in STORY_SLUG_MAP.items():
            if slug == story_slug:
                story_name = name
                break
        
        if not story_name:
            continue
            
        errors = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                errors.append(GroundTruthError(
                    chunk_id=int(row.get("Chunk", -1)),
                    chapter=row.get("Chapter", ""),
                    error_type=row.get("Error Type", ""),
                    description=row.get("Error description", ""),
                    sentence=row.get("Error sentence", ""),
                    story=story_name
                ))
        
        ground_truth[story_name] = errors
    
    return ground_truth


def load_extractions(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load per-chapter extractions from JSONL file."""
    extractions = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                extractions.append(json.loads(line))
    return extractions


# =============================================================================
# Engine wiring -- mirrors scripts/experiment/runners.py::run_step2_engine,
# minus the LLM extraction call (extractions are replayed from
# step2_extractions.jsonl instead of freshly generated).
# =============================================================================

def build_engine(rules_dir: Path):
    """Build a fresh engine bundle for one story, exactly as run_step2_engine
    does: StateManager, RuleRegistry(rules_dir).load_legacy_rules(),
    AliasResolver, ItemTracker, EventExecutor, FinalAnalyzer, LearningAdapter.
    """
    state_manager = StateManager()
    rule_registry = RuleRegistry(rules_dir)
    loaded = rule_registry.load_legacy_rules()
    alias_resolver = AliasResolver()
    item_tracker = ItemTracker()
    event_executor = EventExecutor(state_manager, rule_registry, alias_resolver)
    final_analyzer = FinalAnalyzer(state_manager, rule_registry, item_tracker, alias_resolver)
    learning_adapter = LearningAdapter(rule_registry)

    dbg(f"build_engine(rules_dir={rules_dir}): load_legacy_rules() registered "
        f"{loaded} legacy rule entries; get_active_rule_files() -> "
        f"{len(rule_registry.get_active_rule_files())} file(s)")
    for rf in rule_registry.get_active_rule_files():
        dbg(f"+ {rf}", 1)

    return (state_manager, rule_registry, alias_resolver, item_tracker,
            event_executor, final_analyzer, learning_adapter)


def evaluate_story_with_engine(
    story: str,
    story_extractions: List[Dict[str, Any]],
    rules_dir: Path,
    enable_learning: bool = False,
) -> Dict[int, List[Dict[str, Any]]]:
    """Replay one story's chapters through the real engine pipeline
    (AliasResolver -> ItemTracker -> EventExecutor -> FinalAnalyzer), the same
    orchestration run_step2_engine uses for a live LLM run, just without the
    LLM call (chapter data comes from the extraction JSONL instead).

    Returns a dict of chapter_num -> list of violation dicts (each shaped
    like {"category", "type", "event", "detail"}, matching
    StructuredViolation.to_dict()'s "category"/"type" keys).
    """
    (state_manager, rule_registry, alias_resolver, item_tracker,
     event_executor, final_analyzer, learning_adapter) = build_engine(rules_dir)

    # Chronological order: the engine's cross-chapter state (StateManager,
    # AliasResolver, ItemTracker) accumulates chapter by chapter.
    story_extractions = sorted(story_extractions, key=lambda e: e.get("chapter", -1))
    dbg(f"--- Story: {story} ({len(story_extractions)} modified chapters, "
        f"chronological order, full engine) ---", 1)

    chapter_violations: Dict[int, List[Dict[str, Any]]] = {}
    previous_chapter_events: List[Dict[str, Any]] = []

    for extraction in story_extractions:
        chapter = extraction.get("chapter", -1)
        structured = extraction.get("extraction", {})

        structured, alias_conflicts = alias_resolver.normalize_extraction(structured, chapter)
        if alias_conflicts:
            dbg(f"Chapter {chapter}: {len(alias_conflicts)} alias conflict(s) detected", 2)

        structured = item_tracker.process_extraction(structured, chapter)

        eval_result = event_executor.evaluate_chapter_structured(
            structured, chapter,
            previous_chapter_events=previous_chapter_events,
            item_tracker=item_tracker,
            # This harness only ever evaluates variant == "modified" chapters
            # (see the caller in main()), so modified_story is always true here.
            modified_story=True,
        )
        previous_chapter_events = structured.get("events", [])

        violations = [v.to_dict() for v in eval_result.violations]
        chapter_violations[chapter] = violations
        dbg(f"Chapter {chapter}: {eval_result.event_count} event(s) -> "
            f"{len(violations)} violation(s)", 2)

        final_analyzer.record_chapter_evaluation(
            chapter_num=chapter,
            events=structured.get("events", []),
            violations=violations,
            entities=structured.get("entities", {}),
        )

        if enable_learning and eval_result.violations:
            learning_adapter.learn_rules_from_violations(
                current_facts=eval_result.asp_facts,
                violations=violations,
                chapter_num=chapter,
                story_id=story,
            )

    final_result = final_analyzer.analyze(story, len(story_extractions))
    dbg(f"Story {story}: final analysis -- {len(final_result.loose_ends)} loose end(s), "
        f"{len(final_result.long_range_inconsistencies)} long-range issue(s)", 1)

    return chapter_violations


# =============================================================================
# Experiment Runner
# =============================================================================

@dataclass
class ChapterResult:
    """Results for a single chapter."""
    story: str
    variant: str
    chapter: int
    violations: List[Dict[str, Any]]
    ground_truth_errors: List[Dict[str, Any]]
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0


@dataclass
class StoryResult:
    """Results for a single story."""
    story: str
    chapters: List[ChapterResult]
    total_violations: int = 0
    total_ground_truth: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


@dataclass
class ExperimentResult:
    """Results for a single k-fold experiment."""
    k: int
    test_stories: List[str]
    train_stories: List[str]
    story_results: List[StoryResult]
    total_violations: int = 0
    total_ground_truth: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    timestamp: str = ""


def match_error_category(violation_cat: str, ground_truth_cat: str, strict: bool = False) -> bool:
    """Check if violation category matches ground truth category.
    
    Args:
        violation_cat: Category from detected violation
        ground_truth_cat: Category from ground truth CSV
        strict: If True, require category match. If False, any violation counts.
    """
    if not strict:
        # Lenient mode: any violation in a chapter with GT error counts
        return True
        
    # Normalize categories
    v_cat = violation_cat.lower()
    gt_cat = ground_truth_cat.lower()
    
    # Direct match
    if v_cat == gt_cat:
        return True
    
    # Relaxed matching (some flexibility)
    category_groups = {
        "temporal": {"temporal", "time", "order"},
        "location": {"location", "spatial", "position"},
        "causality": {"causality", "causal", "cause"},
        "emotional": {"emotional", "emotion", "relationship"},
        "coherence": {"coherence", "basic", "logic"}
    }
    
    for group_name, group_members in category_groups.items():
        if v_cat in group_members or group_name == v_cat:
            if gt_cat in group_members or group_name == gt_cat:
                return True
    
    return False


def run_experiment_for_stories(
    story_violations_cache: Dict[str, Dict[int, List[Dict[str, Any]]]],
    test_stories: List[str],
    ground_truth: Dict[str, List[GroundTruthError]],
    verbose: bool = False,
) -> List[StoryResult]:
    """Score test stories against ground truth using cached engine violations.

    The engine's per-chapter violations for a story do not depend on which
    k-fold combination is being scored (the rule set/engine behavior is
    fixed), so evaluation is done once per story up front (see main()) and
    this function only performs matching/scoring.
    """
    
    story_results = []
    
    for story in test_stories:
        chapter_violations = story_violations_cache.get(story, {})
        
        if verbose:
            print(f"  Scoring {story}: {len(chapter_violations)} evaluated chapters")
        dbg(f"--- Scoring story: {story} ({len(chapter_violations)} chapters) ---", 1)
        
        # Get ground truth for this story
        gt_errors = ground_truth.get(story, [])
        gt_by_chapter = defaultdict(list)
        for err in gt_errors:
            gt_by_chapter[err.chapter_num].append(err)
        dbg(f"Ground truth for {story}: {len(gt_errors)} errors loaded from static CSV "
            f"(errors_checklist), NOT generated at runtime", 2)
        
        chapter_results = []
        story_total_violations = 0
        story_tp = 0
        story_fp = 0
        story_fn = 0
        
        for chapter, categorized in sorted(chapter_violations.items()):
            # Get ground truth for this chapter
            chapter_gt = gt_by_chapter.get(chapter, [])
            
            # Match violations to ground truth
            # A violation is a TP if it's in a chapter with a GT error of matching category
            matched_gt = set()
            tp = 0
            
            for v in categorized:
                v_cat = v.get("category", "")
                matched = False
                
                for i, gt in enumerate(chapter_gt):
                    if i not in matched_gt:
                        if match_error_category(v_cat, gt.category, strict=True):
                            matched = True
                            matched_gt.add(i)
                            tp += 1
                            break
                
                if not matched:
                    # FP: violation with no matching GT
                    pass
            
            fp = len(categorized) - tp
            fn = len(chapter_gt) - len(matched_gt)
            dbg(f"Chapter {chapter}: violations={len(categorized)} gt_errors={len(chapter_gt)} "
                f"-> tp={tp} fp={fp} fn={fn}", 2)
            
            chapter_results.append(ChapterResult(
                story=story,
                variant="modified",
                chapter=chapter,
                violations=categorized,
                ground_truth_errors=[asdict(gt) if hasattr(gt, '__dict__') else 
                                    {"chunk_id": gt.chunk_id, "chapter": gt.chapter, 
                                     "error_type": gt.error_type, "category": gt.category}
                                    for gt in chapter_gt],
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn
            ))
            
            story_total_violations += len(categorized)
            story_tp += tp
            story_fp += fp
            story_fn += fn
        
        # Calculate metrics
        precision = story_tp / (story_tp + story_fp) if (story_tp + story_fp) > 0 else 0
        recall = story_tp / (story_tp + story_fn) if (story_tp + story_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        dbg(f"Story {story} totals: violations={story_total_violations} gt={len(gt_errors)} "
            f"tp={story_tp} fp={story_fp} fn={story_fn} "
            f"precision={precision:.4f} recall={recall:.4f} f1={f1:.4f}", 1)
        
        story_results.append(StoryResult(
            story=story,
            chapters=chapter_results,
            total_violations=story_total_violations,
            total_ground_truth=len(gt_errors),
            true_positives=story_tp,
            false_positives=story_fp,
            false_negatives=story_fn,
            precision=precision,
            recall=recall,
            f1=f1
        ))
    
    return story_results


def run_kfold_experiment(
    k: int,
    story_violations_cache: Dict[str, Dict[int, List[Dict[str, Any]]]],
    ground_truth: Dict[str, List[GroundTruthError]],
    verbose: bool = False,
) -> List[ExperimentResult]:
    """Run all k-fold experiments for a given k."""
    
    results = []
    
    # Generate all combinations of k test stories
    for test_combo in combinations(ALL_STORIES, k):
        test_stories = list(test_combo)
        train_stories = [s for s in ALL_STORIES if s not in test_stories]
        dbg(f"=== k={k} combination: test={test_stories} train={train_stories} ===")
        
        if verbose:
            print(f"\nExperiment: test={test_stories}")
        
        # Score experiment (engine evaluation already cached in main())
        story_results = run_experiment_for_stories(
            story_violations_cache, test_stories, ground_truth, verbose
        )
        
        # Aggregate metrics
        total_violations = sum(sr.total_violations for sr in story_results)
        total_gt = sum(sr.total_ground_truth for sr in story_results)
        total_tp = sum(sr.true_positives for sr in story_results)
        total_fp = sum(sr.false_positives for sr in story_results)
        total_fn = sum(sr.false_negatives for sr in story_results)
        
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        results.append(ExperimentResult(
            k=k,
            test_stories=test_stories,
            train_stories=train_stories,
            story_results=story_results,
            total_violations=total_violations,
            total_ground_truth=total_gt,
            true_positives=total_tp,
            false_positives=total_fp,
            false_negatives=total_fn,
            precision=precision,
            recall=recall,
            f1=f1,
            timestamp=datetime.now().isoformat()
        ))
    
    return results


# =============================================================================
# Per-Category Strict Metrics
# =============================================================================

PER_CATEGORY_STRICT_CATEGORIES = ["coherence", "emotional", "location", "temporal", "causality"]


def compute_per_category_strict(story_results: List[StoryResult]) -> Dict[str, Any]:
    """Aggregate per-category precision/recall/f1 (strict category matching) across
    a set of StoryResult objects (normally all 5 k=1 folds, i.e. every story tested
    exactly once against the other four).

    For each category: gt = ground truth errors of that category, tp = detected
    violations of that category matched to an unused GT error of the same category
    (same greedy strict-matching order used in run_experiment_for_stories),
    violations = total detected violations of that category (matched or not).
    precision = tp / violations, recall = tp / gt.
    """
    stats = {cat: {"gt": 0, "tp": 0, "violations": 0} for cat in PER_CATEGORY_STRICT_CATEGORIES}

    for sr in story_results:
        for ch in sr.chapters:
            # ground_truth_errors dicts come from asdict() and lack the 'category'
            # property, so re-derive it from error_type.
            gt_cats = [
                gt.get("category") or ERROR_TYPE_MAP.get(gt.get("error_type", ""), "other")
                for gt in ch.ground_truth_errors
            ]
            matched_gt: Set[int] = set()

            for v in ch.violations:
                v_cat = v.get("category", "other")
                if v_cat in stats:
                    stats[v_cat]["violations"] += 1
                for i, gt_cat in enumerate(gt_cats):
                    if i not in matched_gt and gt_cat == v_cat:
                        matched_gt.add(i)
                        if v_cat in stats:
                            stats[v_cat]["tp"] += 1
                        break

            for gt_cat in gt_cats:
                if gt_cat in stats:
                    stats[gt_cat]["gt"] += 1

    result: Dict[str, Any] = {}
    totals = {"gt": 0, "tp": 0, "fn": 0, "violations": 0}

    for cat in PER_CATEGORY_STRICT_CATEGORIES:
        s = stats[cat]
        fn = s["gt"] - s["tp"]
        precision = (s["tp"] / s["violations"] * 100) if s["violations"] > 0 else 0.0
        recall = (s["tp"] / s["gt"] * 100) if s["gt"] > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        result[cat] = {
            "gt": s["gt"],
            "tp": s["tp"],
            "fn": fn,
            "violations": s["violations"],
            "recall": round(recall, 2),
            "precision": round(precision, 2),
            "f1": round(f1, 2),
        }

        totals["gt"] += s["gt"]
        totals["tp"] += s["tp"]
        totals["fn"] += fn
        totals["violations"] += s["violations"]

    precision = (totals["tp"] / totals["violations"] * 100) if totals["violations"] > 0 else 0.0
    recall = (totals["tp"] / totals["gt"] * 100) if totals["gt"] > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    result["total"] = {
        **totals,
        "recall": round(recall, 2),
        "precision": round(precision, 2),
        "f1": round(f1, 2),
    }

    return result


# =============================================================================
# JSON Serialization
# =============================================================================

def experiment_result_to_dict(result: ExperimentResult) -> Dict[str, Any]:
    """Convert ExperimentResult to dictionary for JSON serialization."""
    return {
        "k": result.k,
        "test_stories": result.test_stories,
        "train_stories": result.train_stories,
        "metrics": {
            "total_violations": result.total_violations,
            "total_ground_truth": result.total_ground_truth,
            "true_positives": result.true_positives,
            "false_positives": result.false_positives,
            "false_negatives": result.false_negatives,
            "precision": round(result.precision, 4),
            "recall": round(result.recall, 4),
            "f1": round(result.f1, 4)
        },
        "story_results": [
            {
                "story": sr.story,
                "total_violations": sr.total_violations,
                "total_ground_truth": sr.total_ground_truth,
                "true_positives": sr.true_positives,
                "false_positives": sr.false_positives,
                "false_negatives": sr.false_negatives,
                "precision": round(sr.precision, 4),
                "recall": round(sr.recall, 4),
                "f1": round(sr.f1, 4),
                "chapters_with_violations": len([c for c in sr.chapters if c.violations]),
                "chapters_with_ground_truth": len([c for c in sr.chapters if c.ground_truth_errors])
            }
            for sr in result.story_results
        ],
        "timestamp": result.timestamp
    }


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run k-fold cross-validation experiments for narrative coherence "
                    "by replaying step2_extractions.jsonl through the full engine "
                    "pipeline (StateManager, RuleRegistry, AliasResolver, ItemTracker, "
                    "EventExecutor, FinalAnalyzer, LearningAdapter), the same "
                    "orchestration used by the live LLM run, without the LLM call."
    )
    parser.add_argument(
        "--experiment_dir",
        type=str,
        default="experiments/15_extraction_only",
        help="Path to experiment directory containing step2_extractions.jsonl"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="experiments/kfold_results",
        help="Directory to write JSON results"
    )
    parser.add_argument(
        "--errors_dir",
        type=str,
        default=None,
        help="Directory with ground truth CSVs (default: the active dataset's errors_checklist)"
    )
    parser.add_argument(
        "--rules_dir",
        type=str,
        default=None,
        help="Directory containing the ASP rule files (default: repo's rules/). "
             "Use this to point at a specific rules snapshot, e.g. to reproduce "
             "an older experiment's exact rule set."
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs='+',
        default=[1, 2, 3, 4],
        help="K values to test (default: 1 2 3 4)"
    )
    parser.add_argument(
        "--enable-learning",
        action="store_true",
        help="Enable LearningAdapter/ILASP rule learning during engine evaluation "
             "(default off -- ILASP may be slow or unavailable)."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print detailed [DEBUG] trace lines showing exactly which rule files "
             "are loaded (and from where), per-chapter engine evaluation "
             "(alias/item/event/final-analysis steps), and per-story/per-chapter "
             "TP/FP/FN. Does not affect results."
    )
    
    args = parser.parse_args()
    
    global DEBUG
    DEBUG = args.debug
    if DEBUG:
        print("[DEBUG] Debug tracing ENABLED\n")
    
    # Setup paths
    experiment_dir = Path(args.experiment_dir)
    if not experiment_dir.is_absolute():
        experiment_dir = PROJECT_ROOT / experiment_dir
    
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    errors_dir = Path(args.errors_dir) if args.errors_dir else ERRORS_CHECKLIST_DIR
    if not errors_dir.is_absolute():
        errors_dir = PROJECT_ROOT / errors_dir

    rules_dir = Path(args.rules_dir) if args.rules_dir else RULES_DIR
    if not rules_dir.is_absolute():
        rules_dir = PROJECT_ROOT / rules_dir

    # Load data
    print("Loading extractions...")
    extractions_path = experiment_dir / "step2_extractions.jsonl"
    if not extractions_path.exists():
        print(f"Error: No extractions found at {extractions_path}")
        sys.exit(1)
    
    extractions = load_extractions(extractions_path)
    print(f"Loaded {len(extractions)} chapter extractions")
    
    print("Loading ground truth...")
    ground_truth = load_ground_truth(errors_dir)
    for story, errors in ground_truth.items():
        print(f"  {story}: {len(errors)} ground truth errors")
    
    print(f"Rules directory: {rules_dir}")
    print("Evaluating each story once through the full engine "
          "(StateManager, RuleRegistry, AliasResolver, ItemTracker, EventExecutor, "
          "FinalAnalyzer, LearningAdapter) -- rule set is fixed, so this result is "
          "reused across every k-fold combination below.")
    story_violations_cache: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
    for story in ALL_STORIES:
        story_extractions = [
            e for e in extractions
            if e.get("story") == story and e.get("variant") == "modified"
        ]
        print(f"  Evaluating {story}: {len(story_extractions)} modified chapters...")
        story_violations_cache[story] = evaluate_story_with_engine(
            story, story_extractions, rules_dir, enable_learning=args.enable_learning
        )
        total_violations = sum(len(v) for v in story_violations_cache[story].values())
        print(f"    -> {total_violations} violation(s) across "
              f"{len(story_violations_cache[story])} chapter(s)")
    
    # Run experiments for each k
    all_results = {}
    
    for k in args.k:
        print(f"\n{'='*60}")
        print(f"Running k={k} experiments ({len(list(combinations(ALL_STORIES, k)))} combinations)")
        print(f"{'='*60}")
        
        results = run_kfold_experiment(
            k, story_violations_cache, ground_truth, args.verbose
        )
        
        all_results[f"k{k}"] = results
        
        # Write individual k results
        k_output_file = output_dir / f"kfold_k{k}_results.json"
        with open(k_output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "k": k,
                "num_experiments": len(results),
                "experiments": [experiment_result_to_dict(r) for r in results]
            }, f, indent=2)
        
        print(f"Written results to {k_output_file}")
        
        # Print summary
        avg_precision = sum(r.precision for r in results) / len(results)
        avg_recall = sum(r.recall for r in results) / len(results)
        avg_f1 = sum(r.f1 for r in results) / len(results)
        
        print(f"\nk={k} Summary:")
        print(f"  Avg Precision: {avg_precision:.4f}")
        print(f"  Avg Recall: {avg_recall:.4f}")
        print(f"  Avg F1: {avg_f1:.4f}")
    
    # Write aggregate results
    aggregate_file = output_dir / "kfold_aggregate_results.json"
    aggregate_data = {
        "timestamp": datetime.now().isoformat(),
        "stories": ALL_STORIES,
        "ground_truth_counts": {s: len(e) for s, e in ground_truth.items()},
        "k_summaries": {}
    }
    
    for k_key, results in all_results.items():
        k = int(k_key[1:])
        aggregate_data["k_summaries"][k_key] = {
            "k": k,
            "num_experiments": len(results),
            "avg_precision": round(sum(r.precision for r in results) / len(results), 4),
            "avg_recall": round(sum(r.recall for r in results) / len(results), 4),
            "avg_f1": round(sum(r.f1 for r in results) / len(results), 4),
            "total_tp": sum(r.true_positives for r in results),
            "total_fp": sum(r.false_positives for r in results),
            "total_fn": sum(r.false_negatives for r in results)
        }
    
    with open(aggregate_file, 'w', encoding='utf-8') as f:
        json.dump(aggregate_data, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Aggregate results written to {aggregate_file}")
    print(f"{'='*60}")

    # Per-category strict metrics require k=1 (one fold per story, covering
    # the whole dataset exactly once).
    if "k1" in all_results:
        print("\nComputing per-category strict metrics (k=1)...")
        per_category = compute_per_category_strict(
            [sr for r in all_results["k1"] for sr in r.story_results]
        )
        per_category_file = output_dir / "per_category_strict.json"
        with open(per_category_file, 'w', encoding='utf-8') as f:
            json.dump(per_category, f, indent=2)
        print(f"Written per-category strict metrics to {per_category_file}")
    else:
        print("\nSkipping per_category_strict.json (requires --k 1 to be included)")


if __name__ == "__main__":
    main()
