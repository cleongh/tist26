"""
Tests for ContinuityContextBuilder - Continuity Context Injection

Phase 3: Ensure each chapter is treated as a delta over known state
"""

import pytest
import json
from engine.continuity_context import (
    ContinuityContextBuilder,
    ContinuityContext,
    build_continuity_context,
)
from engine.state_manager import StateManager
from engine.alias_resolver import AliasResolver


class TestContinuityContext:
    """Tests for the ContinuityContext dataclass."""
    
    def test_empty_context(self):
        """Test that empty context is detected correctly."""
        context = ContinuityContext(
            known_characters=[],
            known_relationships=[],
            known_character_states=[],
            chapter_number=0,
        )
        assert context.is_empty()
    
    def test_non_empty_context(self):
        """Test that non-empty context is detected correctly."""
        context = ContinuityContext(
            known_characters=[{"canonical_id": "harry_potter", "aliases": []}],
            known_relationships=[],
            known_character_states=[],
            chapter_number=1,
        )
        assert not context.is_empty()
    
    def test_to_characters_json_empty(self):
        """Test characters JSON for empty context."""
        context = ContinuityContext(
            known_characters=[],
            known_relationships=[],
            known_character_states=[],
            chapter_number=0,
        )
        assert context.to_characters_json() == "(No characters established yet)"
    
    def test_to_characters_json_with_data(self):
        """Test characters JSON with data."""
        context = ContinuityContext(
            known_characters=[
                {"canonical_id": "harry_potter", "aliases": ["the_boy_who_lived"]},
                {"canonical_id": "vernon_dursley", "aliases": ["uncle_vernon"]},
            ],
            known_relationships=[],
            known_character_states=[],
            chapter_number=1,
        )
        result = context.to_characters_json()
        parsed = json.loads(result)
        
        assert len(parsed) == 2
        assert parsed[0]["canonical_id"] == "harry_potter"
        assert "the_boy_who_lived" in parsed[0]["aliases"]
    
    def test_to_relationships_json_empty(self):
        """Test relationships JSON for empty context."""
        context = ContinuityContext(
            known_characters=[],
            known_relationships=[],
            known_character_states=[],
            chapter_number=0,
        )
        assert context.to_relationships_json() == "(No relationships established yet)"
    
    def test_to_relationships_json_with_data(self):
        """Test relationships JSON with data."""
        context = ContinuityContext(
            known_characters=[],
            known_relationships=[
                {"from": "vernon_dursley", "to": "harry_potter", "type": "hostile"},
            ],
            known_character_states=[],
            chapter_number=1,
        )
        result = context.to_relationships_json()
        parsed = json.loads(result)
        
        assert len(parsed) == 1
        assert parsed[0]["from"] == "vernon_dursley"
        assert parsed[0]["type"] == "hostile"
    
    def test_to_character_states_json_empty(self):
        """Test character states JSON for empty context."""
        context = ContinuityContext(
            known_characters=[],
            known_relationships=[],
            known_character_states=[],
            chapter_number=0,
        )
        assert context.to_character_states_json() == "(No character states established yet)"
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        context = ContinuityContext(
            known_characters=[{"canonical_id": "harry", "aliases": []}],
            known_relationships=[{"from": "a", "to": "b", "type": "friend"}],
            known_character_states=[{"character_id": "c", "state": "dead", "emotion": None}],
            chapter_number=5,
        )
        d = context.to_dict()
        
        assert d["chapter_number"] == 5
        assert len(d["known_characters"]) == 1
        assert len(d["known_relationships"]) == 1
        assert len(d["known_character_states"]) == 1


class TestContinuityContextBuilder:
    """Tests for the ContinuityContextBuilder class."""
    
    def test_build_empty_context(self):
        """Test building context with empty state."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 0)
        
        assert context.is_empty()
        assert context.chapter_number == 0
    
    def test_gather_known_characters(self):
        """Test gathering characters from alias resolver."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        # Register some characters
        alias_resolver.register_character("harry_potter", ["the_boy_who_lived"], 0)
        alias_resolver.register_character("vernon_dursley", ["uncle_vernon", "mr_dursley"], 0)
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 1)
        
        assert len(context.known_characters) == 2
        
        # Find Harry's entry
        harry = next(c for c in context.known_characters if c["canonical_id"] == "harry_potter")
        assert "the_boy_who_lived" in harry["aliases"]
        
        # Find Vernon's entry
        vernon = next(c for c in context.known_characters if c["canonical_id"] == "vernon_dursley")
        assert "uncle_vernon" in vernon["aliases"]
        assert "mr_dursley" in vernon["aliases"]
    
    def test_gather_known_relationships(self):
        """Test gathering relationships from state manager."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        # Add relationships
        state_manager.add_relationship("vernon_dursley", "harry_potter", "hostile")
        state_manager.add_relationship("harry_potter", "ron_weasley", "friendly")
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 1)
        
        assert len(context.known_relationships) == 2
        
        # Check hostile relationship exists
        hostile_rel = next(
            r for r in context.known_relationships 
            if r["from"] == "vernon_dursley" and r["to"] == "harry_potter"
        )
        assert hostile_rel["type"] == "hostile"
    
    def test_gather_known_character_states_dead(self):
        """Test gathering dead character states."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        # Mark character as dead
        state_manager.mark_dead("quirrell")
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 1)
        
        assert len(context.known_character_states) == 1
        assert context.known_character_states[0]["character_id"] == "quirrell"
        assert context.known_character_states[0]["state"] == "dead"
    
    def test_gather_known_character_states_emotions(self):
        """Test gathering character emotions."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        # Set character emotions
        state_manager.persistent_emotions["harry_potter"] = "sad"
        state_manager.persistent_emotions["ron_weasley"] = "angry"
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 1)
        
        assert len(context.known_character_states) == 2
        
        harry_state = next(s for s in context.known_character_states if s["character_id"] == "harry_potter")
        assert harry_state["emotion"] == "sad"
        assert harry_state["state"] == "alive"
    
    def test_dead_character_with_emotion(self):
        """Test that dead characters can also have emotions recorded."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        # Character is dead but had emotion
        state_manager.mark_dead("lily_potter")
        state_manager.persistent_emotions["lily_potter"] = "loving"
        
        builder = ContinuityContextBuilder()
        context = builder.build_context(state_manager, alias_resolver, 1)
        
        assert len(context.known_character_states) == 1
        lily_state = context.known_character_states[0]
        assert lily_state["character_id"] == "lily_potter"
        assert lily_state["state"] == "dead"
        assert lily_state["emotion"] == "loving"


class TestBuildContinuityContextFunction:
    """Tests for the convenience function."""
    
    def test_convenience_function(self):
        """Test that convenience function works."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        alias_resolver.register_character("harry_potter", [], 0)
        state_manager.add_relationship("a", "b", "friend")
        
        context = build_continuity_context(state_manager, alias_resolver, 5)
        
        assert context.chapter_number == 5
        assert len(context.known_characters) == 1
        assert len(context.known_relationships) == 1


class TestContinuityContextIntegration:
    """Integration tests for continuity context with extraction flow."""
    
    def test_chapter_accumulation(self):
        """Test that context accumulates across chapters."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        builder = ContinuityContextBuilder()
        
        # Chapter 0: Empty context
        context0 = builder.build_context(state_manager, alias_resolver, 0)
        assert context0.is_empty()
        
        # Simulate extraction from chapter 0
        alias_resolver.register_character("harry_potter", ["the_boy"], 0)
        alias_resolver.register_character("vernon_dursley", ["uncle_vernon"], 0)
        state_manager.add_relationship("vernon_dursley", "harry_potter", "hostile")
        
        # Chapter 1: Context should have chapter 0's data
        context1 = builder.build_context(state_manager, alias_resolver, 1)
        assert not context1.is_empty()
        assert len(context1.known_characters) == 2
        assert len(context1.known_relationships) == 1
        
        # Verify hostile relationship is in context
        json_str = context1.to_relationships_json()
        assert "hostile" in json_str
        assert "vernon_dursley" in json_str
    
    def test_context_serialization_roundtrip(self):
        """Test that context can be serialized and used in prompt."""
        state_manager = StateManager()
        alias_resolver = AliasResolver()
        
        alias_resolver.register_character("vernon_dursley", ["uncle_vernon", "mr_dursley"], 0)
        state_manager.add_relationship("vernon_dursley", "harry_potter", "hostile")
        state_manager.mark_dead("quirrell")
        
        context = build_continuity_context(state_manager, alias_resolver, 5)
        
        # All JSON outputs should be valid
        chars_json = context.to_characters_json()
        rels_json = context.to_relationships_json()
        states_json = context.to_character_states_json()
        
        # Parse to verify validity
        chars = json.loads(chars_json)
        rels = json.loads(rels_json)
        states = json.loads(states_json)
        
        assert len(chars) == 1
        assert len(rels) == 1
        assert len(states) == 1
