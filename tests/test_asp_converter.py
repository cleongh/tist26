"""
Tests for scripts.logic.asp_converter module.

Phase 8.10: Tests for relationship fact filtering by active universe.
"""

import pytest
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.logic.asp_converter import to_asp, sanitize, sanitize_char
from engine.active_universe import ActiveUniverseResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_data_with_relationships():
    """Sample chapter data with relationships.
    
    Note: sanitize_char normalizes IDs (e.g., 'harry' -> 'harry_potter'),
    so we use already-normalized IDs here.
    """
    return {
        "entities": {
            "characters": [
                {"id": "harry_potter", "name": "Harry Potter"},
                {"id": "ron_weasley", "name": "Ron Weasley"},
                {"id": "hermione_granger", "name": "Hermione Granger"},
                {"id": "lord_voldemort", "name": "Lord Voldemort"},
            ],
            "relationships": [
                {"from": "harry_potter", "to": "ron_weasley", "type": "friend"},
                {"from": "harry_potter", "to": "hermione_granger", "type": "friend"},
                {"from": "harry_potter", "to": "lord_voldemort", "type": "enemy"},
            ],
            "locations": [],
            "items": [],
        },
        "events": [],
    }


@pytest.fixture
def small_universe():
    """Active universe with only Harry, Ron, Hermione (normalized IDs)."""
    return ActiveUniverseResult(
        characters={'harry_potter', 'ron_weasley', 'hermione_granger'},
        items=set(),
        locations=set(),
    )


@pytest.fixture
def full_universe():
    """Active universe with all characters (normalized IDs)."""
    return ActiveUniverseResult(
        characters={'harry_potter', 'ron_weasley', 'hermione_granger', 'lord_voldemort'},
        items=set(),
        locations=set(),
    )


# ---------------------------------------------------------------------------
# Relationship fact filtering tests
# ---------------------------------------------------------------------------

class TestRelationshipUniverseFiltering:
    """Tests for relationship fact filtering by active universe."""

    def test_no_universe_all_relationships_emitted(self, sample_data_with_relationships):
        """Without active_universe, all relationships are emitted."""
        asp = to_asp(sample_data_with_relationships, chapter_num=1)
        
        # All 3 relationships should be present (using normalized IDs)
        assert 'relationship(harry_potter, ron_weasley, friend).' in asp
        assert 'relationship(harry_potter, hermione_granger, friend).' in asp
        assert 'relationship(harry_potter, lord_voldemort, enemy).' in asp

    def test_with_universe_filters_inactive_endpoint(
        self, sample_data_with_relationships, small_universe
    ):
        """Relationships with inactive endpoints are filtered out."""
        asp = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=small_universe,
        )
        
        # harry-ron and harry-hermione should be present (both in universe)
        assert 'relationship(harry_potter, ron_weasley, friend).' in asp
        assert 'relationship(harry_potter, hermione_granger, friend).' in asp
        
        # harry-voldemort should NOT be present (lord_voldemort not in universe)
        assert 'relationship(harry_potter, lord_voldemort, enemy).' not in asp

    def test_full_universe_all_relationships_emitted(
        self, sample_data_with_relationships, full_universe
    ):
        """With full universe, all relationships are emitted."""
        asp = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=full_universe,
        )
        
        assert 'relationship(harry_potter, ron_weasley, friend).' in asp
        assert 'relationship(harry_potter, hermione_granger, friend).' in asp
        assert 'relationship(harry_potter, lord_voldemort, enemy).' in asp

    def test_initial_relationship_also_emitted(
        self, sample_data_with_relationships, small_universe
    ):
        """initial_relationship facts are also emitted for EC framework."""
        asp = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=small_universe,
        )
        
        # Should have initial_relationship for relationships in universe
        assert 'initial_relationship(harry_potter, ron_weasley, friend).' in asp
        assert 'initial_relationship(harry_potter, hermione_granger, friend).' in asp
        
        # Should NOT have initial_relationship for filtered relationships
        assert 'initial_relationship(harry_potter, lord_voldemort, enemy).' not in asp

    def test_empty_universe_filters_all(self, sample_data_with_relationships):
        """Empty universe filters all relationships."""
        empty_universe = ActiveUniverseResult(
            characters=set(),
            items=set(),
            locations=set(),
        )
        asp = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=empty_universe,
        )
        
        # No relationship facts should be present
        assert 'relationship(harry_potter, ron_weasley, friend).' not in asp
        assert 'relationship(harry_potter, hermione_granger, friend).' not in asp
        assert 'relationship(harry_potter, lord_voldemort, enemy).' not in asp

    def test_source_outside_universe_filtered(self):
        """Relationship is filtered if source is outside universe."""
        data = {
            "entities": {
                "characters": [
                    {"id": "harry_potter"},
                    {"id": "albus_dumbledore"},
                ],
                "relationships": [
                    {"from": "albus_dumbledore", "to": "harry_potter", "type": "mentor"},
                ],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        universe = ActiveUniverseResult(
            characters={'harry_potter'},  # albus_dumbledore NOT in universe
            items=set(),
            locations=set(),
        )
        asp = to_asp(data, chapter_num=1, active_universe=universe)
        
        assert 'relationship(albus_dumbledore, harry_potter, mentor).' not in asp

    def test_target_outside_universe_filtered(self):
        """Relationship is filtered if target is outside universe."""
        data = {
            "entities": {
                "characters": [
                    {"id": "harry_potter"},
                    {"id": "sirius_black"},
                ],
                "relationships": [
                    {"from": "harry_potter", "to": "sirius_black", "type": "godson"},
                ],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        universe = ActiveUniverseResult(
            characters={'harry_potter'},  # sirius_black NOT in universe
            items=set(),
            locations=set(),
        )
        asp = to_asp(data, chapter_num=1, active_universe=universe)
        
        assert 'relationship(harry_potter, sirius_black, godson).' not in asp


# ---------------------------------------------------------------------------
# relationship_rule filtering tests
# ---------------------------------------------------------------------------

class TestRelationshipRuleFiltering:
    """Tests for relationship_rule filtering by active universe."""

    @pytest.fixture
    def story_rules_with_relationships(self):
        """Story rules containing relationship rules (using normalized IDs)."""
        return [
            {
                'valid': True,
                'type': 'relationship',
                'subject': 'vernon_dursley',
                'predicate': 'hates',
                'object': 'harry_potter',
                'established_by': 'e0',
            },
            {
                'valid': True,
                'type': 'relationship',
                'subject': 'harry_potter',
                'predicate': 'friend',
                'object': 'ron_weasley',
                'established_by': 'e1',
            },
            {
                'valid': True,
                'type': 'trait',
                'subject': 'harry_potter',
                'predicate': 'brave',
                'object': None,
                'established_by': 'e0',
            },
        ]

    def test_relationship_rule_filtered_by_universe(self, story_rules_with_relationships):
        """relationship_rule facts are filtered by active universe."""
        data = {
            "entities": {
                "characters": [
                    {"id": "harry_potter"},
                    {"id": "ron_weasley"},
                    {"id": "vernon_dursley"},
                ],
                "relationships": [],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        universe = ActiveUniverseResult(
            characters={'harry_potter', 'ron_weasley'},  # vernon_dursley NOT in universe
            items=set(),
            locations=set(),
        )
        
        asp = to_asp(
            data,
            chapter_num=1,
            story_rules=story_rules_with_relationships,
            active_universe=universe,
        )
        
        # harry-ron relationship rule should be present
        assert 'relationship_rule(harry_potter, friend, ron_weasley, e1).' in asp
        
        # vernon_dursley-harry relationship rule should NOT be present
        assert 'relationship_rule(vernon_dursley, hates, harry_potter, e0).' not in asp
        
        # Non-relationship rules (traits) should still be present
        assert 'trait_rule(harry_potter, brave, e0).' in asp

    def test_no_universe_all_relationship_rules_emitted(self, story_rules_with_relationships):
        """Without active_universe, all relationship rules are emitted."""
        data = {
            "entities": {
                "characters": [],
                "relationships": [],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        
        asp = to_asp(
            data,
            chapter_num=1,
            story_rules=story_rules_with_relationships,
        )
        
        assert 'relationship_rule(vernon_dursley, hates, harry_potter, e0).' in asp
        assert 'relationship_rule(harry_potter, friend, ron_weasley, e1).' in asp


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_filtering_is_deterministic(self, sample_data_with_relationships, small_universe):
        """Same input produces same output."""
        asp1 = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=small_universe,
        )
        asp2 = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=small_universe,
        )
        
        assert asp1 == asp2

    def test_no_silent_errors_or_logs(self, sample_data_with_relationships, small_universe, caplog):
        """Filtered relationships don't produce error logs."""
        import logging
        caplog.set_level(logging.DEBUG)
        
        asp = to_asp(
            sample_data_with_relationships,
            chapter_num=1,
            active_universe=small_universe,
        )
        
        # Should not log about filtered relationships
        assert 'voldemort' not in caplog.text.lower() or 'filtered' not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_self_relationship(self):
        """Self-relationship is handled correctly."""
        data = {
            "entities": {
                "characters": [{"id": "narcissus"}],
                "relationships": [
                    {"from": "narcissus", "to": "narcissus", "type": "loves"},
                ],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        universe = ActiveUniverseResult(
            characters={'narcissus'},
            items=set(),
            locations=set(),
        )
        asp = to_asp(data, chapter_num=1, active_universe=universe)
        
        assert 'relationship(narcissus, narcissus, loves).' in asp

    def test_case_sensitive_matching(self):
        """Entity matching after sanitization - sanitize_char lowercases and normalizes."""
        data = {
            "entities": {
                # Use IDs that are already normalized to avoid transformation surprises
                "characters": [{"id": "test_char_a"}, {"id": "test_char_b"}],
                "relationships": [
                    {"from": "test_char_a", "to": "test_char_b", "type": "friend"},
                ],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        # Universe uses same IDs (after sanitization, which just lowercases these)
        universe = ActiveUniverseResult(
            characters={'test_char_a', 'test_char_b'},
            items=set(),
            locations=set(),
        )
        asp = to_asp(data, chapter_num=1, active_universe=universe)
        
        # Should be present because both endpoints are in universe
        assert 'relationship(test_char_a, test_char_b, friend).' in asp

    def test_empty_relationships_list(self, small_universe):
        """Empty relationships list doesn't cause errors."""
        data = {
            "entities": {
                "characters": [{"id": "harry"}],
                "relationships": [],
                "locations": [],
                "items": [],
            },
            "events": [],
        }
        asp = to_asp(data, chapter_num=1, active_universe=small_universe)
        
        # Should not contain any relationship facts
        assert 'relationship(' not in asp or 'relationship(harry' not in asp
