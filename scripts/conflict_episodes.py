#!/usr/bin/env python3
"""
Experimental conflict-episode layer -- built ON TOP OF the existing Exp1
precision layer (scripts/precision_layer.py), NOT a replacement for it.

Core idea (per design spec): a rule firing is EVIDENCE, not automatically a
separate error. Given a conflict episode (Exp1's conflict-component
clustering + breakpoint), later candidates in the same episode are only
counted as new violations when they introduce a genuinely NEW underlying
contradiction; otherwise they are supporting evidence for the
already-counted episode.

Status: EXPERIMENTAL, default OFF. Does not modify precision_layer.py or
change any existing default CLI behavior. Fully ablatable via three
independent flags (use_episode_lifecycle / use_resolution_tracking /
use_new_conflict_detection). See /memories/session/plan.md.

NOT MACHINE LEARNING. No cross-story fitting, no learned weights. Every
threshold/comparison here is derived structurally from THIS story's own
extraction data (never errors_checklist/, never original/clean text -- only
the same modified-chapter extraction data the rule engine itself already
consumed).

NO rule-name-equality shortcuts: "new contradiction" is decided by
comparing structured STATE (character/item state, appearance, emotion,
relationships) before vs. after, never by comparing violation `type`
strings against each other or against any hardcoded list.

Leaf-ish module: imports precision_layer's Exp1 output (candidates,
clustering) to avoid duplicating clustering logic, but NOT
kfold_experiment_runner_conflict_resolver.py (avoids the circular import;
that module imports this one).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from scripts.precision_layer import (
    Candidate,
    apply_precision_layer,
    default_sanitize,
)

StateKey = Tuple[str, ...]

# =============================================================================
# Phase 1 -- State timeline (built ONLY from this story's own modified-
# chapter extraction data, the same data the rule engine already saw --
# never original/clean text, never errors_checklist/).
# =============================================================================

def build_state_timeline(
    story_extractions_modified: List[Dict[str, Any]],
    sanitize_fn: Callable[[Any], str] = default_sanitize,
) -> Dict[StateKey, List[Tuple[int, str]]]:
    """Generic structural state_key -> [(chapter, value), ...] (chapter-
    sorted). state_key shapes are fixed and generic (never a specific
    character/story name):
        ("character_state", char_id)
        ("character_emotion", char_id)
        ("character_appearance", char_id)
        ("item_state", item_id)
        ("relationship", from_id, to_id)
    """
    raw: Dict[StateKey, List[Tuple[int, str]]] = defaultdict(list)
    for extraction in story_extractions_modified:
        chapter = extraction.get("chapter", -1)
        entities = extraction.get("extraction", {}).get("entities", {})
        for char in entities.get("characters", []):
            cid = sanitize_fn(char.get("id"))
            if char.get("state"):
                raw[("character_state", cid)].append((chapter, str(char["state"])))
            if char.get("emotion"):
                raw[("character_emotion", cid)].append((chapter, str(char["emotion"])))
            if char.get("appearance"):
                raw[("character_appearance", cid)].append((chapter, str(char["appearance"])))
        for item in entities.get("items", []):
            iid = sanitize_fn(item.get("id"))
            if item.get("state"):
                raw[("item_state", iid)].append((chapter, str(item["state"])))
        for rel in entities.get("relationships", []):
            frm = sanitize_fn(rel.get("from"))
            to = sanitize_fn(rel.get("to"))
            if rel.get("type"):
                raw[("relationship", frm, to)].append((chapter, str(rel["type"])))

    timeline: Dict[StateKey, List[Tuple[int, str]]] = {}
    for key, entries in raw.items():
        timeline[key] = sorted(entries, key=lambda e: e[0])
    return timeline


def state_value_at(
    timeline: Dict[StateKey, List[Tuple[int, str]]],
    key: StateKey,
    chapter: int,
) -> Optional[str]:
    """Most recent observed value for `key` at or before `chapter`, or None
    if never observed by that point."""
    entries = timeline.get(key)
    if not entries:
        return None
    value = None
    for ch, val in entries:
        if ch > chapter:
            break
        value = val
    return value


def _state_key_entities(key: StateKey) -> Set[str]:
    """Which sanitized entity ids a state_key is "about" -- used to match
    a candidate's entity_tokens against relevant state keys."""
    if key[0] == "relationship":
        return {key[1], key[2]}
    return {key[1]}


def anchor_keys_for_entities(
    entity_tokens: Tuple[str, ...],
    timeline: Dict[StateKey, List[Tuple[int, str]]],
) -> Set[StateKey]:
    """All state_keys in the timeline that are "about" at least one of the
    given (already-sanitized) entity tokens."""
    tokens = set(entity_tokens)
    if not tokens:
        return set()
    return {key for key in timeline if _state_key_entities(key) & tokens}


# =============================================================================
# Phase 2 -- Conflict episode representation
# =============================================================================

@dataclass
class ConflictEpisode:
    episode_id: str
    candidate_ids: List[int] = field(default_factory=list)
    entity_keys: Set[str] = field(default_factory=set)
    state_keys: Set[StateKey] = field(default_factory=set)
    event_keys: Set[str] = field(default_factory=set)
    provenance_roots: Set[str] = field(default_factory=set)
    first_chapter: int = 0
    last_chapter: int = 0
    breakpoint_candidate_id: Optional[int] = None
    primary_candidate_id: Optional[int] = None
    supporting_candidate_ids: List[int] = field(default_factory=list)
    lifecycle: str = "NEW"  # NEW / ACTIVE / RESOLVED / RECURRED


def _new_episode(episode_id: str, primary: Candidate, timeline, lifecycle: str) -> ConflictEpisode:
    anchors = anchor_keys_for_entities(primary.entity_tokens, timeline)
    ep = ConflictEpisode(
        episode_id=episode_id,
        candidate_ids=[primary.index],
        entity_keys=set(primary.entity_tokens),
        state_keys=anchors,
        event_keys=set(),
        provenance_roots={primary.type},
        first_chapter=primary.chapter,
        last_chapter=primary.chapter,
        breakpoint_candidate_id=primary.index,
        primary_candidate_id=primary.index,
        lifecycle=lifecycle,
    )
    return ep


# =============================================================================
# Phase 3 -- New-vs-existing contradiction (structural, no rule-name
# equality; ambiguity always resolves toward NOT suppressing).
# =============================================================================

def introduces_new_contradiction(
    candidate: Candidate,
    episode: ConflictEpisode,
    timeline: Dict[StateKey, List[Tuple[int, str]]],
) -> bool:
    """True if `candidate` is a materially distinct contradiction rather
    than a consequence of `episode`'s already-established conflict.

    Never compares violation `type` strings for equality. Decided purely
    from structured state:
      1. candidate touches a state_key episode has never seen -> new.
      2. candidate shares anchor keys with episode, but at least one of
         those keys' VALUE changed since the episode's last attribution
         -> new (the underlying situation moved on).
      3. candidate shares NO evaluable anchor keys at all with the episode
         (e.g. an item with no state field ever recorded) -> no positive
         evidence exists to call it "the same conflict", so treat as new
         (recall-safety: ambiguity never causes suppression).
    Returns False (=> may become SUPPORTING) only when every shared anchor
    key is verifiably unchanged since the episode's last attribution.
    """
    candidate_keys = anchor_keys_for_entities(candidate.entity_tokens, timeline)
    new_keys = candidate_keys - episode.state_keys
    if new_keys:
        return True
    shared_keys = candidate_keys & episode.state_keys
    if not shared_keys:
        return True
    for key in shared_keys:
        before = state_value_at(timeline, key, episode.last_chapter)
        after = state_value_at(timeline, key, candidate.chapter)
        if before != after:
            return True
    return False


def conflict_resolved(
    episode: ConflictEpisode,
    timeline: Dict[StateKey, List[Tuple[int, str]]],
    candidate: Candidate,
) -> bool:
    """Generic state-transition check: has ANY of the episode's own anchor
    keys changed value between the episode's first_chapter and this
    candidate's chapter? No hardcoded event types (no "resurrection",
    "travel", etc.) -- purely a before/after value comparison."""
    for key in episode.state_keys:
        before = state_value_at(timeline, key, episode.first_chapter)
        after = state_value_at(timeline, key, candidate.chapter)
        if before != after:
            return True
    return False


# =============================================================================
# Phase 4 -- Episode lifecycle + splitting (per original Exp1 component)
# =============================================================================

def _process_component(
    members: List[Candidate],
    timeline: Dict[StateKey, List[Tuple[int, str]]],
    component_id: int,
    use_resolution_tracking: bool,
    use_new_conflict_detection: bool,
) -> Tuple[List[ConflictEpisode], Dict[int, str], Dict[int, str]]:
    """Process one Exp1 conflict component in chronological order,
    producing possibly-several ConflictEpisode splits, plus per-candidate
    role ("PRIMARY"/"SUPPORTING"/"NEW_EPISODE") and reason."""
    ordered = sorted(members, key=lambda c: (c.chapter, c.index))
    breakpoint_candidate = next((c for c in ordered if c.features.get("is_breakpoint") == 1.0), ordered[0])

    episodes: List[ConflictEpisode] = []
    roles: Dict[int, str] = {}
    reasons: Dict[int, str] = {}

    episode = _new_episode(f"{component_id}-0", breakpoint_candidate, timeline, lifecycle="NEW")
    episodes.append(episode)
    roles[breakpoint_candidate.index] = "PRIMARY"
    reasons[breakpoint_candidate.index] = "episode breakpoint"
    split_count = 0

    for c in ordered:
        if c.index == breakpoint_candidate.index:
            continue

        if use_resolution_tracking and conflict_resolved(episode, timeline, c):
            episode.lifecycle = "RESOLVED"
            split_count += 1
            episode = _new_episode(
                f"{component_id}-{split_count}", c, timeline,
                lifecycle="RECURRED" if split_count > 0 else "NEW",
            )
            episodes.append(episode)
            roles[c.index] = "PRIMARY"
            reasons[c.index] = "new episode: previous conflict resolved by intervening state change"
            continue

        if use_new_conflict_detection and introduces_new_contradiction(c, episode, timeline):
            split_count += 1
            new_episode = _new_episode(f"{component_id}-{split_count}", c, timeline, lifecycle="NEW")
            episodes.append(new_episode)
            roles[c.index] = "NEW_EPISODE"
            reasons[c.index] = "materially distinct contradiction (new/changed anchor state)"
            episode = new_episode
            continue

        # SUPPORTING: consequence of the currently active episode.
        episode.candidate_ids.append(c.index)
        episode.supporting_candidate_ids.append(c.index)
        episode.entity_keys |= set(c.entity_tokens)
        episode.provenance_roots.add(c.type)
        episode.last_chapter = c.chapter
        if episode.lifecycle == "NEW":
            episode.lifecycle = "ACTIVE"
        roles[c.index] = "SUPPORTING"
        reasons[c.index] = "consequence of already-active unresolved conflict"

    return episodes, roles, reasons


def build_episodes(
    candidates: List[Candidate],
    timeline: Dict[StateKey, List[Tuple[int, str]]],
    use_episode_lifecycle: bool,
    use_resolution_tracking: bool,
    use_new_conflict_detection: bool,
) -> Tuple[List[ConflictEpisode], Dict[int, str], Dict[int, str]]:
    """Top-level driver: groups candidates by their Exp1 component_id, then
    runs the per-component lifecycle/splitting pass. If
    use_episode_lifecycle is False, this is a pure grouping/diagnostic pass
    -- every candidate is PRIMARY, nothing is ever demoted (Experiment B:
    "grouping only", a measured no-op vs Exp1)."""
    by_component: Dict[int, List[Candidate]] = defaultdict(list)
    for c in candidates:
        by_component[c.component_id].append(c)

    all_episodes: List[ConflictEpisode] = []
    all_roles: Dict[int, str] = {}
    all_reasons: Dict[int, str] = {}

    if not use_episode_lifecycle:
        for component_id, members in by_component.items():
            ordered = sorted(members, key=lambda c: (c.chapter, c.index))
            ep = ConflictEpisode(
                episode_id=str(component_id),
                candidate_ids=[c.index for c in ordered],
                entity_keys={t for c in ordered for t in c.entity_tokens},
                state_keys=set(),
                provenance_roots={c.type for c in ordered},
                first_chapter=ordered[0].chapter,
                last_chapter=ordered[-1].chapter,
                breakpoint_candidate_id=ordered[0].index,
                primary_candidate_id=None,
                lifecycle="NEW",
            )
            all_episodes.append(ep)
            for c in ordered:
                all_roles[c.index] = "PRIMARY"
                all_reasons[c.index] = "episode lifecycle disabled (diagnostic grouping only)"
        return all_episodes, all_roles, all_reasons

    for component_id, members in by_component.items():
        episodes, roles, reasons = _process_component(
            members, timeline, component_id,
            use_resolution_tracking=use_resolution_tracking,
            use_new_conflict_detection=use_new_conflict_detection,
        )
        all_episodes.extend(episodes)
        all_roles.update(roles)
        all_reasons.update(reasons)

    return all_episodes, all_roles, all_reasons


# =============================================================================
# Top-level driver
# =============================================================================

def apply_conflict_episode_layer(
    story: str,
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    story_extractions_modified: List[Dict[str, Any]],
    violation_signature_fn: Callable[[Dict[str, Any]], Tuple[Any, ...]],
    sanitize_fn: Callable[[Any], str] = default_sanitize,
    use_conflict_clustering: bool = True,
    use_breakpoint: bool = True,
    use_episode_lifecycle: bool = True,
    use_resolution_tracking: bool = True,
    use_new_conflict_detection: bool = True,
) -> Tuple[Dict[int, List[Dict[str, Any]]], List[Candidate], List[ConflictEpisode], Dict[str, Any]]:
    """End-to-end, single-story driver. Reuses Exp1's clustering/breakpoint
    (via apply_precision_layer) rather than duplicating it; Exp1's own
    RETAIN-only decision is ignored here -- this layer makes its own
    PRIMARY/SUPPORTING/NEW_EPISODE call per candidate. Only PRIMARY and
    NEW_EPISODE candidates survive into the final output; SUPPORTING
    candidates are dropped from scoring but remain attached to their
    episode for diagnostics.
    """
    _, candidates, _ = apply_precision_layer(
        story, chapter_violations, story_extractions_modified,
        violation_signature_fn, sanitize_fn,
        use_conflict_clustering=use_conflict_clustering,
        use_breakpoint=use_breakpoint,
    )

    timeline = build_state_timeline(story_extractions_modified, sanitize_fn)
    episodes, roles, reasons = build_episodes(
        candidates, timeline,
        use_episode_lifecycle=use_episode_lifecycle,
        use_resolution_tracking=use_resolution_tracking,
        use_new_conflict_detection=use_new_conflict_detection,
    )

    for c in candidates:
        c.decision = "RETAIN" if roles.get(c.index) in ("PRIMARY", "NEW_EPISODE") else "SUPPRESS"
        c.reason = reasons.get(c.index, "")

    new_chapter_violations: Dict[int, List[Dict[str, Any]]] = {
        chapter: [] for chapter in chapter_violations
    }
    for c in candidates:
        if c.decision == "RETAIN":
            new_chapter_violations.setdefault(c.chapter, []).append(c.raw)

    n_primary = sum(1 for r in roles.values() if r == "PRIMARY")
    n_supporting = sum(1 for r in roles.values() if r == "SUPPORTING")
    n_new_episode = sum(1 for r in roles.values() if r == "NEW_EPISODE")
    n_resolved = sum(1 for e in episodes if e.lifecycle == "RESOLVED")
    n_recurred = sum(1 for e in episodes if e.lifecycle == "RECURRED")
    stats = {
        "exp1_candidates": len(candidates),
        "n_episodes": len(episodes),
        "avg_candidates_per_episode": (len(candidates) / len(episodes)) if episodes else 0.0,
        "n_primary": n_primary,
        "n_supporting": n_supporting,
        "n_new_episode": n_new_episode,
        "n_resolved": n_resolved,
        "n_recurred": n_recurred,
        "final_candidates": n_primary + n_new_episode,
    }

    return new_chapter_violations, candidates, episodes, stats


def explain_episode(episode: ConflictEpisode, candidates_by_index: Dict[int, Candidate]) -> str:
    """Human-readable diagnostic block for one episode."""
    primary = candidates_by_index.get(episode.primary_candidate_id) if episode.primary_candidate_id is not None else None
    lines = [
        f"Episode {episode.episode_id} (lifecycle={episode.lifecycle})",
        f"  chapters: {episode.first_chapter}-{episode.last_chapter}",
        f"  primary: {primary.candidate_id if primary else 'n/a'}",
        f"  supporting: {len(episode.supporting_candidate_ids)} candidate(s)",
        f"  provenance roots: {sorted(episode.provenance_roots)}",
        f"  state keys tracked: {len(episode.state_keys)}",
    ]
    return "\n".join(lines)
