"""
Unit Tests for StateManager

Phase 6, Step 6.1: Test StateManager snapshots/deltas

Tests:
    - World state creation and management
    - Snapshot creation at timesteps
    - Delta computation between states
    - Entity and relation tracking
    - Cross-chapter persistence
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.state_manager import (
    StateManager, 
    WorldState, 
    Entity, 
    Relation, 
    StoryRule,
    StateDelta,
)


class TestStateManagerBasics:
    """Basic StateManager functionality."""
    
    def test_initialization(self):
        """StateManager initializes with empty state at time 0."""
        sm = StateManager()
        
        assert sm.current_time == 0
        assert len(sm.states) == 1
        assert 0 in sm.states
        assert sm.states[0].time == 0
    
    def test_get_current_state(self):
        """get_current_state returns state at current time."""
        sm = StateManager()
        state = sm.get_current_state()
        
        assert isinstance(state, WorldState)
        assert state.time == 0
    
    def test_advance_time(self):
        """advance_time increments timestep and clones state."""
        sm = StateManager()
        
        # Add an entity before advancing
        sm.add_entity("harry", "character")
        
        # Advance time
        new_time = sm.advance_time()
        
        assert new_time == 1
        assert sm.current_time == 1
        assert len(sm.states) == 2
        
        # New state should have the entity
        new_state = sm.get_current_state()
        assert "harry" in new_state.entities


class TestStateManagerEntities:
    """Entity tracking tests."""
    
    def test_add_entity(self):
        """add_entity adds to current state and persistent."""
        sm = StateManager()
        
        entity = sm.add_entity("harry", "character", state="alive")
        
        assert entity.id == "harry"
        assert entity.entity_type == "character"
        assert entity.state == "alive"
        
        # Should be in current state
        current = sm.get_current_state()
        assert "harry" in current.entities
        
        # Should be in persistent entities
        assert "harry" in sm.persistent_entities
    
    def test_add_entity_with_traits(self):
        """add_entity supports traits and emotion."""
        sm = StateManager()
        
        entity = sm.add_entity(
            "hermione", 
            "character", 
            traits={"brave", "intelligent"},
            emotion="determined"
        )
        
        assert "brave" in entity.traits
        assert "intelligent" in entity.traits
        assert entity.emotion == "determined"
    
    def test_mark_dead(self):
        """mark_dead updates entity state and persistent_dead."""
        sm = StateManager()
        sm.add_entity("voldemort", "character")
        
        sm.mark_dead("voldemort")
        
        # Should be in persistent_dead
        assert "voldemort" in sm.persistent_dead
        
        # Entity state should be updated
        assert sm.persistent_entities["voldemort"].state == "dead"
        
        # is_dead should return True
        assert sm.is_dead("voldemort") is True
    
    def test_is_dead_unknown_character(self):
        """is_dead returns False for unknown characters."""
        sm = StateManager()
        
        assert sm.is_dead("nonexistent") is False


class TestStateManagerRelations:
    """Relation tracking tests."""
    
    def test_add_relation(self):
        """add_relation adds to current state."""
        sm = StateManager()
        
        relation = sm.add_relation("present", ("harry", "hogwarts"), source_event="e1")
        
        assert relation.predicate == "present"
        assert relation.args == ("harry", "hogwarts")
        assert relation.time == 0
        assert relation.source_event == "e1"
        
        # Should be in current state
        current = sm.get_current_state()
        assert len(current.relations) == 1
    
    def test_add_relationship(self):
        """add_relationship tracks persistent relationships."""
        sm = StateManager()
        
        sm.add_relationship("harry", "ron", "friend", source_event="e1")
        
        # Should be in persistent relationships
        assert ("harry", "ron") in sm.persistent_relationships
        assert sm.persistent_relationships[("harry", "ron")] == "friend"


class TestStateManagerSnapshots:
    """Snapshot and delta computation tests."""
    
    def test_snapshot_clones_state(self):
        """snapshot creates an independent copy."""
        sm = StateManager()
        sm.add_entity("harry", "character")
        
        snapshot = sm.snapshot(0)
        
        # Modify original
        sm.add_entity("ron", "character")
        
        # Snapshot should not have ron
        assert "harry" in snapshot.entities
        assert "ron" not in snapshot.entities
    
    def test_snapshot_nonexistent_time(self):
        """snapshot of nonexistent time returns empty state."""
        sm = StateManager()
        
        snapshot = sm.snapshot(999)
        
        assert snapshot.time == 999
        assert len(snapshot.entities) == 0
    
    def test_delta_computation(self):
        """delta correctly identifies changes between states."""
        sm = StateManager()
        
        # Time 0: Add harry
        sm.add_entity("harry", "character")
        
        # Time 1: Add ron
        sm.advance_time()
        sm.add_entity("ron", "character")
        
        # Get delta
        delta = sm.delta(0, 1)
        
        assert delta.from_time == 0
        assert delta.to_time == 1
        assert len(delta.added_entities) == 1
        assert delta.added_entities[0].id == "ron"


class TestStateManagerStoryRules:
    """Story rule tracking tests."""
    
    def test_add_story_rule(self):
        """add_story_rule adds to current state."""
        sm = StateManager()
        
        rule = sm.add_story_rule(
            rule_type="relationship",
            subject="harry",
            predicate="friends_with",
            obj="ron",
            established_by="e1"
        )
        
        assert rule.rule_type == "relationship"
        assert rule.subject == "harry"
        assert rule.predicate == "friends_with"
        assert rule.object == "ron"
        assert rule.valid is True
        
        # Should be in current state
        current = sm.get_current_state()
        assert len(current.story_rules) == 1
    
    def test_invalidate_rule(self):
        """invalidate_rule marks matching rule as invalid."""
        sm = StateManager()
        sm.add_story_rule("relationship", "harry", "friends_with", "draco", "e1")
        
        # Invalidate the rule
        result = sm.invalidate_rule("harry", "draco", "e5")
        
        assert result is True
        
        current = sm.get_current_state()
        assert current.story_rules[0].valid is False


class TestStateManagerEventTracking:
    """Global event ID tracking tests."""
    
    def test_get_next_event_id(self):
        """get_next_event_id returns sequential IDs."""
        sm = StateManager()
        
        id1 = sm.get_next_event_id()
        id2 = sm.get_next_event_id()
        id3 = sm.get_next_event_id()
        
        assert id1 == "e1"
        assert id2 == "e2"
        assert id3 == "e3"
    
    def test_log_event(self):
        """log_event records event with global ID."""
        sm = StateManager()
        
        event = {
            "type": "travel",
            "agent": "harry",
            "location": "hogwarts",
        }
        
        event_id = sm.log_event(event, chapter_num=0)
        
        assert event_id == "e1"
        assert len(sm.event_log) == 1
        assert sm.event_log[0]["id"] == "e1"
        assert sm.event_log[0]["chapter"] == 0


class TestStateManagerASPOutput:
    """ASP fact generation tests."""
    
    def test_get_asp_facts_for_clingo(self):
        """get_asp_facts_for_clingo generates valid ASP."""
        sm = StateManager()
        sm.add_entity("harry", "character")
        sm.add_entity("hogwarts", "location")
        sm.mark_dead("voldemort")
        
        facts = sm.get_asp_facts_for_clingo()
        
        assert "character(harry)." in facts
        assert "location(hogwarts)." in facts
        assert "is_dead(voldemort)." in facts
    
    def test_get_cross_chapter_state_facts(self):
        """get_cross_chapter_state_facts includes persistent state."""
        sm = StateManager()
        sm.add_entity("harry", "character")
        sm.mark_dead("cedric")
        sm.add_relationship("harry", "ron", "friend")
        
        facts = sm.get_cross_chapter_state_facts()
        
        # Should include death
        death_facts = [f for f in facts if "is_dead" in f]
        assert len(death_facts) == 1
        assert "cedric" in death_facts[0]


class TestWorldState:
    """WorldState dataclass tests."""
    
    def test_to_asp_facts(self):
        """to_asp_facts generates valid ASP output."""
        state = WorldState(time=5)
        state.entities["harry"] = Entity(
            id="harry", 
            entity_type="character",
            traits={"brave"},
            state="alive",
            emotion="happy"
        )
        
        asp = state.to_asp_facts()
        
        assert "% World state at time 5" in asp
        assert "character(harry)." in asp
        assert "trait(harry, brave)." in asp
        assert "character_emotion(harry, happy)." in asp
    
    def test_clone_is_independent(self):
        """clone creates an independent copy."""
        state = WorldState(time=0)
        state.entities["harry"] = Entity(id="harry", entity_type="character")
        
        cloned = state.clone()
        
        # Modify original
        state.entities["ron"] = Entity(id="ron", entity_type="character")
        
        # Clone should not have ron
        assert "harry" in cloned.entities
        assert "ron" not in cloned.entities


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
