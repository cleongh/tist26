#!/usr/bin/env python3
"""
Confidence-ranked per-chapter violation cap.

Post-hoc trimming stage: keeps at most N violations per chapter, ranked by
confidence tier (see scripts/confidence_verifier.py) with a diversity-first
selection so different error TYPES are preferred over repeats of the same
type before the cap fills. Never reads ground truth (errors_checklist/) --
tier assignment is derived purely from each violation's own rule evidence
profile and (if present) opt-in engine provenance, exactly like
scripts/confidence_verifier.py's apply_confidence_layer.

Deliberately independent of --confidence-tiers/--confidence-policy: tiers
are (re)computed fresh here so this cap can be used standalone, regardless
of whether the confidence-tier annotation/support-only stage ran.
"""

from typing import Any, Dict, List

from scripts.confidence_verifier import (
    Tier,
    VerifierResult,
    get_profile,
    assign_tier,
    extract_provenance_facts,
)

_TIER_RANK = {Tier.HIGH: 0, Tier.MEDIUM: 1, Tier.LOW: 2}


def violation_tier(violation: Dict[str, Any]) -> Tier:
    """Ground-truth-free tier lookup for a single violation dict."""
    profile = get_profile(violation.get("category", "unknown"), violation.get("type", "unknown"))
    triggering, derived = extract_provenance_facts(violation)
    tier, _ = assign_tier(profile, triggering, derived, has_delta=False, world_result=VerifierResult.UNKNOWN)
    return tier


def select_top_n_per_chapter(
    violations: List[Dict[str, Any]],
    max_per_chapter: int,
) -> List[Dict[str, Any]]:
    """Select at most `max_per_chapter` violations from one chapter's list.

    Pass 1 (diversity): the best-tier candidate for each distinct
    (category, type) pair, in tier order, so different error types are
    preferred over repeats of the same type.
    Pass 2 (fill): if slots remain (fewer distinct types than the cap),
    top up with the next-best remaining candidates regardless of type.

    Ties within the same tier keep their original relative order (stable).
    Chapters at or under the cap are returned unchanged.
    """
    if max_per_chapter <= 0 or len(violations) <= max_per_chapter:
        return list(violations)

    ranked = sorted(
        range(len(violations)),
        key=lambda i: (_TIER_RANK[violation_tier(violations[i])], i),
    )

    selected: List[int] = []
    seen_types = set()
    for i in ranked:
        if len(selected) >= max_per_chapter:
            break
        key = (violations[i].get("category", "unknown"), violations[i].get("type", "unknown"))
        if key in seen_types:
            continue
        seen_types.add(key)
        selected.append(i)

    if len(selected) < max_per_chapter:
        selected_set = set(selected)
        for i in ranked:
            if len(selected) >= max_per_chapter:
                break
            if i in selected_set:
                continue
            selected.append(i)
            selected_set.add(i)

    selected.sort()
    return [violations[i] for i in selected]


def apply_chapter_cap(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    max_per_chapter: int,
) -> Dict[int, List[Dict[str, Any]]]:
    """Apply select_top_n_per_chapter across every chapter of one story."""
    return {
        chapter: select_top_n_per_chapter(violations, max_per_chapter)
        for chapter, violations in chapter_violations.items()
    }
