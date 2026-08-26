#!/usr/bin/env python3
"""
Precision layer: a deterministic, story-local diagnostic/clustering stage
for narrative violation candidates produced by the ASP rule engine.

Architecture philosophy:
    RULE ENGINE = candidate generator
    PRECISION LAYER = structural diagnostics (clustering + breakpoint
    detection only -- NOT a filter)
This module groups candidates into contradiction episodes and tags each
candidate's episode role (breakpoint / downstream repeat / singleton), but
never suppresses anything on that basis -- ablation testing (see
/memories/repo/kfold-eval-baselines.md) showed that every further
suppression mechanism tried (downstream-consequence suppression,
explanation-event gate, contradiction-strength scoring, independent-
evidence gate) cost real recall for little or inconsistent precision gain,
so they were removed. This is a separate, purely-additive stage: it never
modifies rule semantics, never touches the original/clean narrative text,
and can be fully disabled without touching the existing
`reduce_false_positives()` pipeline in
kfold_experiment_runner_conflict_resolver.py.

NOT MACHINE LEARNING. Nothing in this module is fit across stories -- every
threshold used here is an ADAPTIVE CUTOFF computed from that SAME story's
own candidates, independently, story by story. There is no cross-story
training, no learned weights, no model persisted between runs. (An earlier
version of this precision layer used a cross-story-trained logistic-
regression ranker; it was measured to overfit catastrophically with only 5
stories per dataset -- see /memories/session -- and was replaced by this
deterministic design.)

NO IMPORTS from kfold_experiment_runner_conflict_resolver.py (that module
imports this one; this stays a leaf to avoid a circular import). Anything
this module needs from the caller (violation-signature function) is passed
in as a parameter -- dependency injection, not import.

HONEST APPROXIMATION (the engine exposes only final `violation/N` atoms,
not an ASP justification/proof tree -- true provenance chains are not
reconstructable without new engine instrumentation): "Contradiction
episodes" / conflict components are approximated structurally: candidates
are grouped via union-find, within the same category, connected whenever
they share an entity token that is "rare enough" GLOBALLY across this
story's candidates (document frequency below a self-calibrated cutoff --
the same style of adaptive threshold already used by
reduce_false_positives()). This groups different rule types firing about
the same underlying entity/state into one episode, while generic
ASP-schema scaffolding tokens (agent, patient, toward...) never drive a
merge. This is a generic structural proxy for "same underlying
contradiction", not a reconstruction of the solver's actual derivation.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# =============================================================================
# Local, self-contained helpers (deliberately NOT imported from the runner
# module, to avoid a circular import -- see module docstring).
# =============================================================================

def _local_adaptive_threshold(count: int, fraction: float, floor: int, cap: int) -> int:
    """Mirrors kfold_experiment_runner_conflict_resolver._adaptive_threshold:
    scale a threshold to the size of the data at hand instead of a single
    fixed constant, floor/cap-bounded."""
    return max(floor, min(cap, round(count * fraction)))


def default_sanitize(value: Any) -> str:
    """Mirrors EventExecutor._sanitize_id / the runner's _sanitize_asp_id,
    duplicated locally so this module has no hard dependency on the caller's
    exact sanitizer. Callers may pass their own via `sanitize_fn` params for
    byte-identical atom spelling."""
    if not value:
        return "unknown"
    s = str(value).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'n' + s
    return s or "unknown"


# ASP-schema argument-position words -- these are the ENGINE'S OWN predicate
# argument labels (e.g. `violation_info(E, agent, Agent, acted, Type, toward,
# Patient, despite, RelType, established_at, T)`), not narrative content.
# They recur in nearly every candidate of every category purely because
# they're part of the argument template, so they must never drive an
# entity-based cluster merge. This is schema metadata about the rule
# vocabulary itself (same category as filtering "e123" event ids), NOT
# knowledge of any specific benchmark error/character/story.
_STRUCTURAL_SCAFFOLDING_TOKENS = frozenset({
    "agent", "patient", "toward", "despite", "acted", "established_at",
    "social_action", "pair", "violation_info", "expected_after", "at_times",
    "order", "precedes_cause", "at", "in_event", "requires_copresence",
    "moved_from", "to", "via_event", "no_path", "travels_from", "and",
    "last_at", "item", "signals", "chapter", "reported",
    "despite_friendly_relationship", "location_signals", "temporal_signals",
    "causality_signals",
})


# =============================================================================
# Candidate representation
# =============================================================================

@dataclass
class Candidate:
    """One violation candidate with structural provenance/features attached.

    `raw` keeps the original violation dict untouched so this layer is
    purely additive -- nothing about the underlying dict's schema changes.
    """
    index: int
    story: str
    chapter: int
    category: str
    type: str
    signature: Tuple[Any, ...]
    entity_tokens: Tuple[str, ...]
    numeric_payload: Optional[int]
    raw: Dict[str, Any]
    features: Dict[str, float] = field(default_factory=dict)
    component_id: Optional[int] = None
    decision: str = "PENDING"   # RETAIN / SUPPRESS / PENDING
    reason: str = ""

    @property
    def candidate_id(self) -> str:
        return f"{self.story}:ch{self.chapter}:{self.index}"


def build_candidates(
    story: str,
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    violation_signature_fn: Callable[[Dict[str, Any]], Tuple[Any, ...]],
) -> List[Candidate]:
    """Wrap one story's chapter->violations dict into Candidate objects,
    in chapter order (stable, deterministic indexing)."""
    candidates: List[Candidate] = []
    idx = 0
    for chapter in sorted(chapter_violations):
        for v in chapter_violations[chapter]:
            sig = violation_signature_fn(v)
            args = v.get("args") or []
            payload: Optional[int] = None
            if args:
                last = args[-1]
                if re.fullmatch(r'-?\d+', str(last)):
                    payload = int(last)
            candidates.append(Candidate(
                index=idx,
                story=story,
                chapter=chapter,
                category=v.get("category", "unknown"),
                type=v.get("type", "unknown"),
                signature=sig,
                entity_tokens=tuple(sig[2:]),
                numeric_payload=payload,
                raw=v,
            ))
            idx += 1
    return candidates


# =============================================================================
# Union-Find
# =============================================================================

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# =============================================================================
# Stage 1 -- Contradiction-episode clustering
# =============================================================================

def build_conflict_components(candidates: List[Candidate]) -> None:
    """Cluster candidates into conflict episodes (components), mutating
    component_id in place. Connects two candidates of the SAME category
    whenever they share an entity token that is NOT ASP-schema scaffolding
    (see _STRUCTURAL_SCAFFOLDING_TOKENS -- a fixed, generic list of the
    engine's own predicate argument-position words, not benchmark error
    knowledge) and whose document frequency -- measured across ALL of this
    story's candidates, regardless of category -- is below a self-
    calibrated, deliberately loose cutoff used only as a secondary safety
    net for scaffolding-like tokens not on the fixed list.

    The scaffolding-word filter does the primary work deliberately: pure
    frequency alone cannot distinguish "a genuinely recurring entity that
    IS this whole episode's subject" (which should legitimately have high
    document frequency within its own small episode) from "generic
    argument-position noise" -- both look identical to a frequency-only
    cutoff when a story/category has few candidates.

    A candidate that shares no clustering-eligible token with anything else
    becomes its own singleton episode -- uniqueness is never by itself a
    reason to discard; it just means an empty (size-1) conflict episode.
    """
    global_token_df: Dict[str, int] = defaultdict(int)
    for c in candidates:
        for t in set(c.entity_tokens):
            global_token_df[t] += 1
    # Loose secondary safety net: only catches scaffolding-like tokens NOT
    # already on the fixed list, so it must not fire on a real recurring
    # entity even when it makes up 100% of a small category (hence a much
    # higher floor/fraction than a primary filter would use).
    df_cut = _local_adaptive_threshold(len(candidates), fraction=0.6, floor=20, cap=200)

    by_category: Dict[str, List[Candidate]] = defaultdict(list)
    for c in candidates:
        by_category[c.category].append(c)

    next_component_id = 0
    for cands in by_category.values():
        n = len(cands)
        if n == 0:
            continue
        local_index = {c.index: i for i, c in enumerate(cands)}
        uf = _UnionFind(n)

        token_to_locals: Dict[str, List[int]] = defaultdict(list)
        for c in cands:
            for t in set(c.entity_tokens):
                if t in _STRUCTURAL_SCAFFOLDING_TOKENS:
                    continue
                if global_token_df[t] <= df_cut:
                    token_to_locals[t].append(local_index[c.index])

        for locs in token_to_locals.values():
            if len(locs) < 2:
                continue
            first = locs[0]
            for other in locs[1:]:
                uf.union(first, other)

        root_to_component: Dict[int, int] = {}
        for c in cands:
            root = uf.find(local_index[c.index])
            if root not in root_to_component:
                root_to_component[root] = next_component_id
                next_component_id += 1
            c.component_id = root_to_component[root]


def compute_component_features(candidates: List[Candidate]) -> Dict[int, Dict[str, Any]]:
    """Aggregate episode-level statistics. `independent_evidence` is the
    number of DISTINCT RULE TYPES firing within the episode -- see module
    docstring approximation #3 -- deliberately NOT a chapter or occurrence
    count, so an episode consisting of 50 repeats of one single rule type
    still reports independent_evidence=1 (one detection mechanism, however
    many times it fired), while an episode where 2 different rules agree
    reports 2."""
    members_by_component: Dict[int, List[Candidate]] = defaultdict(list)
    for c in candidates:
        members_by_component[c.component_id].append(c)

    info: Dict[int, Dict[str, Any]] = {}
    for cid, members in members_by_component.items():
        chapters = sorted(m.chapter for m in members)
        info[cid] = {
            "size": len(members),
            "n_types": len({m.type for m in members}),
            "n_entities": len({t for m in members for t in m.entity_tokens}),
            "first_chapter": chapters[0],
            "last_chapter": chapters[-1],
            "duration": chapters[-1] - chapters[0],
        }
    return info


# =============================================================================
# Stage 2 -- Breakpoint detection + downstream/new-contradiction features
# (feature computation only -- nothing here suppresses candidates yet)
# =============================================================================

FEATURE_NAMES = [
    "is_breakpoint",
    "distance_from_first_conflict",
    "component_size",
    "independent_evidence",
]


def compute_candidate_features(
    candidates: List[Candidate],
    component_info: Dict[int, Dict[str, Any]],
) -> None:
    """Populate breakpoint/episode features: is_breakpoint and
    distance_from_first_conflict come straight from the episode's own
    first_chapter (computed already); component_size/independent_evidence
    are episode-level stats copied onto each member for convenience."""
    for c in candidates:
        comp = component_info[c.component_id]
        c.features["is_breakpoint"] = 1.0 if c.chapter == comp["first_chapter"] else 0.0
        c.features["distance_from_first_conflict"] = float(c.chapter - comp["first_chapter"])
        c.features["component_size"] = float(comp["size"])
        c.features["independent_evidence"] = float(comp["n_types"])


def apply_ablation_defaults(
    candidates: List[Candidate],
    use_conflict_clustering: bool,
    use_breakpoint: bool,
) -> None:
    """Ablation switches. When conflict clustering is disabled, every
    candidate becomes its own singleton episode (so breakpoint/independent-
    evidence stats all degrade to their neutral defaults). When breakpoint
    detection alone is disabled (clustering still active), force every
    candidate to look like a fresh/new occurrence -- isolates what
    breakpoint detection itself contributes, independent of clustering."""
    if not use_conflict_clustering:
        for i, c in enumerate(candidates):
            c.component_id = -(i + 1)  # unique per candidate
    if not use_breakpoint:
        for c in candidates:
            c.features["is_breakpoint"] = 1.0
            c.features["distance_from_first_conflict"] = 0.0


# =============================================================================
# Decision pass -- diagnostic only, never suppresses (see module docstring:
# every suppression mechanism previously tried here was measured to cost
# real recall for little/inconsistent precision gain).
# =============================================================================


def decide_candidates(
    candidates: List[Candidate],
    component_info: Dict[int, Dict[str, Any]],
) -> None:
    """Tags every candidate's episode role for diagnostics, but always
    retains it -- this stage does not filter anything."""
    for c in candidates:
        comp = component_info[c.component_id]
        is_multi_member_episode = comp["size"] > 1
        is_breakpoint = c.features["is_breakpoint"] == 1.0

        if not is_multi_member_episode:
            episode_role = "singleton"
        elif is_breakpoint:
            episode_role = "breakpoint"
        else:
            episode_role = "downstream_repeat"

        c.decision = "RETAIN"
        c.reason = f"episode role: {episode_role} (diagnostic only, not suppressed)"


# =============================================================================
# Diagnostics / explainability
# =============================================================================

def explain_candidate(c: Candidate, component_info: Dict[int, Dict[str, Any]]) -> str:
    """Human-readable explanation block."""
    comp = component_info.get(c.component_id, {})
    lines = [
        f"Candidate: {c.candidate_id}",
        f"  Category: {c.category}",
        f"  Rule: {c.type}",
        f"  Chapter: {c.chapter}",
        f"  Conflict episode: {c.component_id} (size={comp.get('size', 1)}, "
        f"first_chapter={comp.get('first_chapter', c.chapter)})",
        f"  Breakpoint: {'yes' if c.features.get('is_breakpoint') == 1.0 else 'no'}",
        f"  Independent rule types in episode: {int(c.features.get('independent_evidence', 0))}",
        f"  Decision: {c.decision}",
        f"  Reason: {c.reason}",
    ]
    return "\n".join(lines)


# =============================================================================
# Top-level driver
# =============================================================================

def apply_precision_layer(
    story: str,
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    story_extractions_modified: List[Dict[str, Any]],
    violation_signature_fn: Callable[[Dict[str, Any]], Tuple[Any, ...]],
    sanitize_fn: Callable[[Any], str] = default_sanitize,
    use_conflict_clustering: bool = True,
    use_breakpoint: bool = True,
) -> Tuple[Dict[int, List[Dict[str, Any]]], List[Candidate], Dict[int, Dict[str, Any]]]:
    """End-to-end, single-story, deterministic entry point. No ground
    truth is consulted anywhere in this function. `story_extractions_modified`/
    `sanitize_fn` are accepted but unused -- kept for call-site compatibility
    with callers that still pass them.

    Returns (new_chapter_violations, all_candidates, component_info) --
    the candidates/component_info are returned too so callers can print
    diagnostics/explanations without recomputing them. This stage never
    suppresses candidates (see module docstring), so
    new_chapter_violations is always equivalent to chapter_violations.
    """
    candidates = build_candidates(story, chapter_violations, violation_signature_fn)
    build_conflict_components(candidates)
    component_info = compute_component_features(candidates)
    compute_candidate_features(candidates, component_info)

    apply_ablation_defaults(candidates, use_conflict_clustering, use_breakpoint)
    # Re-derive component_info after ablation may have rewritten component_id.
    component_info = compute_component_features(candidates)
    if not use_conflict_clustering:
        compute_candidate_features(candidates, component_info)
        if not use_breakpoint:
            apply_ablation_defaults(candidates, use_conflict_clustering, use_breakpoint)

    decide_candidates(candidates, component_info)

    new_chapter_violations: Dict[int, List[Dict[str, Any]]] = {
        chapter: [] for chapter in chapter_violations
    }
    for c in candidates:
        if c.decision == "RETAIN":
            new_chapter_violations.setdefault(c.chapter, []).append(c.raw)

    return new_chapter_violations, candidates, component_info
