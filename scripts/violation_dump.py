"""
Violation dump schema + writer for the offline FP-analysis pipeline (see
/memories/session/plan.md "Offline FP Analysis"). Strictly a diagnostic
artifact: never consumed by any runtime/inference code path. Opt-in only
via --dump-violations; the default pipeline never imports or calls this
module's writer.

Leaf module: imports from scripts.precision_layer / scripts.conflict_episodes
for read-only reuse (component/state helpers), never the other way around.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.conflict_episodes import anchor_keys_for_entities, state_value_at


def assign_dump_id(
    violation: Dict[str, Any],
    dataset: str,
    story: str,
    chapter: int,
    idx: int,
) -> str:
    """Stamp a stable candidate_id onto the violation dict itself (mutates
    in place) the first time it's seen (at the 'raw' stage). Since
    reduce_false_positives()/apply_precision_layer() filter lists without
    copying the underlying dicts, this id survives unchanged into the
    'fp_reduced'/'exp1' stages, letting the same candidate be traced
    across all three."""
    if "_dump_id" not in violation:
        violation["_dump_id"] = f"{dataset}:{story}:ch{chapter}:{idx}"
    return violation["_dump_id"]


def build_state_context(
    violation: Dict[str, Any],
    chapter: int,
    timeline: Dict[Any, List[Any]],
    sanitize_fn: Callable[[Any], str],
) -> Dict[str, Any]:
    """Best-effort state_context: most recent value at/before `chapter` for
    every structural state_key whose entity is referenced by this
    violation's own `entities` list (StructuredViolation.to_dict() folds
    what used to be a separate "detail" argument into `entities`)."""
    entities = list(violation.get("entities") or [])
    tokens = tuple(sanitize_fn(e) for e in entities if e)
    keys = anchor_keys_for_entities(tokens, timeline)
    context: Dict[str, Any] = {}
    for key in keys:
        value = state_value_at(timeline, key, chapter)
        if value is not None:
            context["/".join(key)] = value
    return context


def build_dump_record(
    violation: Dict[str, Any],
    dataset: str,
    story: str,
    chapter: int,
    stage: str,
    idx: int,
    component_info: Optional[Dict[int, Dict[str, Any]]] = None,
    candidate: Optional[Any] = None,
    state_timeline: Optional[Dict[Any, List[Any]]] = None,
    sanitize_fn: Optional[Callable[[Any], str]] = None,
) -> Dict[str, Any]:
    """Build one JSONL record. Only fields the engine/pipeline can
    reliably provide are included -- see plan.md Phase B4. `candidate`
    (a precision_layer.Candidate) and `component_info` are only available
    at the 'exp1' stage; state_context/state_timeline require the
    story's own extraction data and are optional at every stage.

    NOTE: every stage's violation dict is StructuredViolation.to_dict()'s
    output (there is no separate raw check_with_clingo dict anywhere in
    this pipeline by the time evaluate_story_with_engine returns it), so
    the event id lives under "event_id" and provenance detail is nested
    under a "provenance" sub-dict, not top-level "event"/"detail"/
    "triggering_facts" keys.
    """
    candidate_id = assign_dump_id(violation, dataset, story, chapter, idx)
    provenance = violation.get("provenance") or {}
    record: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "dataset": dataset,
        "story": story,
        "chapter": chapter,
        "stage": stage,
        "category": violation.get("category", "unknown"),
        "type": violation.get("type", "unknown"),
        "rule": violation.get("rule") or f"{violation.get('category', 'unknown')}/{violation.get('type', 'unknown')}",
        "event_id": violation.get("event_id", ""),
        "entities": violation.get("entities", []),
        "severity": violation.get("severity"),
        "source_text": violation.get("source_text", ""),
        "triggering_facts": provenance.get("triggering_facts", []),
        "derived_facts": provenance.get("derived_facts", []),
        "provenance_roots": provenance.get("provenance_roots", []),
        "inference_depth": provenance.get("inference_depth", 0),
    }
    if candidate is not None and component_info is not None:
        comp = component_info.get(candidate.component_id, {})
        record["conflict_component_id"] = candidate.component_id
        record["breakpoint_candidate"] = candidate.features.get("is_breakpoint") == 1.0
        record["component_size"] = comp.get("size")
        record["distance_from_first_conflict"] = candidate.features.get("distance_from_first_conflict")
        record["independent_evidence"] = candidate.features.get("independent_evidence")
    if state_timeline is not None and sanitize_fn is not None:
        record["state_context"] = build_state_context(violation, chapter, state_timeline, sanitize_fn)
    return record


class DumpWriter:
    """One JSONL file per dataset, opened lazily, closed at the end of a
    run. Diagnostic-only artifact -- never read by production code."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._handles: Dict[str, Any] = {}

    def write(self, dataset: str, record: Dict[str, Any]) -> None:
        handle = self._handles.get(dataset)
        if handle is None:
            handle = open(self.output_dir / f"violations_{dataset}.jsonl", "w", encoding="utf-8")
            self._handles[dataset] = handle
        handle.write(json.dumps(record) + "\n")

    def write_manifest(self, manifest: Dict[str, Any]) -> None:
        with open(self.output_dir / "run_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
