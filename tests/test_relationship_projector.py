"""
Tests for engine.relationship_projector module.

Phase 8.10: Relationship Projection with Active Universe Filtering
"""

import pytest
from engine.relationship_projector import (
    ProjectedRelationship,
    RelationshipProjectionResult,
    project_relationships,
    project_relationships_to_asp_facts,
    is_relationship_in_universe,
    filter_relationship_facts,
)
from engine.active_universe import ActiveUniverseResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_relationships():
    """Sample persistent relationships dict."""
    return {
        ('harry', 'hermione'): 'friend',
        ('harry', 'ron'): 'friend',
        ('harry', 'voldemort'): 'enemy',
        ('dumbledore', 'harry'): 'mentor',
        ('draco', 'crabbe'): 'ally',
    }


@pytest.fixture
def small_universe():
    """Active universe with only Harry, Hermione, Ron."""
    return ActiveUniverseResult(
        characters={'harry', 'hermione', 'ron'},
        items=set(),
        locations=set(),
        current_chapter_actors=2,
        previous_chapter_actors=1,
    )


@pytest.fixture
def full_universe():
    """Active universe with all characters."""
    return ActiveUniverseResult(
        characters={'harry', 'hermione', 'ron', 'voldemort', 'dumbledore', 'draco', 'crabbe'},
        items=set(),
        locations=set(),
        current_chapter_actors=7,
    )


# ---------------------------------------------------------------------------
# ProjectedRelationship dataclass tests
# ---------------------------------------------------------------------------

class TestProjectedRelationship:
    """Tests for ProjectedRelationship dataclass."""

    def test_basic_creation(self):
        """ProjectedRelationship stores source, target, rel_type."""
        pr = ProjectedRelationship(source='harry', target='hermione', rel_type='friend')
        assert pr.source == 'harry'
        assert pr.target == 'hermione'
        assert pr.rel_type == 'friend'
        assert pr.provenance == 'persistent_registry'  # default

    def test_custom_provenance(self):
        """ProjectedRelationship accepts custom provenance."""
        pr = ProjectedRelationship(
            source='harry',
            target='ron',
            rel_type='friend',
            provenance='learned',
        )
        assert pr.provenance == 'learned'

    def test_to_relationship_fact(self):
        """to_relationship_fact() returns relationship/3 fact."""
        pr = ProjectedRelationship(source='harry', target='hermione', rel_type='friend')
        fact = pr.to_relationship_fact()
        assert fact == 'relationship(harry, hermione, friend).'

    def test_to_initial_relationship_fact(self):
        """to_initial_relationship_fact() returns initial_relationship/3 fact."""
        pr = ProjectedRelationship(source='harry', target='hermione', rel_type='friend')
        fact = pr.to_initial_relationship_fact()
        assert fact == 'initial_relationship(harry, hermione, friend).'

    def test_to_previous_relationship_fact(self):
        """to_previous_relationship_fact() returns previous_relationship/3 fact."""
        pr = ProjectedRelationship(source='harry', target='hermione', rel_type='friend')
        fact = pr.to_previous_relationship_fact()
        assert fact == 'previous_relationship(harry, hermione, friend).'

    def test_to_relationship_fact_special_characters(self):
        """to_relationship_fact() handles underscores in IDs."""
        pr = ProjectedRelationship(source='harry_potter', target='lord_voldemort', rel_type='arch_enemy')
        fact = pr.to_relationship_fact()
        assert fact == 'relationship(harry_potter, lord_voldemort, arch_enemy).'


# ---------------------------------------------------------------------------
# RelationshipProjectionResult dataclass tests
# ---------------------------------------------------------------------------

class TestRelationshipProjectionResult:
    """Tests for RelationshipProjectionResult dataclass."""

    def test_default_values(self):
        """Default values are empty/zero."""
        result = RelationshipProjectionResult()
        assert result.projected == []
        assert result.filtered_count == 0
        assert result.total_in_registry == 0

    def test_projected_count(self):
        """projected_count returns length of projected list."""
        result = RelationshipProjectionResult()
        result.projected = [
            ProjectedRelationship('a', 'b', 'friend'),
            ProjectedRelationship('c', 'd', 'enemy'),
        ]
        assert result.projected_count == 2

    def test_to_dict(self):
        """to_dict() returns serializable dictionary."""
        result = RelationshipProjectionResult()
        result.total_in_registry = 3
        result.filtered_count = 1
        result.projected = [
            ProjectedRelationship('harry', 'hermione', 'friend'),
            ProjectedRelationship('harry', 'ron', 'friend'),
        ]
        d = result.to_dict()
        assert d['total_in_registry'] == 3
        assert d['projected_count'] == 2
        assert d['filtered_count'] == 1
        assert len(d['projected']) == 2


# ---------------------------------------------------------------------------
# project_relationships() tests
# ---------------------------------------------------------------------------

class TestProjectRelationships:
    """Tests for project_relationships() function."""

    def test_empty_relationships(self):
        """Empty relationships dict returns empty result."""
        result = project_relationships({})
        assert result.projected == []
        assert result.filtered_count == 0
        assert result.total_in_registry == 0

    def test_no_universe_filter_all_pass(self, sample_relationships):
        """Without universe, all relationships pass through."""
        result = project_relationships(sample_relationships)
        assert result.total_in_registry == 5
        assert result.projected_count == 5
        assert result.filtered_count == 0

    def test_universe_filters_relationships(self, sample_relationships, small_universe):
        """With universe, only relationships with both endpoints in universe pass."""
        result = project_relationships(sample_relationships, active_universe=small_universe)
        
        # Only harry-hermione and harry-ron should pass (both endpoints in universe)
        assert result.total_in_registry == 5
        assert result.projected_count == 2
        assert result.filtered_count == 3
        
        # Verify correct relationships passed
        sources_targets = [(pr.source, pr.target) for pr in result.projected]
        assert ('harry', 'hermione') in sources_targets
        assert ('harry', 'ron') in sources_targets

    def test_full_universe_all_pass(self, sample_relationships, full_universe):
        """Full universe allows all relationships."""
        result = project_relationships(sample_relationships, active_universe=full_universe)
        assert result.projected_count == 5
        assert result.filtered_count == 0

    def test_single_endpoint_outside_universe_filtered(self):
        """Relationship filtered if either endpoint is outside universe."""
        relationships = {
            ('harry', 'ron'): 'friend',  # both in
            ('harry', 'voldemort'): 'enemy',  # voldemort out
            ('dumbledore', 'harry'): 'mentor',  # dumbledore out
        }
        universe = ActiveUniverseResult(
            characters={'harry', 'ron'},
            items=set(),
            locations=set(),
        )
        
        result = project_relationships(relationships, active_universe=universe)
        assert result.projected_count == 1
        assert result.filtered_count == 2
        assert result.projected[0].source == 'harry'
        assert result.projected[0].target == 'ron'

    def test_provenance_set_correctly(self, sample_relationships):
        """All projected relationships have 'persistent_registry' provenance."""
        result = project_relationships(sample_relationships)
        for pr in result.projected:
            assert pr.provenance == 'persistent_registry'


# ---------------------------------------------------------------------------
# project_relationships_to_asp_facts() tests
# ---------------------------------------------------------------------------

class TestProjectRelationshipsToASPFacts:
    """Tests for project_relationships_to_asp_facts() convenience function."""

    def test_empty_returns_empty_list(self):
        """Empty relationships returns empty fact list."""
        facts = project_relationships_to_asp_facts({})
        assert facts == []

    def test_returns_asp_facts_with_defaults(self, sample_relationships):
        """By default, returns previous_relationship and initial_relationship facts."""
        facts = project_relationships_to_asp_facts(sample_relationships)
        # Default: include_initial=True, include_previous=True, include_current=False
        # So 5 relationships * 2 = 10 facts
        assert len(facts) == 10
        assert all(
            f.startswith('previous_relationship(') or f.startswith('initial_relationship(')
            for f in facts
        )

    def test_returns_only_current_relationship_facts(self, sample_relationships):
        """Can request only relationship/3 facts."""
        facts = project_relationships_to_asp_facts(
            sample_relationships,
            include_initial=False,
            include_previous=False,
            include_current=True,
        )
        assert len(facts) == 5
        assert all(f.startswith('relationship(') for f in facts)
        assert all(f.endswith(').') for f in facts)

    def test_respects_universe_filter(self, sample_relationships, small_universe):
        """Respects active universe filtering."""
        facts = project_relationships_to_asp_facts(
            sample_relationships,
            active_universe=small_universe,
            include_initial=False,
            include_previous=False,
            include_current=True,
        )
        # Only harry-hermione and harry-ron pass
        assert len(facts) == 2


# ---------------------------------------------------------------------------
# is_relationship_in_universe() tests
# ---------------------------------------------------------------------------

class TestIsRelationshipInUniverse:
    """Tests for is_relationship_in_universe() guard function."""

    def test_no_universe_returns_true(self):
        """Without universe, always returns True."""
        assert is_relationship_in_universe('harry', 'hermione', None) is True

    def test_both_in_universe_returns_true(self, small_universe):
        """Both endpoints in universe returns True."""
        assert is_relationship_in_universe('harry', 'hermione', small_universe) is True
        assert is_relationship_in_universe('harry', 'ron', small_universe) is True

    def test_source_outside_returns_false(self, small_universe):
        """Source outside universe returns False."""
        assert is_relationship_in_universe('voldemort', 'harry', small_universe) is False

    def test_target_outside_returns_false(self, small_universe):
        """Target outside universe returns False."""
        assert is_relationship_in_universe('harry', 'voldemort', small_universe) is False

    def test_both_outside_returns_false(self, small_universe):
        """Both endpoints outside universe returns False."""
        assert is_relationship_in_universe('voldemort', 'dumbledore', small_universe) is False


# ---------------------------------------------------------------------------
# filter_relationship_facts() tests
# ---------------------------------------------------------------------------

class TestFilterRelationshipFacts:
    """Tests for filter_relationship_facts() function."""

    def test_empty_facts_returns_empty(self, small_universe):
        """Empty facts list returns empty."""
        result = filter_relationship_facts([], small_universe)
        assert result == []

    def test_no_universe_returns_all(self):
        """Without universe, all facts pass."""
        facts = [
            'relationship(harry, hermione, friend).',
            'relationship(voldemort, bellatrix, ally).',
        ]
        result = filter_relationship_facts(facts, None)
        assert result == facts

    def test_filters_by_universe(self, small_universe):
        """Filters facts based on active universe."""
        facts = [
            'relationship(harry, hermione, friend).',  # pass
            'relationship(harry, ron, friend).',  # pass
            'relationship(harry, voldemort, enemy).',  # filtered (voldemort out)
            'relationship(dumbledore, harry, mentor).',  # filtered (dumbledore out)
        ]
        result = filter_relationship_facts(facts, small_universe)
        assert len(result) == 2
        assert 'relationship(harry, hermione, friend).' in result
        assert 'relationship(harry, ron, friend).' in result

    def test_handles_malformed_facts_gracefully(self, small_universe):
        """Non-relationship facts are kept as-is (pass through)."""
        facts = [
            'relationship(harry, hermione, friend).',  # valid relationship - kept
            'not_a_relationship(x, y, z).',  # wrong predicate - not a relationship, kept
            'relationship(only_one_arg).',  # wrong arity - doesn't match pattern, kept
            '',  # empty - kept
        ]
        result = filter_relationship_facts(facts, small_universe)
        # Non-relationship predicates pass through, malformed relationship also passes
        # (as it doesn't match the regex pattern)
        assert len(result) == 4
        assert 'relationship(harry, hermione, friend).' in result
        # Non-relationships pass through unchanged
        assert 'not_a_relationship(x, y, z).' in result

    def test_handles_underscores_in_entity_ids(self):
        """Correctly parses entity IDs with underscores."""
        universe = ActiveUniverseResult(
            characters={'harry_potter', 'hermione_granger'},
            items=set(),
            locations=set(),
        )
        facts = [
            'relationship(harry_potter, hermione_granger, best_friend).',
        ]
        result = filter_relationship_facts(facts, universe)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestRelationshipProjectorIntegration:
    """Integration tests combining multiple functions."""

    def test_full_pipeline(self, sample_relationships, small_universe):
        """Test full pipeline from relationships dict to filtered ASP facts."""
        # Step 1: Project relationships
        result = project_relationships(sample_relationships, active_universe=small_universe)
        
        # Step 2: Convert to ASP facts using to_relationship_fact()
        facts = [rel.to_relationship_fact() for rel in result.projected]
        
        # Verify
        assert len(facts) == 2
        assert 'relationship(harry, hermione, friend).' in facts
        assert 'relationship(harry, ron, friend).' in facts

    def test_convenience_function_matches_full_pipeline(self, sample_relationships, small_universe):
        """Convenience function produces same result as full pipeline."""
        # Full pipeline with only current facts
        result = project_relationships(sample_relationships, active_universe=small_universe)
        pipeline_facts = [rel.to_relationship_fact() for rel in result.projected]
        
        # Convenience function with only current facts
        convenience_facts = project_relationships_to_asp_facts(
            sample_relationships,
            active_universe=small_universe,
            include_initial=False,
            include_previous=False,
            include_current=True,
        )
        
        assert set(pipeline_facts) == set(convenience_facts)

    def test_empty_universe_filters_all(self, sample_relationships):
        """Empty universe filters all relationships."""
        empty_universe = ActiveUniverseResult(
            characters=set(),
            items=set(),
            locations=set(),
        )
        result = project_relationships(sample_relationships, active_universe=empty_universe)
        assert result.projected_count == 0
        assert result.filtered_count == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_self_relationship(self):
        """Self-relationship (same source and target) is handled."""
        relationships = {('harry', 'harry'): 'self_aware'}
        universe = ActiveUniverseResult(
            characters={'harry'},
            items=set(),
            locations=set(),
        )
        result = project_relationships(relationships, active_universe=universe)
        assert result.projected_count == 1
        assert result.projected[0].source == 'harry'
        assert result.projected[0].target == 'harry'

    def test_case_sensitive_matching(self):
        """Entity matching is case-sensitive."""
        relationships = {('Harry', 'Ron'): 'friend'}
        universe = ActiveUniverseResult(
            characters={'harry', 'ron'},  # lowercase
            items=set(),
            locations=set(),
        )
        result = project_relationships(relationships, active_universe=universe)
        # Should be filtered because 'Harry' != 'harry'
        assert result.projected_count == 0
        assert result.filtered_count == 1

    def test_symmetric_relationships_both_emitted(self):
        """Both directions of symmetric relationships are preserved if present."""
        relationships = {
            ('harry', 'ron'): 'friend',
            ('ron', 'harry'): 'friend',
        }
        universe = ActiveUniverseResult(
            characters={'harry', 'ron'},
            items=set(),
            locations=set(),
        )
        result = project_relationships(relationships, active_universe=universe)
        assert result.projected_count == 2


# ---------------------------------------------------------------------------
# Debug Instrumentation Tests (Phase 8.11.2)
# ---------------------------------------------------------------------------

class TestRelationshipDebugInstrumentation:
    """Tests for relationship projection debug instrumentation."""
    
    def test_debug_disabled_by_default(self):
        """Debug is disabled by default."""
        from engine.relationship_projector import is_relationship_debug_enabled
        # Reset to ensure clean state (in case previous test enabled it)
        from engine.relationship_projector import disable_relationship_debug
        disable_relationship_debug()
        
        assert is_relationship_debug_enabled() is False
    
    def test_enable_disable_debug(self):
        """Can enable and disable debug mode."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            is_relationship_debug_enabled,
        )
        
        disable_relationship_debug()
        assert is_relationship_debug_enabled() is False
        
        enable_relationship_debug()
        assert is_relationship_debug_enabled() is True
        
        disable_relationship_debug()
        assert is_relationship_debug_enabled() is False
    
    def test_stats_not_recorded_when_disabled(self):
        """Stats are not recorded when debug is disabled."""
        from engine.relationship_projector import (
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        disable_relationship_debug()
        reset_relationship_debug_stats()
        
        relationships = {('harry', 'ron'): 'friend'}
        universe = ActiveUniverseResult(
            characters={'harry', 'ron'},
            items=set(),
            locations=set(),
        )
        
        project_relationships_to_asp_facts(
            relationships,
            active_universe=universe,
            chapter=1,
        )
        
        stats = get_relationship_debug_stats()
        assert len(stats) == 0
    
    def test_stats_recorded_when_enabled(self):
        """Stats are recorded when debug is enabled."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        enable_relationship_debug()
        reset_relationship_debug_stats()
        
        try:
            relationships = {
                ('harry', 'ron'): 'friend',
                ('harry', 'hermione'): 'friend',
                ('voldemort', 'bellatrix'): 'ally',
            }
            universe = ActiveUniverseResult(
                characters={'harry', 'ron', 'hermione'},
                items=set(),
                locations=set(),
            )
            
            project_relationships_to_asp_facts(
                relationships,
                active_universe=universe,
                chapter=1,
            )
            
            stats = get_relationship_debug_stats()
            assert 1 in stats
            assert stats[1]['examined'] == 3
            assert stats[1]['projected'] == 2  # harry-ron, harry-hermione
            assert stats[1]['filtered'] == 1   # voldemort-bellatrix
        finally:
            disable_relationship_debug()
    
    def test_stats_accumulate_across_chapters(self):
        """Stats accumulate across multiple chapters."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        enable_relationship_debug()
        reset_relationship_debug_stats()
        
        try:
            relationships = {('harry', 'ron'): 'friend'}
            universe = ActiveUniverseResult(
                characters={'harry', 'ron'},
                items=set(),
                locations=set(),
            )
            
            # Chapter 1
            project_relationships_to_asp_facts(
                relationships, active_universe=universe, chapter=1
            )
            
            # Chapter 2 - add more relationships
            relationships[('harry', 'hermione')] = 'friend'
            universe = ActiveUniverseResult(
                characters={'harry', 'ron', 'hermione'},
                items=set(),
                locations=set(),
            )
            project_relationships_to_asp_facts(
                relationships, active_universe=universe, chapter=2
            )
            
            stats = get_relationship_debug_stats()
            assert 1 in stats
            assert 2 in stats
            assert stats[1]['examined'] == 1
            assert stats[2]['examined'] == 2
        finally:
            disable_relationship_debug()
    
    def test_reset_clears_stats(self):
        """reset_relationship_debug_stats clears all accumulated stats."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        enable_relationship_debug()
        reset_relationship_debug_stats()
        
        try:
            relationships = {('harry', 'ron'): 'friend'}
            universe = ActiveUniverseResult(
                characters={'harry', 'ron'},
                items=set(),
                locations=set(),
            )
            
            project_relationships_to_asp_facts(
                relationships, active_universe=universe, chapter=1
            )
            
            assert len(get_relationship_debug_stats()) > 0
            
            reset_relationship_debug_stats()
            
            assert len(get_relationship_debug_stats()) == 0
        finally:
            disable_relationship_debug()
    
    def test_no_chapter_no_stats(self):
        """When chapter is not provided, stats are not recorded."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        enable_relationship_debug()
        reset_relationship_debug_stats()
        
        try:
            relationships = {('harry', 'ron'): 'friend'}
            universe = ActiveUniverseResult(
                characters={'harry', 'ron'},
                items=set(),
                locations=set(),
            )
            
            # Call without chapter parameter
            project_relationships_to_asp_facts(
                relationships,
                active_universe=universe,
                # chapter not provided
            )
            
            stats = get_relationship_debug_stats()
            assert len(stats) == 0
        finally:
            disable_relationship_debug()
    
    def test_get_stats_returns_copy(self):
        """get_relationship_debug_stats returns a copy, not the original."""
        from engine.relationship_projector import (
            enable_relationship_debug,
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
        )
        
        enable_relationship_debug()
        reset_relationship_debug_stats()
        
        try:
            relationships = {('harry', 'ron'): 'friend'}
            universe = ActiveUniverseResult(
                characters={'harry', 'ron'},
                items=set(),
                locations=set(),
            )
            
            project_relationships_to_asp_facts(
                relationships, active_universe=universe, chapter=1
            )
            
            stats = get_relationship_debug_stats()
            stats[1]['examined'] = 999  # Modify the copy
            
            # Original should be unchanged
            original_stats = get_relationship_debug_stats()
            assert original_stats[1]['examined'] == 1
        finally:
            disable_relationship_debug()
    
    def test_zero_cost_when_disabled(self):
        """When disabled, no overhead from debug code paths."""
        from engine.relationship_projector import (
            disable_relationship_debug,
            reset_relationship_debug_stats,
            get_relationship_debug_stats,
            _DEBUG_RELATIONSHIP_PROJECTION,
        )
        
        disable_relationship_debug()
        reset_relationship_debug_stats()
        
        # The flag should be False, ensuring the if-check short-circuits
        from engine import relationship_projector
        assert relationship_projector._DEBUG_RELATIONSHIP_PROJECTION is False
        
        # Even with chapter, no stats recorded
        relationships = {('harry', 'ron'): 'friend'}
        universe = ActiveUniverseResult(
            characters={'harry', 'ron'},
            items=set(),
            locations=set(),
        )
        
        project_relationships_to_asp_facts(
            relationships, active_universe=universe, chapter=1
        )
        
        assert len(get_relationship_debug_stats()) == 0
