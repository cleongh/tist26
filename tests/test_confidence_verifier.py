"""
Tests for scripts/confidence_verifier.py: tier assignment, curated
world-knowledge verification, and the support-only disposition policy.
"""

from scripts.confidence_verifier import (
    Tier,
    VerifierResult,
    Disposition,
    EvidenceProfile,
    get_profile,
    assign_tier,
    extract_provenance_facts,
    compute_delta_evidence,
    WorldVerifier,
    apply_confidence_layer,
)


def _extraction(chapter, characters=None):
    return {
        "chapter": chapter,
        "extraction": {"entities": {"characters": characters or []}},
    }


def _violation(category, vtype, event_id="e1", entities=None, provenance=None, args=None):
    entities = entities or []
    v = {
        "category": category,
        "type": vtype,
        "event_id": event_id,
        "entities": entities,
        "args": args or [category, vtype, event_id, *entities],
    }
    if provenance is not None:
        v["provenance"] = provenance
    return v


def _sig(v):
    return (v["category"], v["type"]) + tuple(str(a) for a in (v.get("args") or [])[2:])


class TestEvidenceProfileRegistry:
    def test_known_absence_profiles(self):
        assert get_profile("causality", "chekhov_gun").evidence_kind == "absence"
        assert get_profile("temporal", "prerequisite_not_met").evidence_kind == "absence"

    def test_unknown_type_fails_closed_to_absence(self):
        profile = get_profile("causality", "totally_unseen_rule_type")
        assert profile.evidence_kind == "absence"
        assert profile.note == "unclassified_evidence_profile"

    def test_explicit_contradiction_profile(self):
        assert get_profile("coherence", "contradictory_state").evidence_kind == "explicit_contradiction"


class TestTierAssignment:
    def test_explicit_contradiction_two_facts_is_high(self):
        profile = EvidenceProfile("explicit_contradiction")
        tier, reasons = assign_tier(profile, ["f1", "f2"], [], False, VerifierResult.UNKNOWN)
        assert tier == Tier.HIGH
        assert any("two_explicit_facts" in r for r in reasons)

    def test_absence_only_is_low(self):
        profile = EvidenceProfile("absence")
        tier, _ = assign_tier(profile, [], [], False, VerifierResult.UNKNOWN)
        assert tier == Tier.LOW

    def test_aggregate_only_is_low(self):
        profile = EvidenceProfile("aggregate")
        tier, _ = assign_tier(profile, [], [], False, VerifierResult.UNKNOWN)
        assert tier == Tier.LOW

    def test_absence_with_explicit_reversal_upgrades_to_medium(self):
        profile = EvidenceProfile("absence")
        tier, reasons = assign_tier(profile, [], [], True, VerifierResult.UNKNOWN)
        assert tier == Tier.MEDIUM
        assert any("reversal" in r for r in reasons)

    def test_mixed_with_explicit_and_inferred_is_medium(self):
        profile = EvidenceProfile("mixed")
        tier, _ = assign_tier(profile, ["f1"], ["d1"], False, VerifierResult.UNKNOWN)
        assert tier == Tier.MEDIUM

    def test_mixed_with_reversal_and_support_is_high(self):
        profile = EvidenceProfile("mixed")
        tier, _ = assign_tier(profile, ["f1"], [], True, VerifierResult.SUPPORTS)
        assert tier == Tier.HIGH

    def test_severity_is_never_an_input(self):
        # Tier signature intentionally has no severity parameter; this test
        # documents that constraint so a future edit can't silently add one.
        import inspect
        params = inspect.signature(assign_tier).parameters
        assert "severity" not in params


class TestProvenanceAdapter:
    def test_no_provenance_key_yields_empty(self):
        v = _violation("causality", "chekhov_gun")
        assert extract_provenance_facts(v) == ([], [])

    def test_provenance_present_is_extracted(self):
        v = _violation(
            "coherence", "contradictory_state",
            provenance={"triggering_facts": ["a", "b"], "derived_facts": ["c"]},
        )
        triggering, derived = extract_provenance_facts(v)
        assert triggering == ["a", "b"]
        assert derived == ["c"]


class TestOriginalModifiedDelta:
    def test_explicit_reversal_detected(self):
        original = _extraction(1, [{"id": "mr_dawes", "state": "injured"}])
        modified = _extraction(1, [{"id": "mr_dawes", "state": "dead"}])
        has_delta, reason = compute_delta_evidence(("mr_dawes",), original, modified)
        assert has_delta is True
        assert "reversal" in reason

    def test_absence_from_original_is_not_delta_evidence(self):
        original = _extraction(1, [])
        modified = _extraction(1, [{"id": "mr_dawes", "state": "dead"}])
        has_delta, _ = compute_delta_evidence(("mr_dawes",), original, modified)
        assert has_delta is False

    def test_missing_original_chapter_is_not_delta_evidence(self):
        modified = _extraction(1, [{"id": "mr_dawes", "state": "dead"}])
        has_delta, reason = compute_delta_evidence(("mr_dawes",), None, modified)
        assert has_delta is False
        assert reason == "no_paired_original_chapter"


class TestWorldVerifier:
    def setup_method(self):
        self.verifier = WorldVerifier()

    def test_material_supports_non_edible(self):
        v = _violation("coherence", "non_edible", entities=["rock"])
        v["material"] = "stone"
        result, domain, matched = self.verifier.verify(v, None)
        assert result == VerifierResult.SUPPORTS
        assert domain == "material"
        assert matched

    def test_material_unknown_without_field(self):
        v = _violation("coherence", "non_edible")
        result, domain, _ = self.verifier.verify(v, None)
        assert result == VerifierResult.UNKNOWN
        assert domain is None

    def test_state_action_mutually_exclusive_supports(self):
        v = _violation("coherence", "contradictory_state", event_id="mr_dawes", entities=["pair(injured, dead)"])
        result, domain, matched = self.verifier.verify(v, None)
        assert result == VerifierResult.SUPPORTS
        assert domain == "state_action"
        assert matched

    def test_emotional_supports_hostile_warm_action(self):
        v = _violation(
            "emotional", "hostile_warm_action",
            event_id="violation_info(e1,agent,a,acted,comfort,toward,b,despite,hostile,established_at,0)",
        )
        result, domain, matched = self.verifier.verify(v, None)
        assert result == VerifierResult.SUPPORTS
        assert domain == "emotional"
        assert matched

    def test_spatial_affordance_possession_default_unknown_without_data(self):
        v = _violation("location", "impossible_travel")
        result, domain, _ = self.verifier.verify(v, None)
        assert result == VerifierResult.UNKNOWN
        assert domain is None

    def test_verifier_never_returns_a_new_candidate_shape(self):
        v = _violation("coherence", "non_edible")
        v["material"] = "stone"
        result, _, _ = self.verifier.verify(v, None)
        assert isinstance(result, VerifierResult)


class TestApplyConfidenceLayerPolicy:
    def test_annotate_policy_is_exact_no_op(self):
        chapter_violations = {
            1: [_violation("causality", "chekhov_gun", event_id="x1")],
            2: [_violation("coherence", "contradictory_state", event_id="x2",
                           provenance={"triggering_facts": ["a", "b"]})],
        }
        new_v, decisions = apply_confidence_layer("story", chapter_violations, _sig, policy="annotate")
        assert new_v == chapter_violations
        assert len(decisions) == 2

    def test_support_only_standalone_low_becomes_supporting_not_alert(self):
        chapter_violations = {1: [_violation("causality", "chekhov_gun", event_id="x1", entities=["lonely_item"])]}
        new_v, decisions = apply_confidence_layer("story", chapter_violations, _sig, policy="support-only")
        assert new_v[1] == []
        assert decisions[0].tier == Tier.LOW
        assert decisions[0].disposition == Disposition.SUPPORTING

    def test_support_only_high_medium_always_retained_by_default(self):
        chapter_violations = {
            1: [_violation("coherence", "contradictory_state", event_id="x1",
                            provenance={"triggering_facts": ["a", "b"]})],
        }
        new_v, decisions = apply_confidence_layer("story", chapter_violations, _sig, policy="support-only")
        assert len(new_v[1]) == 1
        assert decisions[0].disposition == Disposition.ALERT

    def test_low_corroborating_anchored_high_is_attached_not_alerted(self):
        high = _violation(
            "emotional", "relationship_action_mismatch", event_id="e1", entities=["harry", "ron"],
            provenance={"triggering_facts": ["r1", "r2"]},
        )
        low_same_entities = _violation(
            "temporal", "prerequisite_not_met", event_id="e2", entities=["harry", "ron"],
        )
        chapter_violations = {1: [high, low_same_entities]}
        new_v, decisions = apply_confidence_layer("story", chapter_violations, _sig, policy="support-only")
        low_decision = next(d for d in decisions if d.type == "prerequisite_not_met")
        assert low_decision.disposition == Disposition.SUPPORTING
        assert low_decision.corroborated_by

    def test_world_supported_low_is_promoted_to_alert(self):
        v = _violation("coherence", "non_edible", event_id="x1", entities=["rock"])
        v["material"] = "stone"
        chapter_violations = {1: [v]}
        new_v, decisions = apply_confidence_layer(
            "story", chapter_violations, _sig, policy="support-only", use_world_verifier=True,
        )
        assert len(new_v[1]) == 1
        assert decisions[0].disposition == Disposition.ALERT
        assert decisions[0].verifier_result == VerifierResult.SUPPORTS

    def test_refutation_veto_is_inert_unless_enabled(self):
        v = _violation(
            "emotional", "hostile_warm_action", event_id="violation_info(e1,agent,a,acted,attack,toward,b,despite,hostile,established_at,0)",
            provenance={"triggering_facts": ["a"]},
        )
        chapter_violations = {1: [v]}
        new_v, decisions = apply_confidence_layer(
            "story", chapter_violations, _sig, policy="support-only", use_world_verifier=True,
        )
        assert len(new_v[1]) == 1
        assert decisions[0].disposition == Disposition.ALERT
