"""
Tests for the evidence checklist module.

Validates that:
1. PredicateType covers all needed predicate types
2. ERROR_CATEGORY_CHECKLISTS is comprehensive
3. check_predicate_presence correctly identifies predicates
4. evaluate_checklist produces accurate evaluations
5. Checklist results integrate with detectability classification
"""

import pytest

from scripts.evaluation.evidence_checklist import (
    PredicateType,
    EvidenceRequirement,
    ErrorCategoryChecklist,
    ChecklistItem,
    ChecklistEvaluation,
    ERROR_CATEGORY_CHECKLISTS,
    check_predicate_presence,
    evaluate_checklist,
    get_checklist_for_category,
    get_all_categories,
    format_checklist_evaluation,
)


# =============================================================================
# Test PredicateType Enum
# =============================================================================


class TestPredicateType:
    """Tests for PredicateType enum."""

    def test_all_predicate_types_defined(self):
        """Verify all expected predicate types exist."""
        expected = {
            "RELATIONSHIP",
            "SOCIAL_ACTION_TYPE",
            "TEMPORAL_CONSTRAINT",
            "AFTER_LINK",
            "PRESENT",
            "EVENT_LOCATION",
            "CHARACTER_STATE",
            "CHARACTER_APPEARANCE",
            "CHARACTER_EMOTION",
            "CARRIES",
            "ITEM_STATE",
            "EVENT_TYPE",
        }
        actual = {pt.name for pt in PredicateType}
        assert expected.issubset(actual), f"Missing: {expected - actual}"

    def test_predicate_type_values_are_strings(self):
        """All predicate types should have string values matching ASP predicates."""
        for pt in PredicateType:
            assert isinstance(pt.value, str)
            assert len(pt.value) > 0


# =============================================================================
# Test ERROR_CATEGORY_CHECKLISTS
# =============================================================================


class TestErrorCategoryChecklists:
    """Tests for the ERROR_CATEGORY_CHECKLISTS dictionary."""

    def test_all_expected_categories_exist(self):
        """Verify all expected error categories are defined."""
        expected_categories = {
            "emotional_inconsistency",
            "temporal_violation",
            "location_violation",
            "appearance_inconsistency",
        }
        actual = set(ERROR_CATEGORY_CHECKLISTS.keys())
        assert expected_categories.issubset(actual), f"Missing: {expected_categories - actual}"

    def test_each_category_has_requirements(self):
        """Each category should have at least one mandatory or alternative requirement."""
        for category, checklist in ERROR_CATEGORY_CHECKLISTS.items():
            has_requirements = (
                len(checklist.mandatory_predicates) > 0
                or len(checklist.alternative_predicates) > 0
            )
            assert has_requirements, f"{category} has no requirements"

    def test_checklist_descriptions_not_empty(self):
        """Each checklist should have a description."""
        for category, checklist in ERROR_CATEGORY_CHECKLISTS.items():
            assert len(checklist.description) > 0, f"{category} has empty description"

    def test_emotional_inconsistency_checklist(self):
        """Verify emotional_inconsistency has correct requirements."""
        checklist = ERROR_CATEGORY_CHECKLISTS["emotional_inconsistency"]
        assert PredicateType.RELATIONSHIP in checklist.mandatory_predicates
        # Should have alternative predicates for social_action_type or event_type
        assert len(checklist.alternative_predicates) > 0

    def test_temporal_violation_checklist(self):
        """Verify temporal_violation has correct requirements."""
        checklist = ERROR_CATEGORY_CHECKLISTS["temporal_violation"]
        # Should require temporal_constraint or after_link
        temporal_predicates = {
            PredicateType.TEMPORAL_CONSTRAINT,
            PredicateType.AFTER_LINK,
        }
        all_predicates = set(checklist.mandatory_predicates)
        all_predicates.update(checklist.alternative_predicates)
        assert temporal_predicates.intersection(all_predicates)


# =============================================================================
# Test check_predicate_presence
# =============================================================================


class TestCheckPredicatePresence:
    """Tests for check_predicate_presence function."""

    def test_finds_relationship_predicate(self):
        """Should find relationship predicates in extraction result."""
        extraction_result = {
            "entities": {
                "relationships": [
                    {"source": "harry", "target": "hermione", "type": "friend"}
                ]
            },
            "events": [],
        }
        found, source = check_predicate_presence(
            PredicateType.RELATIONSHIP, extraction_result
        )
        assert found is True
        assert source is not None

    def test_finds_temporal_constraint(self):
        """Should find temporal_constraint predicates."""
        extraction_result = {
            "entities": {},
            "events": [],
            "temporal_constraints": [
                {"constraint": "morning", "event": "e1"}
            ],
        }
        found, source = check_predicate_presence(
            PredicateType.TEMPORAL_CONSTRAINT, extraction_result
        )
        assert found is True

    def test_finds_after_link(self):
        """Should find after_link predicates."""
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1", "after": "e0"}],
        }
        found, source = check_predicate_presence(
            PredicateType.AFTER_LINK, extraction_result
        )
        assert found is True

    def test_finds_present_predicate(self):
        """Should find present predicates from locations."""
        extraction_result = {
            "entities": {
                "locations": [{"name": "hogwarts", "type": "school"}]
            },
            "events": [],
        }
        found, source = check_predicate_presence(
            PredicateType.PRESENT, extraction_result
        )
        assert found is True

    def test_finds_event_location(self):
        """Should find event location predicates."""
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1", "location": "great_hall"}],
        }
        found, source = check_predicate_presence(
            PredicateType.EVENT_LOCATION, extraction_result
        )
        assert found is True

    def test_finds_carries_predicate(self):
        """Should find carries predicates from give/take events."""
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1", "type": "give"}],
        }
        found, source = check_predicate_presence(
            PredicateType.CARRIES, extraction_result
        )
        assert found is True

    def test_finds_character_appearance(self):
        """Should find character appearance traits."""
        extraction_result = {
            "entities": {
                "characters": [{"name": "harry", "appearance": "scarred"}]
            },
            "events": [],
        }
        found, source = check_predicate_presence(
            PredicateType.CHARACTER_APPEARANCE, extraction_result
        )
        assert found is True

    def test_finds_social_action_type(self):
        """Should find social_action_type in events."""
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }
        found, source = check_predicate_presence(
            PredicateType.SOCIAL_ACTION_TYPE, extraction_result
        )
        assert found is True

    def test_returns_false_for_missing_predicate(self):
        """Should return False when predicate is not present."""
        extraction_result = {
            "entities": {
                "characters": [{"name": "harry"}]
            },
            "events": [],
        }
        found, source = check_predicate_presence(
            PredicateType.RELATIONSHIP, extraction_result
        )
        assert found is False
        assert source is None

    def test_handles_empty_extraction_result(self):
        """Should handle empty extraction result gracefully."""
        found, source = check_predicate_presence(
            PredicateType.RELATIONSHIP, {}
        )
        assert found is False

    def test_handles_none_extraction_result(self):
        """Should handle None extraction result gracefully."""
        # Note: check_predicate_presence expects a dict, None is an error
        # This test verifies behavior - actual code may require dict
        try:
            found, source = check_predicate_presence(
                PredicateType.RELATIONSHIP, None
            )
            assert found is False
        except (AttributeError, TypeError):
            # Also acceptable - None is not a valid input
            pass


# =============================================================================
# Test evaluate_checklist
# =============================================================================


class TestEvaluateChecklist:
    """Tests for evaluate_checklist function."""

    def test_returns_evaluation_for_unknown_category(self):
        """Should return evaluation with unknown category message."""
        result = evaluate_checklist(
            error_category="unknown_category",
            chapter_id="chapter_1",
            extraction_result={},
        )
        # Returns evaluation with justification explaining unknown category
        assert result is not None
        assert result.overall_satisfied is False
        assert "unknown" in result.justification.lower()

    def test_all_requirements_met(self):
        """Should evaluate as all requirements met."""
        extraction_result = {
            "entities": {
                "relationships": [{"source": "a", "target": "b", "type": "friend"}],
            },
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }
        result = evaluate_checklist(
            error_category="emotional_inconsistency",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        assert result.overall_satisfied is True

    def test_missing_mandatory_predicate(self):
        """Should detect missing mandatory predicate."""
        extraction_result = {
            "entities": {},  # Missing relationships - mandatory for emotional_inconsistency
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }
        result = evaluate_checklist(
            error_category="emotional_inconsistency",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        assert result.mandatory_satisfied is False
        assert len(result.missing_mandatory) > 0

    def test_missing_alternative_predicates(self):
        """Should detect when no alternative is present."""
        extraction_result = {
            "entities": {
                "relationships": [{"source": "a", "target": "b", "type": "friend"}],
            },
            # Events without social_action_type or event_type values
            "events": [],
        }
        result = evaluate_checklist(
            error_category="emotional_inconsistency",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        # Alternative predicates not satisfied when no events exist
        assert result.alternative_satisfied is False

    def test_items_contain_predicate_status(self):
        """Each checklist item should have present status."""
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1", "after": "e0"}],
        }
        result = evaluate_checklist(
            error_category="temporal_violation",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        assert len(result.items) > 0
        for item in result.items:
            assert isinstance(item.present, bool)
            assert isinstance(item.predicate_type, PredicateType)

    def test_to_dict_returns_serializable(self):
        """to_dict should return JSON-serializable dictionary."""
        extraction_result = {
            "entities": {
                "relationships": [{"source": "a", "target": "b", "type": "friend"}],
            },
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }
        result = evaluate_checklist(
            error_category="emotional_inconsistency",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "error_category" in d
        assert "chapter_id" in d
        assert "overall_satisfied" in d
        assert "items" in d
        assert "justification" in d

    def test_justification_explains_result(self):
        """Justification should explain the evaluation result."""
        extraction_result = {
            "entities": {
                "locations": [{"name": "hall"}]
            },
            "events": [{"event_id": "e1", "location": "hall"}],
        }
        result = evaluate_checklist(
            error_category="location_violation",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        assert result is not None
        assert len(result.justification) > 0


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_checklist_for_category(self):
        """Should return checklist for valid category."""
        checklist = get_checklist_for_category("emotional_inconsistency")
        assert checklist is not None
        assert isinstance(checklist, ErrorCategoryChecklist)

    def test_get_checklist_for_unknown_category(self):
        """Should return None for unknown category."""
        checklist = get_checklist_for_category("nonexistent")
        assert checklist is None

    def test_get_all_categories(self):
        """Should return list of all defined categories."""
        categories = get_all_categories()
        assert isinstance(categories, list)
        assert len(categories) >= 4
        assert "emotional_inconsistency" in categories

    def test_format_checklist_evaluation(self):
        """Should format evaluation as readable string."""
        extraction_result = {
            "entities": {
                "relationships": [{"source": "a", "target": "b", "type": "friend"}],
            },
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }
        result = evaluate_checklist(
            error_category="emotional_inconsistency",
            chapter_id="chapter_1",
            extraction_result=extraction_result,
        )
        formatted = format_checklist_evaluation(result)
        assert isinstance(formatted, str)
        assert "emotional_inconsistency" in formatted
        assert "✓" in formatted or "✗" in formatted


# =============================================================================
# Test Integration with Detectability
# =============================================================================


class TestIntegrationWithDetectability:
    """Tests for integration between evidence_checklist and detectability."""

    def test_checklist_evaluation_in_detectability_result(self):
        """Checklist evaluation should be included in DetectabilityResult."""
        from scripts.evaluation.detectability import (
            classify_detectability,
            ImplantedError,
            DetectabilityStatus,
        )

        implanted_error = ImplantedError(
            chapter_id="chapter_1",
            error_type="emotional_inconsistency",
            description="Ron shows hostility instead of friendship",
        )
        extraction_result = {
            "entities": {
                "relationships": [{"source": "ron", "target": "harry", "type": "friend"}],
            },
            "events": [{"event_id": "e1", "social_action_type": "greeting"}],
        }

        result = classify_detectability(
            chapter_id="chapter_1",
            implanted_error=implanted_error,
            extraction_diagnostic=None,
            asp_violations=[],  # No errors detected
            extraction_result=extraction_result,
        )

        assert result.checklist_evaluation is not None
        assert result.checklist_evaluation.error_category == "emotional_inconsistency"

    def test_checklist_affects_classification(self):
        """Missing predicates should affect detectability classification."""
        from scripts.evaluation.detectability import (
            classify_detectability,
            ImplantedError,
            DetectabilityStatus,
        )

        implanted_error = ImplantedError(
            chapter_id="chapter_1",
            error_type="temporal_violation",
            description="Event occurs at wrong time",
        )
        extraction_result = {
            "entities": {},
            "events": [{"event_id": "e1"}],  # No temporal info
        }

        result = classify_detectability(
            chapter_id="chapter_1",
            implanted_error=implanted_error,
            extraction_diagnostic=None,
            asp_violations=[],  # No errors detected
            extraction_result=extraction_result,
        )

        # Without temporal predicates, should be undetectable or detectable_but_missed
        assert result.checklist_evaluation is not None
        assert result.checklist_evaluation.overall_satisfied is False
