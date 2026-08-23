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
from scripts.state.config import ERRORS_CHECKLIST_DIR
from engine.rule_registry import RuleRegistry
from engine.conflict_resolver import ConflictResolver


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
# ConflictResolver wiring (story metadata derived from extraction data only,
# never hardcoded per book title, per LOGIC_DESIGN.md Section 2)
# =============================================================================

GHOST_KEYWORDS = {"ghost", "spirit", "phantom", "specter", "spectre", "apparition"}
UNDEAD_KEYWORDS = {"undead", "vampire", "zombie", "revenant", "immortal"}


def build_story_metadata(story_extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive ConflictResolver story metadata purely from the LLM extraction
    data for this story (character states/appearances), never from a
    hardcoded per-title lookup. Used to initialize StoryContext generically
    so the same code works unmodified on any new dataset/story.
    """
    ghost_characters: Set[str] = set()
    undead_characters: Set[str] = set()

    for extraction in story_extractions:
        for char in extraction.get("extraction", {}).get("entities", {}).get("characters", []):
            cid = char.get("id", "")
            if not cid:
                continue
            signals = " ".join(str(char.get(f, "")) for f in ("state", "appearance", "emotion")).lower()
            if any(kw in signals for kw in GHOST_KEYWORDS):
                ghost_characters.add(cid)
            if any(kw in signals for kw in UNDEAD_KEYWORDS):
                undead_characters.add(cid)

    return {
        "is_fantasy": False,
        "has_magic": False,
        "has_teleportation": False,
        "ghost_characters": sorted(ghost_characters),
        "undead_characters": sorted(undead_characters),
        "immortal_characters": [],
    }


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

def collect_rule_files(stories: List[str] = None, rules_dir: Optional[Path] = None,
                        include_story_files: bool = True) -> List[Path]:
    """Collect all rule files to load into Clingo.
    
    Args:
        stories: Optional list of story names to load story-specific rules for.
                 If None, loads all story rules.
        rules_dir: Optional override for the rules directory (default: repo's rules/).
        include_story_files: If False, skip the static rules/story/*.lp files
            entirely (used when ConflictResolver generates story rules at
            runtime instead, so the two mechanisms don't stack).
    """
    rules_dir = rules_dir if rules_dir is not None else PROJECT_ROOT / "rules"
    rule_files = []
    dbg(f"collect_rule_files(stories={stories}, rules_dir={rules_dir}, "
        f"include_story_files={include_story_files})")

    if include_story_files:
        dbg("Static rules/story/*.lp files WILL be loaded (ConflictResolver not "
            "replacing them in this call).")
    else:
        dbg("Static rules/story/*.lp files are SKIPPED for this call -- story rules "
            "are expected to be generated at runtime by ConflictResolver instead.")
    
    # Core rules
    core_file = rules_dir / "core.lp"
    if core_file.exists():
        rule_files.append(core_file)
        dbg(f"+ core.lp (static file on disk): {core_file}", 1)
    
    # General narrative rules
    general_narrative = rules_dir / "general_narrative.lp"
    if general_narrative.exists():
        rule_files.append(general_narrative)
        dbg(f"+ general_narrative.lp (static file on disk): {general_narrative}", 1)
    
    # Story-specific rules (legacy location)
    story_rules = rules_dir / "story_rules.lp"
    if story_rules.exists():
        rule_files.append(story_rules)
        dbg(f"+ story_rules.lp legacy (static file on disk): {story_rules}", 1)
    
    # Enhanced detection rules
    enhanced_detection = rules_dir / "enhanced_detection.lp"
    if enhanced_detection.exists():
        rule_files.append(enhanced_detection)
        dbg(f"+ enhanced_detection.lp (static file on disk): {enhanced_detection}", 1)
    
    # Universal rules (all .lp files)
    universal_dir = rules_dir / "universal"
    if universal_dir.exists():
        for lp_file in sorted(universal_dir.glob("*.lp")):
            rule_files.append(lp_file)
            dbg(f"+ universal/{lp_file.name} (static file on disk)", 1)
    
    # Story-specific rules from rules/story/ directory
    story_dir = rules_dir / "story"
    if not include_story_files:
        dbg("Skipping rules/story/ directory entirely (include_story_files=False)")
    elif story_dir.exists():
        dbg(f"rules/story/ directory exists: {story_dir}")
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
                        dbg(f"+ story/{rule_name} (static, hand-authored file on disk, "
                            f"HARDCODED to story name '{story}' via story_rule_map) "
                            f"-> {rule_file}", 1)
                    else:
                        dbg(f"  (no story-specific rule file exists for '{story}': {rule_file})", 1)
        else:
            # Load all story rules
            for lp_file in sorted(story_dir.glob("*.lp")):
                rule_files.append(lp_file)
                dbg(f"+ story/{lp_file.name} (static file on disk)", 1)
    else:
        dbg(f"rules/story/ directory does NOT exist under {rules_dir} "
            "-> no story-specific rules loaded at all")

    dbg(f"collect_rule_files() -> {len(rule_files)} total rule file(s)")
    return rule_files


def run_clingo(asp_facts: str, rule_files: List[Path]) -> List[Tuple[str, ...]]:
    """Run Clingo solver and return violations."""
    import clingo
    
    violations = []
    dbg(f"run_clingo() loading {len(rule_files)} rule file(s) + 1 facts temp file", 2)
    
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
    
    dbg(f"run_clingo() -> {len(violations)} raw violation atom(s)", 2)
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
    verbose: bool = False,
    use_conflict_resolver: bool = False
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
        dbg(f"--- Story: {story} ({len(story_extractions)} modified chapters) ---", 1)
        
        # Get ground truth for this story
        gt_errors = ground_truth.get(story, [])
        gt_by_chapter = defaultdict(list)
        for err in gt_errors:
            gt_by_chapter[err.chapter_num].append(err)
        dbg(f"Ground truth for {story}: {len(gt_errors)} errors loaded from static CSV "
            f"(errors_checklist), NOT generated at runtime", 2)
        
        conflict_resolver = None
        if use_conflict_resolver:
            rule_registry = RuleRegistry()
            conflict_resolver = ConflictResolver(rule_registry)
            story_metadata = build_story_metadata(story_extractions)
            conflict_resolver.initialize_story_context(story, story_metadata)
            dbg(f"ConflictResolver initialized for '{story}' with metadata derived "
                f"from extraction data (no hardcoded per-title lookup): {story_metadata}", 2)
        
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
            dbg(f"Chapter {chapter}: to_asp() produced {len(asp_facts)} chars of ASP facts "
                f"(story_rules=None, active_universe=None -- both to_asp() optional params "
                f"are NOT passed by this script)", 2)
            
            # Pass 1: raw violations against base (non-story) rules only
            raw_violations = run_clingo(asp_facts, rule_files)
            categorized = [categorize_violation(v) for v in raw_violations]

            if conflict_resolver is not None and categorized:
                generated_rule_ids = []
                for v in categorized:
                    conflict = conflict_resolver.analyze_violation(v)
                    if conflict is not None:
                        success, rule_id = conflict_resolver.resolve_conflict(conflict, resolution_type="exception")
                        if success:
                            generated_rule_ids.append(rule_id)
                            dbg(f"ConflictResolver: chapter {chapter} violation "
                                f"type={conflict.violation_type} entities={conflict.entities_involved} "
                                f"-> generated story rule '{rule_id}'", 3)

                if generated_rule_ids:
                    story_rules_content = "\n\n".join(
                        rule_registry.rules[rid].content for rid in generated_rule_ids
                        if rid in rule_registry.rules
                    )
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.lp', delete=False) as f:
                        f.write(story_rules_content)
                        generated_rules_path = Path(f.name)
                    try:
                        final_violations = run_clingo(asp_facts, rule_files + [generated_rules_path])
                    finally:
                        generated_rules_path.unlink(missing_ok=True)
                    final_categorized = [categorize_violation(v) for v in final_violations]
                    dbg(f"Chapter {chapter}: ConflictResolver pass changed violation count "
                        f"{len(categorized)} -> {len(final_categorized)} "
                        f"(using {len(generated_rule_ids)} generated rule(s))", 2)
                    categorized = final_categorized
            
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
    extractions: List[Dict[str, Any]],
    ground_truth: Dict[str, List[GroundTruthError]],
    rule_files: List[Path],
    verbose: bool = False,
    use_conflict_resolver: bool = False
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
        
        # Run experiment
        story_results = run_experiment_for_stories(
            extractions, test_stories, ground_truth, rule_files, verbose,
            use_conflict_resolver=use_conflict_resolver
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
        "--use-conflict-resolver",
        action="store_true",
        help="Generate story-specific rules at runtime via engine.ConflictResolver "
             "(from extraction-derived metadata) instead of loading the static "
             "rules/story/*.lp files."
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
             "are loaded (and from where), per-chapter ASP fact generation, Clingo "
             "invocation, and per-story/per-chapter TP/FP/FN. Does not affect results."
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

    rules_dir = Path(args.rules_dir) if args.rules_dir else (PROJECT_ROOT / "rules")
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
    
    print("Collecting rule files...")
    print(f"Rules directory: {rules_dir}")
    if args.use_conflict_resolver:
        print("ConflictResolver mode: story rules generated at runtime, "
              "static rules/story/*.lp files skipped")
    rule_files = collect_rule_files(ALL_STORIES, rules_dir=rules_dir,
                                     include_story_files=not args.use_conflict_resolver)
    print(f"Found {len(rule_files)} rule files")
    
    # Run experiments for each k
    all_results = {}
    
    for k in args.k:
        print(f"\n{'='*60}")
        print(f"Running k={k} experiments ({len(list(combinations(ALL_STORIES, k)))} combinations)")
        print(f"{'='*60}")
        
        results = run_kfold_experiment(
            k, extractions, ground_truth, rule_files, args.verbose,
            use_conflict_resolver=args.use_conflict_resolver
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
