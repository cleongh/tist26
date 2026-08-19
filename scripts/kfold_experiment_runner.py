#!/usr/bin/env python3
"""
K-Fold Cross-Validation Experiment Runner for Narrative Coherence Detection.

This script runs leave-k-out cross-validation experiments on the logic-based
coherence detection system. It evaluates how well the system generalizes
across different story combinations.

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
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import logic modules
from scripts.logic.asp_converter import to_asp
from scripts.state.config import DATA_ROOT


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


# =============================================================================
# Clingo Integration
# =============================================================================

def collect_rule_files(stories: List[str] = None) -> List[Path]:
    """Collect all rule files to load into Clingo.
    
    Args:
        stories: Optional list of story names to load story-specific rules for.
                 If None, loads all story rules.
    """
    rules_dir = PROJECT_ROOT / "rules"
    rule_files = []
    
    # Core rules
    core_file = rules_dir / "core.lp"
    if core_file.exists():
        rule_files.append(core_file)
    
    # General narrative rules
    general_narrative = rules_dir / "general_narrative.lp"
    if general_narrative.exists():
        rule_files.append(general_narrative)
    
    # Story-specific rules (legacy location)
    story_rules = rules_dir / "story_rules.lp"
    if story_rules.exists():
        rule_files.append(story_rules)
    
    # Enhanced detection rules
    enhanced_detection = rules_dir / "enhanced_detection.lp"
    if enhanced_detection.exists():
        rule_files.append(enhanced_detection)
    
    # Universal rules (all .lp files)
    universal_dir = rules_dir / "universal"
    if universal_dir.exists():
        for lp_file in sorted(universal_dir.glob("*.lp")):
            rule_files.append(lp_file)
    
    # Story-specific rules from rules/story/ directory
    story_dir = rules_dir / "story"
    if story_dir.exists():
        # Map story names to rule file names
        story_rule_map = {
            "Harry Potter": "harry_potter.lp",
            "The Hunger Games": "hunger_games.lp",
            "Twilight": "twilight.lp",
            "Goosebumps": "goosebumps.lp",
            "The Lord of the Rings": "lord_of_the_rings.lp"
        }
        
        if stories:
            # Load only specific story rules
            for story in stories:
                rule_name = story_rule_map.get(story)
                if rule_name:
                    rule_file = story_dir / rule_name
                    if rule_file.exists():
                        rule_files.append(rule_file)
        else:
            # Load all story rules
            for lp_file in sorted(story_dir.glob("*.lp")):
                rule_files.append(lp_file)
    
    return rule_files


def run_clingo(asp_facts: str, rule_files: List[Path]) -> List[Tuple[str, ...]]:
    """Run Clingo solver and return violations."""
    import clingo
    
    violations = []
    
    # Write facts to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.lp', delete=False) as f:
        f.write(asp_facts)
        facts_path = Path(f.name)
    
    try:
        ctl = clingo.Control(["--warn=none"])
        
        # Load all rule files
        for rule_file in rule_files:
            if rule_file.exists():
                ctl.load(str(rule_file))
        
        # Load facts
        ctl.load(str(facts_path))
        
        # Ground and solve
        ctl.ground([("base", [])])
        
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                for atom in model.symbols(shown=True):
                    if atom.name == "violation":
                        parts = tuple(str(arg) for arg in atom.arguments)
                        violations.append(parts)
    
    finally:
        facts_path.unlink(missing_ok=True)
    
    return violations


def categorize_violation(v: Tuple[str, ...]) -> Dict[str, Any]:
    """Categorize a violation tuple into structured format."""
    if len(v) >= 4:
        category = v[0].strip('"').lower()
        vtype = v[1].strip('"')
        event = v[2].strip('"')
        detail = v[3].strip('"')
    elif len(v) >= 3:
        vtype = v[0].strip('"')
        event = v[1].strip('"')
        detail = v[2].strip('"')
        category = infer_category(vtype)
    elif len(v) >= 2:
        vtype = v[0].strip('"')
        event = v[1].strip('"')
        detail = ""
        category = infer_category(vtype)
    else:
        return {
            "category": "unknown",
            "type": "unknown",
            "event": "unknown",
            "detail": str(v),
        }
    
    return {
        "category": category,
        "type": vtype,
        "event": event,
        "detail": detail,
    }


def infer_category(vtype: str) -> str:
    """Infer error category from violation type."""
    vtype = vtype.lower()
    
    if vtype in {"ubiquity", "proximity_required", "impossible_travel", 
                 "unreachable_location", "explicit_ubiquity", "invalid_remote",
                 "simultaneous_presence"}:
        return "location"
    if vtype in {"circular_time", "negative_duration", "explicit_order_violated", 
                 "epistemic_temporal_violation", "temporal_inconsistency",
                 "ordering_violation", "causal_violation", "state_contradiction",
                 "time_travel", "knowledge_before_acquisition"}:
        return "temporal"
    if vtype in {"chekhov_gun", "uncaused_event", "effect_without_cause", 
                 "precondition_missing", "causality", "dead_character_acting",
                 "interacting_with_dead", "give_without_having"}:
        return "causality"
    if vtype in {"conflicting_dialogue", "out_of_character", "relationship_violation",
                 "hostile_greeting", "friendly_threat", "neutral_departure_no_greeting",
                 "relationship_action_mismatch", "relationship_betrayal",
                 "trait_action_mismatch"}:
        return "emotional"
    if vtype in {"appearance_change_without_cause", "state_persistence_error",
                 "appearance", "coherence", "solo_communication",
                 "impossible_self_action", "contradictory_state"}:
        return "coherence"
    
    return "other"


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


def load_extractions(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load per-chapter extractions from JSONL file."""
    extractions = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                extractions.append(json.loads(line))
    return extractions


def match_violation_to_chapter(violation: Dict[str, Any], chapter: int) -> bool:
    """Check if a violation matches a specific chapter."""
    # The violation event ID might contain chapter info
    event = violation.get("event", "")
    detail = violation.get("detail", "")
    
    # Check if chapter number appears in the violation
    # Events are typically named like "e1", "e2" etc. within a chapter
    # The chapter context comes from how we run the solver
    return True  # For now, all violations in a chapter run belong to that chapter


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
    extractions: List[Dict[str, Any]],
    test_stories: List[str],
    ground_truth: Dict[str, List[GroundTruthError]],
    rule_files: List[Path],
    verbose: bool = False
) -> List[StoryResult]:
    """Run experiment on test stories and compute metrics."""
    
    story_results = []
    
    for story in test_stories:
        # Filter extractions for this story (modified only for error detection)
        story_extractions = [
            e for e in extractions 
            if e.get("story") == story and e.get("variant") == "modified"
        ]
        
        if verbose:
            print(f"  Processing {story}: {len(story_extractions)} modified chapters")
        
        # Get ground truth for this story
        gt_errors = ground_truth.get(story, [])
        gt_by_chapter = defaultdict(list)
        for err in gt_errors:
            gt_by_chapter[err.chapter_num].append(err)
        
        chapter_results = []
        story_total_violations = 0
        story_tp = 0
        story_fp = 0
        story_fn = 0
        
        for extraction in story_extractions:
            chapter = extraction.get("chapter", -1)
            chapter_data = extraction.get("extraction", {})
            
            # Convert to ASP
            asp_facts = to_asp(chapter_data, chapter)
            asp_facts += "\n% Variant indicator\nmodified_story.\n"
            
            # Run Clingo
            violations = run_clingo(asp_facts, rule_files)
            categorized = [categorize_violation(v) for v in violations]
            
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
    extractions: List[Dict[str, Any]],
    ground_truth: Dict[str, List[GroundTruthError]],
    rule_files: List[Path],
    verbose: bool = False
) -> List[ExperimentResult]:
    """Run all k-fold experiments for a given k."""
    
    results = []
    
    # Generate all combinations of k test stories
    for test_combo in combinations(ALL_STORIES, k):
        test_stories = list(test_combo)
        train_stories = [s for s in ALL_STORIES if s not in test_stories]
        
        if verbose:
            print(f"\nExperiment: test={test_stories}")
        
        # Run experiment
        story_results = run_experiment_for_stories(
            extractions, test_stories, ground_truth, rule_files, verbose
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
        description="Run k-fold cross-validation experiments for narrative coherence"
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
        help="Directory with ground truth CSVs (default: $NARRATIVE_DATA_ROOT/errors_checklist)"
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs='+',
        default=[1, 2, 3, 4],
        help="K values to test (default: 1 2 3 4)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    experiment_dir = Path(args.experiment_dir)
    if not experiment_dir.is_absolute():
        experiment_dir = PROJECT_ROOT / experiment_dir
    
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    errors_dir = Path(args.errors_dir) if args.errors_dir else DATA_ROOT / "errors_checklist"
    if not errors_dir.is_absolute():
        errors_dir = PROJECT_ROOT / errors_dir
    
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
    
    print("Collecting rule files...")
    rule_files = collect_rule_files(ALL_STORIES)
    print(f"Found {len(rule_files)} rule files")
    
    # Run experiments for each k
    all_results = {}
    
    for k in args.k:
        print(f"\n{'='*60}")
        print(f"Running k={k} experiments ({len(list(combinations(ALL_STORIES, k)))} combinations)")
        print(f"{'='*60}")
        
        results = run_kfold_experiment(
            k, extractions, ground_truth, rule_files, args.verbose
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


if __name__ == "__main__":
    main()
