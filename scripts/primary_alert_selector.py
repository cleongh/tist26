"""
Primary-alert selector (ground-truth-free, modified-story-only).

Groups a story's violations by (chapter, category) and selects exactly one
PRIMARY alert per non-empty group -- the single best-evidenced candidate --
while every other candidate in that group is kept as SUPPORTING. Only
PRIMARY alerts are meant to be scored; SUPPORTING alerts remain available for
diagnostics/reporting.

Ranking uses only fields already present on each violation dict (as produced
by engine.event_executor.StructuredViolation.to_dict()): whether the
violation is anchored to a concrete event (as opposed to a chapter-level
aggregate rule, whose event_id is the literal "chapter"), whether it has
source text, and how many concrete entities it names. No ground truth, no
original-story data, and no story/chapter/character names are consulted.
"""

from typing import Any, Dict, List, Tuple

# Chapter-level aggregate rule types (rules/enhanced_detection.lp) whose
# event_id is the literal "chapter" rather than a real event id -- these
# carry the weakest evidence (no single anchoring event/entity) and should
# never outrank an anchored violation for the same chapter/category.
AGGREGATE_EVENT_ID = "chapter"


def _is_anchored(violation: Dict[str, Any]) -> bool:
    """True if this violation is tied to a concrete event rather than being
    a chapter-wide aggregate finding."""
    return violation.get("event_id") not in (None, "", AGGREGATE_EVENT_ID)


def _rank_key(violation: Dict[str, Any], original_index: int) -> Tuple:
    """Lower is better. Ranking signals, all derived from the violation
    itself (no ground truth, no original-story data):
      1. Anchored to a concrete event beats chapter-level aggregate.
      2. Non-empty source text beats missing source text.
      3. More concrete entities named beats fewer.
      4. Stable original order as the final tie-break.
    """
    anchored = 0 if _is_anchored(violation) else 1
    has_source = 0 if violation.get("source_text") else 1
    entity_count = len(violation.get("entities") or [])
    return (anchored, has_source, -entity_count, original_index)


def select_primary_alerts(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Given one story's chapter_num -> violations mapping, return a new
    mapping of the same shape where each violation dict has an added
    "disposition" key ("primary" or "supporting") and, for primaries, a
    "rank_reason" key. Exactly one "primary" is selected per non-empty
    (chapter, category) group; the group's remaining candidates are
    "supporting". No violations are dropped.
    """
    result: Dict[int, List[Dict[str, Any]]] = {}

    for chapter, violations in chapter_violations.items():
        by_category: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
        for idx, v in enumerate(violations):
            by_category.setdefault(v.get("category"), []).append((idx, v))

        annotated: List[Dict[str, Any]] = [None] * len(violations)
        for category, indexed in by_category.items():
            ranked = sorted(indexed, key=lambda pair: _rank_key(pair[1], pair[0]))
            primary_idx, primary_violation = ranked[0]
            for idx, v in indexed:
                v = dict(v)
                if idx == primary_idx:
                    v["disposition"] = "primary"
                    v["rank_reason"] = (
                        "anchored_event" if _is_anchored(primary_violation)
                        else "sole_candidate_aggregate"
                    )
                else:
                    v["disposition"] = "supporting"
                annotated[idx] = v

        result[chapter] = annotated

    return result


def primary_only(
    chapter_violations: Dict[int, List[Dict[str, Any]]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Convenience wrapper: select primaries, then return only the primary
    violations per chapter (for scoring), stripped of no keys -- disposition
    metadata is kept so downstream code can still tell primaries apart if
    reused elsewhere."""
    annotated = select_primary_alerts(chapter_violations)
    return {
        chapter: [v for v in violations if v.get("disposition") == "primary"]
        for chapter, violations in annotated.items()
    }
