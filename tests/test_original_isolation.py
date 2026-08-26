"""
Regression tests proving modified-story evaluation is fully isolated from
ORIGINAL-story extractions in scripts/kfold_experiment_runner_conflict_resolver.py.

These are static/structural checks (signature + source inspection) rather
than full engine runs, so they stay fast and don't depend on Clingo/rules
being present -- the goal is to catch any regression that reintroduces an
`original_extractions` parameter or a `variant == "original"` read in the
production evaluation path.
"""

import inspect
import re

from scripts import kfold_experiment_runner_conflict_resolver as runner


class TestEvaluateStoryWithEngineSignature:
    def test_no_original_extractions_parameter(self):
        params = inspect.signature(runner.evaluate_story_with_engine).parameters
        assert "original_extractions" not in params

    def test_only_expected_parameters(self):
        params = list(inspect.signature(runner.evaluate_story_with_engine).parameters)
        assert params == ["story", "story_extractions", "rules_dir", "enable_learning"]


class TestMainDoesNotLoadOriginalVariant:
    def test_main_source_has_no_original_variant_filter(self):
        source = inspect.getsource(runner.main)
        assert '"original"' not in source
        assert "'original'" not in source

    def test_main_does_not_pass_original_extractions(self):
        source = inspect.getsource(runner.main)
        assert "original_extractions=" not in source


class TestMiningHelpersUnusedInProduction:
    """The mining helpers (mine_temporal_precedence_rules, etc.) are kept for
    reference/tests only. They must not be called from
    evaluate_story_with_engine or main() anymore -- production detection for
    a modified story must depend only on that story's own modified chapters
    and fixed, authored rules.
    """

    MINING_HELPER_NAMES = [
        "mine_temporal_precedence_rules",
        "mine_temporal_precedence_rules_by_patient",
        "mine_temporal_precedence_rules_by_location",
        "mine_appearance_emotion_compatibility",
        "mine_relationship_action_compatibility",
        "mine_signal_density_threshold",
        "mine_location_connectivity",
    ]

    def test_mining_helpers_not_called_from_evaluate_story_with_engine(self):
        source = inspect.getsource(runner.evaluate_story_with_engine)
        for name in self.MINING_HELPER_NAMES:
            assert re.search(rf"\b{name}\(", source) is None, (
                f"{name}() must not be called from evaluate_story_with_engine "
                "-- original-story mining must not influence modified-story "
                "evaluation."
            )

    def test_mining_helpers_not_called_from_main(self):
        source = inspect.getsource(runner.main)
        for name in self.MINING_HELPER_NAMES:
            assert re.search(rf"\b{name}\(", source) is None, (
                f"{name}() must not be called from main() -- original-story "
                "mining must not influence modified-story evaluation."
            )
