#!/usr/bin/env python3
"""
Confidence-tiered evidence classification + curated world-knowledge
verification for existing violation candidates.

Architecture:
    RULE ENGINE      = candidate generator (unchanged)
    THIS MODULE       = evidence classification (HIGH/MEDIUM/LOW) + a
    curated-ontology verifier that only SUPPORTS/REFUTES/abstains on an
    EXISTING candidate. Neither this module nor the ontology it loads can
    create a new violation candidate.

Evidence tiers are assigned from a versioned, rule-level evidence-profile
registry (what KIND of evidence a rule's own firing logic represents --
explicit contradiction, mixed explicit+inferred, or absence/closed-world),
combined with per-candidate signals that are actually available: opt-in
engine provenance (triggering_facts/derived_facts, see
engine/event_executor.py's collect_provenance mode) and an explicit
original-vs-modified state reversal. Severity (`ViolationSeverity`) is
NEVER used to infer confidence -- it is a different, orthogonal concept.

Ground truth (errors_checklist/) is NEVER read by this module -- tiers and
verification are decided purely from the candidate's own structure, engine
provenance, paired original/modified extraction data, and the curated
ontology. Any offline TP/FP labelling belongs strictly to reporting code,
never here.

NOT MACHINE LEARNING. Nothing here is fit across stories; the ontology is a
fixed, versioned, hand-curated JSON file loaded once.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from scripts.precision_layer import (
    Candidate,
    build_candidates,
    build_conflict_components,
    default_sanitize,
    _STRUCTURAL_SCAFFOLDING_TOKENS,
)

DEFAULT_ONTOLOGY_PATH = Path(__file__).parent.parent / "rules" / "world_knowledge" / "ontology.json"


class Tier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceOrigin(str, Enum):
    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"
    ABSENCE = "ABSENCE"
    ORIGINAL_MODIFIED_DELTA = "ORIGINAL_MODIFIED_DELTA"
    WORLD_KNOWLEDGE = "WORLD_KNOWLEDGE"


class VerifierResult(str, Enum):
    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    UNKNOWN = "UNKNOWN"


class Disposition(str, Enum):
    ALERT = "ALERT"
    SUPPORTING = "SUPPORTING"
    SUPPRESSED = "SUPPRESSED"


# =============================================================================
# Evidence-profile registry -- describes what a RULE'S OWN firing logic
# represents (explicit contradiction / mixed / absence / aggregate), never
# what any specific benchmark error looks like. Unknown (category, type)
# pairs fail closed to an "unclassified" LOW profile (see get_profile()).
# =============================================================================

@dataclass(frozen=True)
class EvidenceProfile:
    evidence_kind: str  # "explicit_contradiction" | "mixed" | "absence" | "aggregate"
    note: str = ""


_EXPLICIT_CONTRADICTION = "explicit_contradiction"
_MIXED = "mixed"
_ABSENCE = "absence"
_AGGREGATE = "aggregate"

EVIDENCE_PROFILE_REGISTRY: Dict[Tuple[str, str], EvidenceProfile] = {
    ("coherence", "contradictory_state"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "two explicit incompatible states"),
    ("coherence", "impossible_self_action"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "agent==patient, explicit"),
    ("coherence", "abnormal_color"): EvidenceProfile(_MIXED, "explicit appearance value, ontology-checkable"),
    ("coherence", "appearance_emotion_mismatch"): EvidenceProfile(_MIXED, "explicit appearance+emotion, mined compatibility"),
    ("coherence", "solo_communication"): EvidenceProfile(_MIXED, "explicit dialogue event + absence of reachable listener"),
    ("coherence", "multi_signal_anomaly"): EvidenceProfile(_AGGREGATE, "chapter-level anomaly-signal count"),
    ("causality", "chekhov_gun"): EvidenceProfile(_ABSENCE, "closed-world: item never re-used"),
    ("causality", "effect_anomaly"): EvidenceProfile(_AGGREGATE, "chapter-level anomaly-signal count"),
    ("causality", "give_without_having"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit possession vs explicit give"),
    ("causality", "use_without_having"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit possession vs explicit use"),
    ("causality", "take_nonexistent"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit take of a never-introduced item"),
    ("causality", "interacting_with_dead"): EvidenceProfile(_MIXED, "explicit death state + explicit later interaction"),
    ("temporal", "prerequisite_not_met"): EvidenceProfile(_ABSENCE, "closed-world: mined prerequisite never observed"),
    ("temporal", "explicit_order_violated"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit must_precede + explicit reversal"),
    ("temporal", "ordering_violation"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit must_precede + explicit reversal"),
    ("temporal", "causal_violation"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "explicit causal_link + explicit reversal"),
    ("temporal", "sequence_anomaly"): EvidenceProfile(_AGGREGATE, "chapter-level anomaly-signal count"),
    ("location", "explicit_ubiquity"): EvidenceProfile(_EXPLICIT_CONTRADICTION, "two explicit disjoint presences"),
    ("location", "impossible_travel"): EvidenceProfile(_MIXED, "explicit presence pair + closed-world connectivity"),
    ("location", "invalid_remote"): EvidenceProfile(_MIXED, "explicit locations + missing remote-action marker"),
    ("location", "item_impossible_relocation"): EvidenceProfile(_MIXED, "explicit item locations + closed-world connectivity"),
    ("location", "item_unreachable"): EvidenceProfile(_MIXED, "explicit agent/item locations + closed-world connectivity"),
    ("location", "spatial_anomaly"): EvidenceProfile(_AGGREGATE, "chapter-level anomaly-signal count"),
    ("emotional", "relationship_action_mismatch"): EvidenceProfile(_MIXED, "explicit relationship + explicit contradicting action"),
    ("emotional", "learned_relationship_action_mismatch"): EvidenceProfile(_MIXED, "explicit relationship + mined action compatibility"),
    ("emotional", "friendly_hostile_action"): EvidenceProfile(_MIXED, "explicit relationship + explicit hostile action"),
    ("emotional", "hostile_warm_action"): EvidenceProfile(_MIXED, "explicit relationship + explicit warm action"),
    ("emotional", "friend_hostile_report"): EvidenceProfile(_MIXED, "explicit friendly relationship + explicit report action"),
}


def get_profile(category: str, vtype: str) -> EvidenceProfile:
    return EVIDENCE_PROFILE_REGISTRY.get(
        (category, vtype),
        EvidenceProfile(_ABSENCE, "unclassified_evidence_profile"),
    )


# =============================================================================
# Provenance adapter (opt-in; engine/event_executor.py's collect_provenance)
# =============================================================================

def extract_provenance_facts(violation: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Returns (triggering_facts, derived_facts) if opt-in provenance was
    collected (violation["provenance"] present), else ([], []) -- never
    guesses. Heterogeneous final-analyzer findings (e.g. chekhov_gun, which
    never carries a "provenance" sub-dict) simply yield no facts here; their
    tier comes from the ABSENCE evidence profile above instead."""
    prov = violation.get("provenance")
    if not isinstance(prov, dict):
        return [], []
    return list(prov.get("triggering_facts") or []), list(prov.get("derived_facts") or [])


# =============================================================================
# Original vs modified explicit-reversal delta
# =============================================================================

def compute_delta_evidence(
    entity_tokens: Tuple[str, ...],
    original_chapter_extraction: Optional[Dict[str, Any]],
    modified_chapter_extraction: Optional[Dict[str, Any]],
    sanitize_fn: Callable[[Any], str] = default_sanitize,
) -> Tuple[bool, str]:
    """True only when an entity referenced by this candidate has an
    EXPLICIT state/appearance/emotion value in the modified chapter that
    directly contradicts an EXPLICIT value for the SAME entity in the
    ORIGINAL chapter (both present -- absence from the original is never
    evidence of anything by itself, see module/plan design)."""
    if not original_chapter_extraction or not modified_chapter_extraction:
        return False, "no_paired_original_chapter"

    def _char_field_map(extraction: Dict[str, Any], field_name: str) -> Dict[str, str]:
        out = {}
        for char in extraction.get("extraction", {}).get("entities", {}).get("characters", []):
            cid = sanitize_fn(char.get("id"))
            val = char.get(field_name)
            if val:
                out[cid] = str(val)
        return out

    tokens = set(entity_tokens)
    for field_name in ("state", "emotion", "appearance"):
        orig_map = _char_field_map(original_chapter_extraction, field_name)
        mod_map = _char_field_map(modified_chapter_extraction, field_name)
        for cid in tokens & set(orig_map) & set(mod_map):
            if orig_map[cid] != mod_map[cid]:
                return True, f"explicit_{field_name}_reversal:{cid}:{orig_map[cid]}->{mod_map[cid]}"
    return False, "no_explicit_reversal_found"


# =============================================================================
# Tier assignment
# =============================================================================

def assign_tier(
    profile: EvidenceProfile,
    triggering_facts: List[str],
    derived_facts: List[str],
    has_delta: bool,
    world_result: VerifierResult,
) -> Tuple[Tier, List[str]]:
    """Deterministic, provenance/profile-driven tier assignment. Severity is
    never consulted. `triggering_facts`/`derived_facts` are only used to
    REFINE an explicit_contradiction/mixed profile when available -- their
    absence (provenance not collected) never downgrades a profile that is
    intrinsically explicit_contradiction, since the rule's own firing logic
    already guarantees that evidence kind."""
    reasons: List[str] = [f"profile={profile.evidence_kind} ({profile.note})"]

    if profile.evidence_kind in (_ABSENCE, _AGGREGATE):
        if has_delta:
            reasons.append("explicit_original_modified_reversal_present")
            return Tier.MEDIUM, reasons
        reasons.append("absence_or_aggregate_only")
        return Tier.LOW, reasons

    if profile.evidence_kind == _EXPLICIT_CONTRADICTION:
        if has_delta or len(triggering_facts) >= 2:
            reasons.append("two_explicit_facts_or_reversal")
            return Tier.HIGH, reasons
        reasons.append("explicit_rule_fired_single_fact_context")
        if derived_facts or world_result == VerifierResult.SUPPORTS:
            reasons.append("corroborated_by_inference_or_world_knowledge")
            return Tier.MEDIUM, reasons
        return Tier.MEDIUM, reasons  # rule itself guarantees >=1 explicit contradiction pair

    # _MIXED
    has_explicit = bool(triggering_facts) or has_delta
    has_inferred = bool(derived_facts) or world_result == VerifierResult.SUPPORTS
    if has_delta and (has_inferred or len(triggering_facts) >= 1):
        reasons.append("explicit_reversal_plus_supporting_fact")
        return Tier.HIGH, reasons
    if has_explicit and has_inferred:
        reasons.append("one_explicit_fact_plus_one_inferred_fact")
        return Tier.MEDIUM, reasons
    reasons.append("mixed_profile_without_provenance_defaults_to_medium")
    return Tier.MEDIUM, reasons


# =============================================================================
# Curated world-knowledge verifier -- SUPPORTS/REFUTES/UNKNOWN only, never
# creates a candidate. Missing ontology/extraction data is always UNKNOWN.
# =============================================================================

ALL_DOMAINS = (
    "spatial",
    "affordance",
    "possession",
    "state_action",
    "material",
    "emotional",
)


class WorldVerifier:
    def __init__(self, ontology_path: Path = DEFAULT_ONTOLOGY_PATH):
        with open(ontology_path, encoding="utf-8") as f:
            self.ontology = json.load(f)
        self.ontology_path = ontology_path

    def verify(
        self,
        violation: Dict[str, Any],
        chapter_extraction: Optional[Dict[str, Any]],
        enabled_domains: Tuple[str, ...] = ALL_DOMAINS,
    ) -> Tuple[VerifierResult, Optional[str], List[str]]:
        """Returns (result, domain_that_decided, matched_ontology_entries).
        Domains are checked in a fixed order; the first non-UNKNOWN result
        wins. Domains lacking any usable extraction field simply abstain."""
        checks = {
            "material": self._check_material,
            "state_action": self._check_state_action,
            "emotional": self._check_emotional,
            "affordance": self._check_affordance,
            "possession": self._check_possession,
            "spatial": self._check_spatial,
        }
        for domain in ("material", "state_action", "emotional", "affordance", "possession", "spatial"):
            if domain not in enabled_domains:
                continue
            result, matched = checks[domain](violation, chapter_extraction)
            if result != VerifierResult.UNKNOWN:
                return result, domain, matched
        return VerifierResult.UNKNOWN, None, []

    def _check_material(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        if violation.get("category") != "coherence" or violation.get("type") != "non_edible":
            return VerifierResult.UNKNOWN, []
        material = str(violation.get("material") or "").lower()
        props = self.ontology.get("material_properties", {})
        if material in props.get("non_edible_materials", []):
            return VerifierResult.SUPPORTS, [f"non_edible_materials:{material}"]
        if material in props.get("edible_materials", []):
            return VerifierResult.REFUTES, [f"edible_materials:{material}"]
        return VerifierResult.UNKNOWN, []

    def _check_state_action(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        if violation.get("category") != "coherence" or violation.get("type") != "contradictory_state":
            return VerifierResult.UNKNOWN, []
        pair = self._extract_pair(violation)
        if not pair:
            return VerifierResult.UNKNOWN, []
        s1, s2 = pair
        exclusive = self.ontology.get("state_incompatibility", {}).get("mutually_exclusive_states", [])
        for a, b in exclusive:
            if {s1, s2} == {a, b}:
                return VerifierResult.SUPPORTS, [f"mutually_exclusive_states:{a}/{b}"]
        return VerifierResult.UNKNOWN, []

    def _check_emotional(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        if violation.get("category") != "emotional":
            return VerifierResult.UNKNOWN, []
        rel_type, action = self._extract_relationship_action(violation)
        if not rel_type or not action:
            return VerifierResult.UNKNOWN, []
        emo = self.ontology.get("emotional_action_compatibility", {})
        if rel_type in emo.get("negative_relationship_types", []) and action in emo.get("actions_incompatible_with_negative", []):
            return VerifierResult.SUPPORTS, [f"actions_incompatible_with_negative:{action}"]
        if rel_type in emo.get("positive_relationship_types", []) and action in emo.get("actions_incompatible_with_positive", []):
            return VerifierResult.SUPPORTS, [f"actions_incompatible_with_positive:{action}"]
        return VerifierResult.UNKNOWN, []

    def _check_affordance(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        return VerifierResult.UNKNOWN, []

    def _check_possession(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        return VerifierResult.UNKNOWN, []

    def _check_spatial(self, violation, extraction) -> Tuple[VerifierResult, List[str]]:
        return VerifierResult.UNKNOWN, []

    @staticmethod
    def _extract_pair(violation: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        detail = violation.get("event_id") or ""
        entities = violation.get("entities") or []
        m = re.search(r"pair\(([^,]+),\s*([^)]+)\)", " ".join([str(detail)] + [str(e) for e in entities]))
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return None

    @staticmethod
    def _extract_relationship_action(violation: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        blob = str(violation.get("event_id") or "")
        rel_m = re.search(r"despite,?\s*([a-z_]+)", blob)
        act_m = re.search(r"acted,?\s*([a-z_]+)|social_action,?\s*([a-z_]+)", blob)
        rel = rel_m.group(1) if rel_m else None
        act = None
        if act_m:
            act = act_m.group(1) or act_m.group(2)
        return rel, act


# =============================================================================
# Corroboration + disposition policy
# =============================================================================

@dataclass
class ConfidenceDecision:
    candidate_id: str
    category: str
    type: str
    tier: Tier
    reasons: List[str]
    verifier_result: VerifierResult
    verifier_domain: Optional[str]
    verifier_matched: List[str]
    has_delta: bool
    delta_reason: str
    disposition: Disposition = Disposition.ALERT
    corroborated_by: List[str] = field(default_factory=list)


def _find_anchors(
    candidate: Candidate,
    candidates: List[Candidate],
    tiers: Dict[int, Tier],
) -> List[Candidate]:
    """HIGH/MEDIUM candidates in the SAME CHAPTER that share a non-
    scaffolding entity token with `candidate` -- deliberately NOT scoped by
    precision_layer's component_id (that clustering is per-category, so a
    LOW candidate in one category could never corroborate a HIGH/MEDIUM one
    in a different category, even though both plainly concern the same
    underlying entity)."""
    own_tokens = {t for t in candidate.entity_tokens if t not in _STRUCTURAL_SCAFFOLDING_TOKENS}
    if not own_tokens:
        return []
    anchors = []
    for other in candidates:
        if other.index == candidate.index or other.chapter != candidate.chapter:
            continue
        if tiers.get(other.index) not in (Tier.HIGH, Tier.MEDIUM):
            continue
        other_tokens = {t for t in other.entity_tokens if t not in _STRUCTURAL_SCAFFOLDING_TOKENS}
        if own_tokens & other_tokens:
            anchors.append(other)
    return anchors


def apply_confidence_layer(
    story: str,
    chapter_violations: Dict[int, List[Dict[str, Any]]],
    violation_signature_fn: Callable[[Dict[str, Any]], Tuple[Any, ...]],
    original_extractions_by_chapter: Optional[Dict[int, Dict[str, Any]]] = None,
    policy: str = "annotate",
    use_world_verifier: bool = False,
    enabled_domains: Tuple[str, ...] = ALL_DOMAINS,
    use_refutation_veto: bool = False,
    verifier: Optional[WorldVerifier] = None,
    modified_extractions_by_chapter: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[Dict[int, List[Dict[str, Any]]], List[ConfidenceDecision]]:
    """Single-story, deterministic entry point. `policy="annotate"` is a
    strict no-op (returns every candidate, unchanged membership/order);
    `policy="support-only"` applies the disposition policy documented in
    the module docstring (HIGH/MEDIUM always ALERT unless an explicitly
    enabled refutation veto fires; standalone LOW becomes SUPPORTING;
    world-supported or anchored-corroborated LOW is promoted to ALERT).
    """
    if policy not in ("annotate", "support-only"):
        raise ValueError(f"unknown policy: {policy}")

    original_extractions_by_chapter = original_extractions_by_chapter or {}
    modified_extractions_by_chapter = modified_extractions_by_chapter or {}
    if use_world_verifier and verifier is None:
        verifier = WorldVerifier()

    candidates = build_candidates(story, chapter_violations, violation_signature_fn)
    build_conflict_components(candidates)

    tiers: Dict[int, Tier] = {}
    decisions: List[ConfidenceDecision] = []

    for c in candidates:
        profile = get_profile(c.category, c.type)
        triggering, derived = extract_provenance_facts(c.raw)
        has_delta, delta_reason = compute_delta_evidence(
            c.entity_tokens,
            original_extractions_by_chapter.get(c.chapter),
            modified_extractions_by_chapter.get(c.chapter),
        )
        world_result, world_domain, world_matched = (
            verifier.verify(c.raw, modified_extractions_by_chapter.get(c.chapter), enabled_domains)
            if use_world_verifier else (VerifierResult.UNKNOWN, None, [])
        )
        tier, reasons = assign_tier(profile, triggering, derived, has_delta, world_result)
        tiers[c.index] = tier
        decisions.append(ConfidenceDecision(
            candidate_id=c.candidate_id,
            category=c.category,
            type=c.type,
            tier=tier,
            reasons=reasons,
            verifier_result=world_result,
            verifier_domain=world_domain,
            verifier_matched=world_matched,
            has_delta=has_delta,
            delta_reason=delta_reason,
        ))

    if policy == "support-only":
        for c, d in zip(candidates, decisions):
            if d.tier in (Tier.HIGH, Tier.MEDIUM):
                if use_refutation_veto and d.verifier_result == VerifierResult.REFUTES:
                    d.disposition = Disposition.SUPPRESSED
                else:
                    d.disposition = Disposition.ALERT
                continue
            # LOW
            if d.verifier_result == VerifierResult.SUPPORTS:
                d.disposition = Disposition.ALERT
                continue
            d.disposition = Disposition.SUPPORTING
            anchor_members = _find_anchors(c, candidates, tiers)
            if anchor_members:
                d.corroborated_by = [a.candidate_id for a in anchor_members]

    new_chapter_violations: Dict[int, List[Dict[str, Any]]] = {ch: [] for ch in chapter_violations}
    for c, d in zip(candidates, decisions):
        if policy == "annotate" or d.disposition == Disposition.ALERT:
            new_chapter_violations.setdefault(c.chapter, []).append(c.raw)

    return new_chapter_violations, decisions
