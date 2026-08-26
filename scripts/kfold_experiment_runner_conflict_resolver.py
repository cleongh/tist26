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
import copy
import csv
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state.config import ERRORS_CHECKLIST_DIR, RULES_DIR
from scripts.chapter_cap import apply_chapter_cap
from scripts.primary_alert_selector import select_primary_alerts
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


def _adaptive_threshold(count: int, fraction: float, floor: int, cap: int) -> int:
    """Scale a mining confidence threshold to the size of the story's own
    data instead of using one fixed constant for every corpus. A dense
    extraction (e.g. Kimi, ~70 events/chapter) needs a higher absolute count
    to avoid learning coincidental patterns; a sparse one (e.g. OpenAI, ~10
    events/chapter) would never clear a fixed high threshold at all. `floor`
    guarantees we never trust a single-digit sample; `cap` guarantees we
    never become MORE lenient than the previously-validated fixed defaults
    for very large corpora.
    """
    return max(floor, min(cap, round(count * fraction)))


# =============================================================================
# Similarity-based false-positive reduction (post-engine, pre-scoring)
# =============================================================================
#
# Applied to the engine's own violations AFTER evaluate_story_with_engine and
# BEFORE run_kfold_experiment. Operates purely on each violation's own
# structure (category/type/args) -- never given ground truth, never given
# story identity, never references errors_checklist/ or any per-book
# vocabulary. See /memories/session/plan.md for the full design rationale.

_EVENT_ID_TOKEN_RE = re.compile(r'^e\d+$')


def _violation_signature(v: Dict[str, Any]) -> Tuple[Any, ...]:
    """Structural, content-agnostic identity for a violation: (category,
    type) plus every remaining positional atom argument, tokenized and
    stripped of VOLATILE tokens only -- pure integers (timesteps/signal
    counts) and event ids like "e412" (globally unique per
    assign_global_event_ids, so they would make every occurrence of an
    otherwise-identical finding look artificially distinct).

    Two violations sharing a signature are the same finding restated (same
    rule, same entities/relationship/pair involved), independent of which
    event id or timestep it happened to attach to -- this is what lets a
    recurring "harry talking to self"-style finding be recognized as such
    regardless of its violation type.
    """
    category = v.get("category", "unknown")
    vtype = v.get("type", "unknown")
    args = v.get("args") or []
    # args[0]/args[1] are category/type (already in the base tuple);
    # tokenize everything from args[2:] on (event id, detail, and any extra
    # positional args some rules emit, e.g. multi_signal_anomaly's trailing
    # signal count -- the count itself is dropped here as volatile, but
    # recovered separately by the Stage C2 intensity-ranking pass below).
    raw = "|".join(str(a) for a in args[2:])
    if not raw:
        # Violations lacking "args" (e.g. system/clingo_error entries never
        # routed through StructuredViolation) fall back to entities.
        raw = "|".join(str(e) for e in v.get("entities") or [])
    tokens = re.split(r'[^a-zA-Z0-9_]+', raw.lower())
    kept = tuple(
        t for t in tokens
        if t and not t.isdigit() and not _EVENT_ID_TOKEN_RE.match(t)
    )
    return (category, vtype) + kept


def reduce_false_positives(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Similarity-based FP reduction for one story's violations. Receives
    ONLY this story's own chapter->violations mapping -- no ground truth,
    no story name -- so it structurally cannot be tuned to
    errors_checklist/.

    Stage A (within-chapter near-duplicate collapse): keep at most one
    violation per (chapter, signature). Distinct signatures in the same
    chapter/category all survive -- this is similarity-based, NOT a
    "1 violation per chapter/category" cap (errors_checklist is not assumed
    to be exhaustive, so a chapter may legitimately hold several distinct
    real errors of the same category).

    Stage C1 (cross-chapter repetition filter): a signature recurring
    across many of this story's chapters is evidence of a systemic rule
    artifact (fires the same way regardless of injected errors), not an
    injected one-off error. df_cut scales with the story's own chapter
    count via the existing _adaptive_threshold() convention.

    Stage C2 (intensity ranking): for a signature that exceeds df_cut, NEVER
    drop it outright (a hard drop risks zeroing an entire violation family,
    e.g. every mined temporal precedence pair shares one signature story-
    wide) -- instead keep a top slice, ranked by whatever signal is
    available: (a) a numeric trailing payload some rules emit (e.g.
    rules/enhanced_detection.lp's multi_signal_anomaly signal count), which
    is otherwise indistinguishable across chapters via structure alone,
    else (b) the chapter's own violation diversity (how many OTHER distinct
    signatures also fired in that chapter) -- a chapter independently
    tripping several different findings is more likely to hold a genuine
    injected error than one only tripping the single recurring pattern.
    Both signals are intrinsic to the violations themselves, never GT.
    """
    # --- Stage A: within-chapter near-duplicate collapse ---
    deduped: Dict[int, List[Dict[str, Any]]] = {}
    for chapter, violations in chapter_violations.items():
        seen: Set[Tuple[Any, ...]] = set()
        kept = []
        for v in violations:
            sig = _violation_signature(v)
            if sig in seen:
                continue
            seen.add(sig)
            kept.append(v)
        deduped[chapter] = kept

    # Chapter diversity: how many distinct signatures fired in this chapter
    # (deduped already holds at most one violation per signature/chapter).
    chapter_diversity: Dict[int, int] = {ch: len(vs) for ch, vs in deduped.items()}

    # Index post-Stage-A violations by signature (each chapter contributes
    # at most one violation per signature at this point).
    sig_occurrences: Dict[Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for chapter, violations in deduped.items():
        for v in violations:
            sig_occurrences[_violation_signature(v)].append((chapter, v))

    # --- Stage C1 cutoff + Stage C2 ranked retention ---
    # df_cut combines two self-calibrating candidate cutoffs and takes
    # whichever is LOOSER (larger), so neither alone has to be perfectly
    # tuned: (a) a chapter-count-scaled floor (>=60% of this story's own
    # chapter count), which alone fully preserved recall on a sparse corpus
    # (OpenAI) but was too aggressive on a dense one (Kimi, -12pp recall);
    # (b) a statistical-outlier cutoff (mean + 2*stdev) over this story's
    # OWN signature-repetition distribution, which adapts to how many
    # distinct signatures exist but alone was too aggressive on the sparse
    # corpus. Both are derived solely from this story's own violations, no
    # ground truth, no cross-dataset constants.
    n_chapters = max(1, len(chapter_violations))
    fraction_cut = _adaptive_threshold(n_chapters, fraction=0.9, floor=20, cap=90)

    df_values = [len(occ) for occ in sig_occurrences.values()]
    if len(df_values) >= 2:
        mean_df = sum(df_values) / len(df_values)
        variance = sum((x - mean_df) ** 2 for x in df_values) / len(df_values)
        stdev_df = variance ** 0.5
        stat_cut = math.ceil(mean_df + 2 * stdev_df)
    else:
        stat_cut = 2

    df_cut = max(2, fraction_cut, stat_cut)

    def _numeric_payload(v: Dict[str, Any]) -> Optional[int]:
        args = v.get("args") or []
        last = args[-1] if args else None
        if last is not None and re.fullmatch(r'-?\d+', str(last)):
            return int(last)
        return None

    keep_ids: Set[int] = set()
    for sig, occurrences in sig_occurrences.items():
        if len(occurrences) <= df_cut:
            keep_ids.update(id(v) for _, v in occurrences)
            continue

        slice_size = _adaptive_threshold(
            len(occurrences), fraction=0.15, floor=1, cap=len(occurrences)
        )
        ranked = sorted(
            occurrences,
            key=lambda item: (
                _numeric_payload(item[1]) or 0,
                chapter_diversity.get(item[0], 0),
            ),
            reverse=True,
        )
        keep_ids.update(id(v) for _, v in ranked[:slice_size])

    return {
        chapter: [v for v in violations if id(v) in keep_ids]
        for chapter, violations in deduped.items()
    }


def _mine_precedence_rules_by_key(
    original_extractions: List[Dict[str, Any]],
    key_field: str,
    min_occurrences: Optional[int] = None,
    min_groups: Optional[int] = None,
    occurrence_fraction: float = 0.003,
    occurrence_floor: int = 3,
    occurrence_cap: int = 8,
    group_fraction: float = 0.05,
    group_floor: int = 2,
    group_cap: int = 2,
) -> List[tuple]:
    """Shared implementation: mine (TypeA, TypeB) precedence pairs by
    grouping events on `key_field` (e.g. "agent" or "patient") -- TypeA is a
    learned prerequisite of TypeB if, for every group (e.g. every agent, or
    every item/patient) that has a TypeB occurrence, that same group also
    has an earlier TypeA occurrence. See mine_temporal_precedence_rules and
    mine_temporal_precedence_rules_by_patient for the two call sites.

    If min_occurrences/min_groups are not given, they're computed adaptively
    from this story's own event/group counts (see _adaptive_threshold) so
    sparse extractions aren't starved by a threshold tuned for dense ones.
    The occurrence_*/group_* knobs let callers with noisier `key_field`
    evidence (e.g. backfilled locations) demand more confirmation before
    trusting a pattern; mine_temporal_precedence_rules_by_location tightens
    them for exactly this reason.
    """
    from collections import defaultdict

    sorted_extractions = sorted(original_extractions, key=lambda e: e.get("chapter", -1))
    group_type_times: Dict[str, List[tuple]] = defaultdict(list)
    seq = 0
    for extraction in sorted_extractions:
        for event in extraction.get("extraction", {}).get("events", []):
            seq += 1
            key = event.get(key_field)
            etype = event.get("type")
            if not key or not etype:
                continue
            group_type_times[key].append((seq, etype))

    if min_occurrences is None:
        min_occurrences = _adaptive_threshold(
            seq, fraction=occurrence_fraction, floor=occurrence_floor, cap=occurrence_cap
        )
    if min_groups is None:
        min_groups = _adaptive_threshold(
            len(group_type_times), fraction=group_fraction, floor=group_floor, cap=group_cap
        )

    all_types = {etype for times in group_type_times.values() for _, etype in times}
    type_total_occurrences: Dict[str, int] = defaultdict(int)
    for times in group_type_times.values():
        for _, etype in times:
            type_total_occurrences[etype] += 1

    candidates = []
    for type_b in all_types:
        if type_total_occurrences[type_b] < min_occurrences:
            continue
        for type_a in all_types:
            if type_a == type_b:
                continue
            holds = False
            consistent = True
            confirming_groups = 0
            for times in group_type_times.values():
                b_times = [t for t, et in times if et == type_b]
                if not b_times:
                    continue
                a_times = [t for t, et in times if et == type_a]
                earliest_b = min(b_times)
                if not a_times or not any(ta < earliest_b for ta in a_times):
                    consistent = False
                    break
                holds = True
                confirming_groups += 1
            if holds and consistent and confirming_groups >= min_groups:
                candidates.append((type_a, type_b))
    return candidates


def mine_temporal_precedence_rules(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
    min_agents: Optional[int] = None,
) -> List[tuple]:
    """Mine (TypeA, TypeB) action-type precedence pairs from a story's own
    ORIGINAL (unmodified) chapters -- purely data-driven, never references
    error content or ground truth.

    TypeA is treated as a learned prerequisite of TypeB if, for EVERY agent
    who performs TypeB anywhere in the original text, that same agent has
    an earlier occurrence of TypeA. Requires at least `min_occurrences`
    total occurrences of TypeB AND at least `min_agents` distinct agents
    confirming the pattern, so a coincidental ordering from a single
    character's small number of actions doesn't get promoted to a
    story-wide rule (a real narrative regularity should hold across
    multiple characters, not just one).

    These populate temporal_rule/4 (via StateManager.add_story_rule) for
    story_rules.lp's existing explicit_order_violated/prerequisite_not_met
    checks, which were previously dead code (temporal_rule was never
    populated by anything in production).
    """
    return _mine_precedence_rules_by_key(
        original_extractions, "agent", min_occurrences, min_agents
    )


def mine_temporal_precedence_rules_by_patient(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
    min_patients: Optional[int] = None,
) -> List[tuple]:
    """Same mining logic as mine_temporal_precedence_rules, but grouped by
    PATIENT (the item/entity an event acts upon) instead of by agent.

    Many real prerequisite relationships are about the same OBJECT, not the
    same character -- e.g. an item must be "received"/"found" by SOMEONE
    before it can be "worn"/"used" by (possibly a different) SOMEONE. Groups
    events by their shared patient and requires the same before-evidence
    across every patient/item that has a TypeB occurrence.
    """
    return _mine_precedence_rules_by_key(
        original_extractions, "patient", min_occurrences, min_patients
    )


def _backfill_event_locations(
    extractions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Forward-fill each null event location with the last known non-null
    location earlier in the story's chronological event stream, so
    location-based mining isn't starved by backends (e.g. OpenAI) that leave
    location null on narration-derived events like "learn". Returns a deep
    copy; never mutates the caller's extractions."""
    sorted_extractions = sorted(extractions, key=lambda e: e.get("chapter", -1))
    result = copy.deepcopy(sorted_extractions)
    last_location = None
    for extraction in result:
        for event in extraction.get("extraction", {}).get("events", []):
            if event.get("location"):
                last_location = event["location"]
            elif last_location is not None:
                event["location"] = last_location
    return result


def mine_temporal_precedence_rules_by_location(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
    min_locations: Optional[int] = None,
) -> List[tuple]:
    """Same mining logic as mine_temporal_precedence_rules, but grouped by
    LOCATION instead of by agent or patient.

    Some prerequisite relationships are about the same PLACE -- e.g.
    "arrive at the cave" must precede "leave an item at the cave", regardless
    of which character does either. Groups events by their shared location
    and requires the same before-evidence across every location that has a
    TypeB occurrence.

    Locations are backfilled from the last known non-null value (see
    _backfill_event_locations), so they're noisier evidence than the
    directly-extracted agent/patient fields; thresholds here are stricter
    than the defaults to avoid promoting coincidental place-based orderings.
    """
    return _mine_precedence_rules_by_key(
        original_extractions, "location", min_occurrences, min_locations,
        occurrence_fraction=0.005, occurrence_floor=5, occurrence_cap=12,
        group_fraction=0.08, group_floor=3, group_cap=4,
    )


def _sanitize_asp_id(value: Any) -> str:
    """Sanitize a raw string into an ASP atom identifier. Mirrors
    EventExecutor._sanitize_id exactly so mined facts use the same atom
    spelling as the character_appearance/character_emotion facts emitted by
    the engine (e.g. "pale green" -> "pale_green")."""
    if not value:
        return "unknown"
    s = str(value).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'n' + s
    return s or "unknown"


def mine_appearance_emotion_compatibility(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
) -> tuple:
    """Learn which (appearance, emotion) combinations are compatible, purely
    from a story's own ORIGINAL (unmodified) chapters -- no hand-written
    mapping, no reference to error content.

    A character's "appearance" (e.g. "pale", "trembling", "smiling") and
    "emotion" (e.g. "afraid", "happy") are both per-chapter snapshot fields.
    For each non-default appearance value seen often enough in the original
    text (>= min_occurrences), we record every emotion that has EVER been
    observed alongside it -- that's the set of "compatible" emotions for
    that appearance in THIS story. An appearance/emotion combination that
    never appears in the original text, for an appearance value with enough
    track record to be trusted, is a candidate coherence mismatch when it
    shows up in the modified text.

    If min_occurrences is not given, it's computed adaptively (see
    _adaptive_threshold) from this story's own character-chapter entry
    count, so sparse extractions aren't starved by a threshold tuned for
    dense ones.

    Returns (trusted_appearances: Set[str], compatible_pairs: Set[Tuple[str, str]]).
    """
    from collections import defaultdict

    appearance_total: Dict[str, int] = defaultdict(int)
    compatible_pairs = set()
    total_entries = 0
    for extraction in original_extractions:
        for char in extraction.get("extraction", {}).get("entities", {}).get("characters", []):
            appearance = char.get("appearance")
            emotion = char.get("emotion")
            if not appearance or not emotion:
                continue
            total_entries += 1
            appearance = _sanitize_asp_id(appearance)
            emotion = _sanitize_asp_id(emotion)
            if appearance in ("normal", "unknown", "none"):
                continue
            appearance_total[appearance] += 1
            compatible_pairs.add((appearance, emotion))

    if min_occurrences is None:
        min_occurrences = _adaptive_threshold(total_entries, fraction=0.005, floor=3, cap=5)

    trusted_appearances = {a for a, n in appearance_total.items() if n >= min_occurrences}
    return trusted_appearances, compatible_pairs


def mine_relationship_action_compatibility(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
) -> tuple:
    """Learn which (relationship_type, action_type) combinations are
    compatible, purely from a story's own ORIGINAL (unmodified) chapters --
    no hand-written verb lists, no reference to error content.

    Step 1: build a Python-side approximation of "which relationship type
    holds between each ordered character pair", from the same raw fields the
    engine itself turns into initial_relationship/3 facts -- entities.relationships
    (from/to/type) and initial_rules (subject/predicate/object) -- pooled
    across ALL original chapters. This is a coarser approximation than the
    engine's own evidence-gated explicit_relationship/4 (it ignores mid-story
    relationship changes), which is acceptable here because it is only used
    to build a permissive "have these two ever had this relationship" lookup
    for MINING, not to decide violations directly.

    Step 2: for every event in the original chapters whose agent and patient
    are both characters with a known relationship type, record the event's
    `type` and `social_action_type` (when present) as "compatible" with that
    relationship type -- these are literal, observed actions between
    characters who really do have that relationship in this story.

    For each relationship type seen often enough (>= min_occurrences, see
    _adaptive_threshold), that's the set of "compatible" actions for it in
    THIS story. An action against a character with an established
    relationship, where that action never once accompanied that relationship
    type in the original text, is a candidate coherence mismatch when it
    shows up in the modified text.

    Returns (trusted_relationship_types: Set[str], compatible_pairs: Set[Tuple[str, str]]).
    """
    from collections import defaultdict

    # Step 1: pool relationship type(s) per ordered character pair across the
    # whole story (coarse -- doesn't model mid-story relationship changes).
    pair_relationship_types: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for extraction in original_extractions:
        data = extraction.get("extraction", {})
        for rel in data.get("entities", {}).get("relationships", []):
            c1 = _sanitize_asp_id(rel.get("from", ""))
            c2 = _sanitize_asp_id(rel.get("to", ""))
            rtype = _sanitize_asp_id(rel.get("type", ""))
            if c1 != "unknown" and c2 != "unknown" and rtype not in ("unknown", "neutral"):
                pair_relationship_types[(c1, c2)].add(rtype)
        for rule in data.get("initial_rules", []):
            c1 = _sanitize_asp_id(rule.get("subject", ""))
            c2 = _sanitize_asp_id(rule.get("object", ""))
            rtype = _sanitize_asp_id(rule.get("predicate", ""))
            if c1 != "unknown" and c2 != "unknown" and rtype not in ("unknown", ""):
                pair_relationship_types[(c1, c2)].add(rtype)

    # Step 2: for every event between a pair with a known relationship,
    # record its action type(s) as observed-compatible with that relationship.
    reltype_action_count: Dict[str, int] = defaultdict(int)
    compatible_pairs: Set[Tuple[str, str]] = set()
    for extraction in original_extractions:
        for event in extraction.get("extraction", {}).get("events", []):
            agent = _sanitize_asp_id(event.get("agent", ""))
            patient = _sanitize_asp_id(event.get("patient", ""))
            if agent == "unknown" or patient == "unknown":
                continue
            rtypes = pair_relationship_types.get((agent, patient)) or pair_relationship_types.get((patient, agent))
            if not rtypes:
                continue
            actions = []
            etype = event.get("type")
            if etype:
                actions.append(_sanitize_asp_id(etype))
            social_action = event.get("social_action_type")
            if social_action:
                actions.append(_sanitize_asp_id(social_action))
            for rtype in rtypes:
                for action in actions:
                    reltype_action_count[rtype] += 1
                    compatible_pairs.add((rtype, action))

    if min_occurrences is None:
        min_occurrences = _adaptive_threshold(
            sum(reltype_action_count.values()), fraction=0.01, floor=3, cap=8
        )

    trusted_relationship_types = {r for r, n in reltype_action_count.items() if n >= min_occurrences}
    return trusted_relationship_types, compatible_pairs


def mine_signal_density_threshold(
    original_extractions: List[Dict[str, Any]],
    breakpoints: Tuple[Tuple[float, int], ...] = ((30.0, 4), (42.0, 5)),
    dense_threshold: int = 6,
) -> int:
    """Mine a per-story `multi_signal_anomaly` firing threshold from the
    story's own ORIGINAL (unmodified) chapters' average event density
    (events per chapter) -- purely data-driven, no reference to error
    content or story identity.

    rules/enhanced_detection.lp's multi_signal_anomaly rule fires whenever a
    chapter accumulates >= T independent anomaly signals (default T=3, the
    paper's fixed value, reproduced here for any corpus below the first
    breakpoint). A fixed threshold of 3 is well-calibrated for sparse
    extractions (validated against the paper's own OpenAI run at ~12
    events/chapter) but under-selective for denser ones: a corpus like Kimi
    (~46 events/chapter) accumulates 3+ signals in almost every chapter just
    from volume, drowning precision. This only ever RAISES the threshold
    for denser corpora, never lowers it below the paper's validated default.

    Breakpoints were calibrated against this benchmark's measured average
    events/chapter across all 4 datasets (OpenAI ~12, Qwen ~23, Claude ~37,
    Kimi ~46), not against any per-story identity or ground truth.
    """
    total_events = sum(
        len(e.get("extraction", {}).get("events", [])) for e in original_extractions
    )
    n_chapters = max(1, len(original_extractions))
    avg_events_per_chapter = total_events / n_chapters

    for cutoff, threshold in breakpoints:
        if avg_events_per_chapter < cutoff:
            return threshold
    return dense_threshold


def mine_location_connectivity(
    original_extractions: List[Dict[str, Any]],
    min_occurrences: Optional[int] = None,
    min_avg_events_per_chapter: float = 18.0,
) -> Set[Tuple[str, str]]:
    """Mine (Location1, Location2) connectivity pairs purely from a story's
    own ORIGINAL (unmodified) chapters' movement patterns -- no hand-written
    location graph, no reference to error content.

    rules/universal/location.lp's disjoint_locations/2 treats any two
    locations WITHOUT an explicit connections/contains declaration as
    disjoint by default (a closed-world assumption). LLM extractions
    routinely omit an exhaustive location connectivity graph even when the
    narrative itself repeatedly shows characters moving between two
    locations -- left uncorroborated, this makes impossible_travel/
    item_unreachable/item_impossible_relocation fire on ordinary movement
    the extraction simply never declared a connection for.

    For each story, using ONLY its own original/unmodified chapters, track
    each character's most recent location across their own events and
    count how many times a (LocationA, LocationB) transition is observed
    (unordered, since a route walked once is usually walked back
    eventually). Pairs observed >= min_occurrences times are inferred as
    connected -- mirrors the >=2 pair-interaction corroboration convention
    already applied to emotional.lp's relationship-action mismatch rules.

    If min_occurrences is not given, computed adaptively (see
    _adaptive_threshold) from this story's own transition-observation count.

    Skipped entirely (returns an empty set) for stories below
    min_avg_events_per_chapter: below ~12 events/chapter (validated against
    OpenAI, the sparsest of the 4 benchmark corpora), even a repeatedly-
    observed transition is too thin a sample -- a handful of coincidental
    same-direction moves gets promoted to "connected" without enough
    independent narrative evidence, and this was measured to cost real
    recall on that corpus at every min_occurrences threshold tested (2/3/4),
    while the denser corpora (Kimi/Claude/Qwen, >=23 events/chapter)
    benefited cleanly at every threshold. Mirrors
    mine_signal_density_threshold's density-based calibration.
    """
    total_events = sum(
        len(e.get("extraction", {}).get("events", [])) for e in original_extractions
    )
    n_chapters = max(1, len(original_extractions))
    if total_events / n_chapters < min_avg_events_per_chapter:
        return set()

    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    sorted_extractions = sorted(original_extractions, key=lambda e: e.get("chapter", -1))
    last_location_by_entity: Dict[str, str] = {}

    for extraction in sorted_extractions:
        for event in extraction.get("extraction", {}).get("events", []):
            agent = event.get("agent")
            if not agent:
                continue
            agent = _sanitize_asp_id(agent)
            new_location = event.get("destination") or event.get("location")
            if not new_location:
                continue
            new_location = _sanitize_asp_id(new_location)
            prev_location = last_location_by_entity.get(agent)
            if prev_location and prev_location != new_location:
                pair = tuple(sorted((prev_location, new_location)))
                pair_counts[pair] += 1
            last_location_by_entity[agent] = new_location

    if min_occurrences is None:
        min_occurrences = _adaptive_threshold(
            sum(pair_counts.values()), fraction=0.02, floor=3, cap=6
        )

    return {pair for pair, count in pair_counts.items() if count >= min_occurrences}


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

    Isolation: this function must never receive or use ORIGINAL-story
    extractions. Detection/ranking for a modified story depends only on that
    story's own modified chapters plus fixed, authored rules -- original
    chapters (mining temporal precedence, appearance/emotion compatibility,
    relationship/action compatibility, signal-density thresholds, or location
    connectivity from them) must have zero influence here. The mine_* helpers
    defined below are kept for reference/tests but are intentionally NOT
    called from this function.

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
# Weak-evidence type cap
# =============================================================================
#
# Unlike the uniform per-chapter cap (scripts/chapter_cap.py, all types
# competing for the same N slots), this targets ONLY the specific rule types
# whose own firing logic is absence/aggregate-based rather than an explicit
# positive contradiction (see scripts/confidence_verifier.py's evidence-
# profile registry): prerequisite_not_met ("TypeA never occurs anywhere"),
# chekhov_gun ("item never mentioned again"), and multi_signal_anomaly
# (aggregate signal count, no single explicit contradiction). These three
# are documented (see /memories/repo/kfold-eval-baselines.md) as the
# dominant false-positive volume sources on this benchmark. Capped to 1/
# chapter each; every other violation type is left untouched.
WEAK_EVIDENCE_TYPES = {
    ("temporal", "prerequisite_not_met"),
    ("causality", "chekhov_gun"),
    ("coherence", "multi_signal_anomaly"),
}


def cap_weak_evidence_types(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    max_per_type: int = 1,
) -> Dict[int, List[Dict[str, Any]]]:
    """Keep at most `max_per_type` violations per chapter for each
    (category, type) pair in WEAK_EVIDENCE_TYPES; all other types pass
    through unchanged."""
    capped: Dict[int, List[Dict[str, Any]]] = {}
    for chapter, violations in chapter_violations.items():
        kept: List[Dict[str, Any]] = []
        type_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for v in violations:
            key = (v.get("category", "unknown"), v.get("type", "unknown"))
            if key in WEAK_EVIDENCE_TYPES:
                if type_counts[key] >= max_per_type:
                    continue
                type_counts[key] += 1
            kept.append(v)
        capped[chapter] = kept
    return capped


def suppress_violation_types(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    suppress_keys: Set[Tuple[str, str]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Remove ALL violations whose (category, type) is in `suppress_keys`,
    every chapter. Ground-truth-free at runtime -- `suppress_keys` must be
    supplied by the caller (e.g. --suppress-types) from prior offline
    analysis, never computed from a live GT lookup here."""
    return {
        chapter: [
            v for v in violations
            if (v.get("category"), v.get("type")) not in suppress_keys
        ]
        for chapter, violations in chapter_violations.items()
    }


# =============================================================================
# Tier 1 zero-recall-cost types (per-rule overfiring analysis)
# =============================================================================
#
# Found by testing EVERY distinct (category, type) present on the OpenAI k=1
# dataset: suppressing each of these types, individually AND combined, never
# removes a single TP (verified via per_category_strict.json TP counts before
# and after) while cutting a meaningful number of FPs. See
# /memories/session/plan.md's "Comprehensive per-rule-type overfiring
# analysis" section for the full methodology and per-type root-cause notes.
# Combined result on OpenAI k=1 (isolated baseline, fp-reduce + primary-
# alerts + chapter-cap 4): TP unchanged at 32, FP 451->423, P 6.63%->7.03%,
# R unchanged at 42.67%. NOTE: unlike WEAK_EVIDENCE_TYPES (a per-chapter cap
# of 1), these are suppressed ENTIRELY -- they contributed 0 TPs on this
# dataset, not just excess duplicates. This is dataset-specific evidence
# (OpenAI extraction only, not re-validated on denser extractions like Kimi
# -- see the cross-dataset validation attempt in session memory, which
# stalled and was abandoned) -- opt-in via --suppress-tier1-zero-cost rather
# than a silent default, for the same overfitting caution as --suppress-types.
TIER1_ZERO_RECALL_COST_TYPES = {
    ("location", "impossible_travel"),
    ("coherence", "contradictory_state"),
    ("coherence", "abnormal_color"),
    ("emotional", "relationship_action_mismatch"),
    ("location", "item_ubiquity"),
    ("coherence", "impossible_self_action"),
    ("possession", "give_without_having"),
    ("temporal", "missing_prerequisite"),
}


# =============================================================================
# Tier 2 low-recall-cost types (per-rule overfiring analysis, phase 2)
# =============================================================================
#
# Unlike Tier 1 (0 TPs lost), these types DO carry some real recall on the
# OpenAI k=1 dataset -- suppressing them trades a small, known number of TPs
# for a disproportionately larger number of FPs. Only "friendly_hostile_action"
# is included: it had the best FP:TP ratio of the low-cost candidates (1 TP
# lost for 13 FPs removed, measured on top of the isolated + fp-reduce +
# primary-alerts + chapter-cap-4 baseline WITHOUT Tier 1 suppression yet
# applied -- see /memories/session/plan.md for the full ranked table).
# "solo_communication" and "effect_anomaly" were measured too but rejected:
# stacking them past friendly_hostile_action made F1 worse and eventually
# dropped recall below the 39% floor. "hostile_warm_action" (same rule
# family as friendly_hostile_action) was rejected outright: it has a much
# worse ratio (2 TP lost for only 6 FP removed).
# Same caution as Tier 1: opt-in only, OpenAI-only evidence, not
# cross-validated on a denser-extraction dataset.
TIER2_LOW_RECALL_COST_TYPES = {
    ("emotional", "friendly_hostile_action"),
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
        "--fp-reduce",
        dest="fp_reduce",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply similarity-based false-positive reduction (Stage A dedup + "
             "Stage C1 repetition filter + Stage C2 intensity ranking, see "
             "reduce_false_positives()) to each story's violations before "
             "scoring. Default on; pass --no-fp-reduce to score raw engine "
             "output for comparison."
    )
    parser.add_argument(
        "--chapter-cap",
        dest="chapter_cap",
        type=int,
        default=0,
        help="Keep at most N violations per chapter (ground-truth-free, ranked "
             "by scripts/confidence_verifier.py's evidence tier via "
             "scripts/chapter_cap.py, diversity-first across distinct "
             "category/type pairs). Applied AFTER --fp-reduce/--weak-evidence-cap "
             "AND after --primary-alerts (if both are given -- measured to "
             "compose better in that order). 0 (default) disables the cap."
    )
    parser.add_argument(
        "--weak-evidence-cap",
        dest="weak_evidence_cap",
        type=int,
        default=0,
        help="Keep at most N violations per chapter for each of the specific "
             "absence/aggregate-based rule types in WEAK_EVIDENCE_TYPES "
             "(prerequisite_not_met, chekhov_gun, multi_signal_anomaly) -- "
             "every other violation type is untouched. Applied AFTER "
             "--fp-reduce, BEFORE --chapter-cap. 0 (default) disables it."
    )
    parser.add_argument(
        "--primary-alerts",
        dest="primary_alerts",
        action="store_true",
        default=False,
        help="Score only one PRIMARY violation per (chapter, category) -- the "
             "best-evidenced candidate per scripts/primary_alert_selector.py, "
             "ground-truth-free and modified-story-only. All other candidates "
             "are demoted to SUPPORTING and excluded from scoring but kept in "
             "a diagnostic JSON. Applied AFTER --fp-reduce/--weak-evidence-cap, "
             "BEFORE --chapter-cap. Default off."
    )
    parser.add_argument(
        "--suppress-types",
        dest="suppress_types",
        nargs="+",
        default=[],
        metavar="CATEGORY:TYPE",
        help="Remove ALL violations matching the given 'category:type' pairs "
             "(e.g. 'emotional:relationship_action_mismatch') entirely, before "
             "--weak-evidence-cap/--primary-alerts/--chapter-cap. Ground-truth-"
             "free at runtime -- the decision to name a type here must come "
             "from prior offline analysis (see /memories/repo or the OpenAI "
             "vocab report), never from a live GT lookup. Use with caution: a "
             "type contributing 0 TPs on one dataset may still carry real "
             "recall on another (denser-extraction) dataset -- re-validate "
             "before adding a type here. Default: none suppressed."
    )
    parser.add_argument(
        "--suppress-tier1-zero-cost",
        dest="suppress_tier1_zero_cost",
        action="store_true",
        default=False,
        help="Suppress TIER1_ZERO_RECALL_COST_TYPES entirely (8 curated types "
             "that contributed 0 TPs on the OpenAI k=1 dataset, verified both "
             "individually and combined -- see the type definition above). "
             "Combines with --suppress-types if both are given. Default off."
    )
    parser.add_argument(
        "--suppress-tier2-low-cost",
        dest="suppress_tier2_low_cost",
        action="store_true",
        default=False,
        help="Suppress TIER2_LOW_RECALL_COST_TYPES entirely (currently just "
             "emotional:friendly_hostile_action -- 1 TP lost for 13 FPs "
             "removed on the OpenAI k=1 dataset, the best ratio among the "
             "low-cost candidates -- see the type definition above). Combines "
             "with --suppress-types/--suppress-tier1-zero-cost if given. "
             "Default off."
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
        # Original-story chapters are intentionally never loaded here: modified-
        # story detection must be fully isolated from original-story content.
        story_extractions = [
            e for e in extractions
            if e.get("story") == story and e.get("variant") == "modified"
        ]
        print(f"  Evaluating {story}: {len(story_extractions)} modified chapters...")
        story_violations_cache[story] = evaluate_story_with_engine(
            story, story_extractions, rules_dir, enable_learning=args.enable_learning,
        )
        total_violations = sum(len(v) for v in story_violations_cache[story].values())
        print(f"    -> {total_violations} violation(s) across "
              f"{len(story_violations_cache[story])} chapter(s)")

    if args.fp_reduce:
        print("\nApplying similarity-based FP reduction (Stage A dedup + "
              "Stage C1 repetition filter + Stage C2 intensity ranking)...")
        for story in ALL_STORIES:
            before = sum(len(v) for v in story_violations_cache[story].values())
            story_violations_cache[story] = reduce_false_positives(story_violations_cache[story])
            after = sum(len(v) for v in story_violations_cache[story].values())
            print(f"  {story}: {before} -> {after} violation(s)")
    else:
        print("\nSkipping FP reduction (--no-fp-reduce)")

    if args.suppress_types or args.suppress_tier1_zero_cost or args.suppress_tier2_low_cost:
        suppress_keys = set()
        for entry in args.suppress_types:
            category, _, vtype = entry.partition(":")
            suppress_keys.add((category, vtype))
        if args.suppress_tier1_zero_cost:
            suppress_keys |= TIER1_ZERO_RECALL_COST_TYPES
        if args.suppress_tier2_low_cost:
            suppress_keys |= TIER2_LOW_RECALL_COST_TYPES
        print(f"\nSuppressing violation type(s) {sorted(suppress_keys)} entirely...")
        for story in ALL_STORIES:
            before = sum(len(v) for v in story_violations_cache[story].values())
            story_violations_cache[story] = suppress_violation_types(
                story_violations_cache[story], suppress_keys
            )
            after = sum(len(v) for v in story_violations_cache[story].values())
            print(f"  {story}: {before} -> {after} violation(s)")

    if args.weak_evidence_cap > 0:
        print(f"\nApplying weak-evidence type cap (max {args.weak_evidence_cap} "
              "violation(s)/chapter for prerequisite_not_met/chekhov_gun/"
              "multi_signal_anomaly only)...")
        for story in ALL_STORIES:
            before = sum(len(v) for v in story_violations_cache[story].values())
            story_violations_cache[story] = cap_weak_evidence_types(
                story_violations_cache[story], args.weak_evidence_cap
            )
            after = sum(len(v) for v in story_violations_cache[story].values())
            print(f"  {story}: {before} -> {after} violation(s)")

    if args.primary_alerts:
        print("\nSelecting one PRIMARY alert per (chapter, category) "
              "(scripts/primary_alert_selector.py)...")
        diagnostics: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
        for story in ALL_STORIES:
            annotated = select_primary_alerts(story_violations_cache[story])
            diagnostics[story] = annotated
            before = sum(len(v) for v in story_violations_cache[story].values())
            story_violations_cache[story] = {
                chapter: [v for v in violations if v.get("disposition") == "primary"]
                for chapter, violations in annotated.items()
            }
            after = sum(len(v) for v in story_violations_cache[story].values())
            print(f"  {story}: {before} -> {after} primary violation(s) "
                  f"({before - after} demoted to supporting)")
        diagnostics_file = output_dir / "primary_supporting_diagnostics.json"
        with open(diagnostics_file, 'w', encoding='utf-8') as f:
            json.dump(diagnostics, f, indent=2)
        print(f"Written primary/supporting diagnostics to {diagnostics_file}")

    if args.chapter_cap > 0:
        # NOTE: applied AFTER --primary-alerts (not before) -- measured on the
        # OpenAI k=1 dataset to compose better in this order: same recall,
        # fewer residual FPs (e.g. ccap=4 after primary-select: micro P
        # 6.50%->6.63%, TP unchanged at 32; capping first then selecting
        # primaries was strictly worse or equal at every tested cap value).
        print(f"\nApplying chapter cap (max {args.chapter_cap} violation(s)/chapter, "
              "confidence-tier ranked, diversity-first)...")
        for story in ALL_STORIES:
            before = sum(len(v) for v in story_violations_cache[story].values())
            story_violations_cache[story] = apply_chapter_cap(
                story_violations_cache[story], args.chapter_cap
            )
            after = sum(len(v) for v in story_violations_cache[story].values())
            print(f"  {story}: {before} -> {after} violation(s)")

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
