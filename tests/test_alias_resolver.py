"""
Tests for AliasResolver - Canonical Identity & Alias Resolution

Phase 2: Ensure one entity = one logic symbol
"""

import pytest
from engine.alias_resolver import AliasResolver, AliasConflict


class TestAliasResolver:
    """Tests for the AliasResolver class."""
    
    def test_initialization(self):
        """Test that resolver initializes with empty state."""
        resolver = AliasResolver()
        assert resolver.get_statistics()["total_canonical_ids"] == 0
        assert resolver.get_statistics()["total_aliases"] == 0
    
    def test_register_character_simple(self):
        """Test registering a character with no aliases."""
        resolver = AliasResolver()
        conflicts = resolver.register_character("harry_potter", [], 0)
        
        assert len(conflicts) == 0
        assert resolver.resolve("harry_potter") == "harry_potter"
        assert resolver.is_known("harry_potter")
    
    def test_register_character_with_aliases(self):
        """Test registering a character with aliases."""
        resolver = AliasResolver()
        conflicts = resolver.register_character(
            "vernon_dursley",
            ["Uncle Vernon", "Mr. Dursley", "the_walrus"],
            0
        )
        
        assert len(conflicts) == 0
        
        # All aliases should resolve to canonical ID
        assert resolver.resolve("uncle_vernon") == "vernon_dursley"
        assert resolver.resolve("mr_dursley") == "vernon_dursley"
        assert resolver.resolve("the_walrus") == "vernon_dursley"
        assert resolver.resolve("vernon_dursley") == "vernon_dursley"
    
    def test_normalize_id(self):
        """Test ID normalization (snake_case conversion)."""
        resolver = AliasResolver()
        
        assert resolver._normalize_id("Uncle Vernon") == "uncle_vernon"
        assert resolver._normalize_id("Mr. Dursley") == "mr_dursley"
        assert resolver._normalize_id("Harry-Potter") == "harry_potter"
        assert resolver._normalize_id("  spaces  around  ") == "spaces_around"
        assert resolver._normalize_id("CAPS") == "caps"
    
    def test_resolve_unknown_returns_normalized(self):
        """Test that unknown identifiers are returned normalized."""
        resolver = AliasResolver()
        
        # Unknown IDs should be returned as-is (normalized)
        assert resolver.resolve("Unknown Person") == "unknown_person"
        assert resolver.resolve("new_character") == "new_character"
    
    def test_conflict_detection(self):
        """Test that alias conflicts are detected."""
        resolver = AliasResolver()
        
        # Register first character
        resolver.register_character("vernon_dursley", ["uncle_vernon"], 0)
        
        # Try to register same alias to different character - conflict!
        conflicts = resolver.register_character(
            "another_uncle",
            ["uncle_vernon"],  # Already mapped to vernon_dursley
            1
        )
        
        assert len(conflicts) == 1
        assert conflicts[0].alias == "uncle_vernon"
        assert "vernon_dursley" in conflicts[0].canonical_ids
        assert "another_uncle" in conflicts[0].canonical_ids
        
        # First mapping wins
        assert resolver.resolve("uncle_vernon") == "vernon_dursley"
    
    def test_normalize_extraction_events(self):
        """Test that events are normalized correctly."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon"], 0)
        resolver.register_character("harry_potter", ["the_boy"], 0)
        
        extraction = {
            "entities": {"characters": []},
            "events": [
                {"id": "e1", "agent": "uncle_vernon", "patient": "the_boy", "type": "attack"},
                {"id": "e2", "agent": "harry_potter", "patient": None, "type": "leave"},
            ],
            "initial_rules": [],
        }
        
        normalized, conflicts = resolver.normalize_extraction(extraction, 1)
        
        assert len(conflicts) == 0
        assert normalized["events"][0]["agent"] == "vernon_dursley"
        assert normalized["events"][0]["patient"] == "harry_potter"
        assert normalized["events"][1]["agent"] == "harry_potter"
    
    def test_normalize_extraction_relationships(self):
        """Test that relationships are normalized correctly."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon"], 0)
        resolver.register_character("harry_potter", [], 0)
        
        extraction = {
            "entities": {
                "characters": [],
                "relationships": [
                    {"from": "uncle_vernon", "to": "harry_potter", "type": "hostile"},
                ],
            },
            "events": [],
            "initial_rules": [],
        }
        
        normalized, conflicts = resolver.normalize_extraction(extraction, 1)
        
        assert normalized["entities"]["relationships"][0]["from"] == "vernon_dursley"
        assert normalized["entities"]["relationships"][0]["to"] == "harry_potter"
    
    def test_normalize_extraction_initial_rules(self):
        """Test that initial_rules are normalized correctly."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon"], 0)
        resolver.register_character("harry_potter", ["the_boy"], 0)
        
        extraction = {
            "entities": {"characters": []},
            "events": [],
            "initial_rules": [
                {"subject": "uncle_vernon", "predicate": "hates", "object": "the_boy"},
            ],
        }
        
        normalized, conflicts = resolver.normalize_extraction(extraction, 1)
        
        assert normalized["initial_rules"][0]["subject"] == "vernon_dursley"
        assert normalized["initial_rules"][0]["object"] == "harry_potter"
    
    def test_normalize_extraction_registers_new_characters(self):
        """Test that new characters in extraction are registered."""
        resolver = AliasResolver()
        
        extraction = {
            "entities": {
                "characters": [
                    {"id": "hermione_granger", "name": "Hermione Granger", "aliases": ["the_bushy_haired_girl"]},
                    {"id": "ron_weasley", "name": "Ron Weasley", "aliases": []},
                ],
            },
            "events": [],
            "initial_rules": [],
        }
        
        normalized, conflicts = resolver.normalize_extraction(extraction, 0)
        
        assert resolver.is_known("hermione_granger")
        assert resolver.is_known("the_bushy_haired_girl")
        assert resolver.is_known("ron_weasley")
        assert resolver.resolve("the_bushy_haired_girl") == "hermione_granger"
    
    def test_get_known_characters_context(self):
        """Test generating context for extraction prompt."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon", "mr_dursley"], 0)
        resolver.register_character("harry_potter", ["the_boy_who_lived"], 0)
        
        context = resolver.get_known_characters_context()
        
        assert len(context) == 2
        
        # Find Vernon's entry
        vernon_entry = next(c for c in context if c["canonical_id"] == "vernon_dursley")
        assert "uncle_vernon" in vernon_entry["aliases"]
        assert "mr_dursley" in vernon_entry["aliases"]
    
    def test_to_asp_facts(self):
        """Test generating ASP alias facts."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon", "mr_dursley"], 0)
        
        facts = resolver.to_asp_facts()
        
        assert "alias(uncle_vernon, vernon_dursley)." in facts
        assert "alias(mr_dursley, vernon_dursley)." in facts
        # Self-alias should not be generated
        assert "alias(vernon_dursley, vernon_dursley)." not in facts
    
    def test_reset(self):
        """Test that reset clears all state."""
        resolver = AliasResolver()
        resolver.register_character("harry_potter", ["the_boy"], 0)
        
        assert resolver.get_statistics()["total_canonical_ids"] == 1
        
        resolver.reset()
        
        assert resolver.get_statistics()["total_canonical_ids"] == 0
        assert not resolver.is_known("harry_potter")
    
    def test_statistics(self):
        """Test statistics tracking."""
        resolver = AliasResolver()
        resolver.register_character("vernon_dursley", ["uncle_vernon", "mr_dursley"], 0)
        resolver.register_character("harry_potter", [], 0)
        
        # Make some resolutions
        resolver.resolve("uncle_vernon")
        resolver.resolve("mr_dursley")
        resolver.resolve("unknown_person")  # Not a resolution
        
        stats = resolver.get_statistics()
        
        assert stats["total_canonical_ids"] == 2
        assert stats["total_aliases"] == 4  # vernon + 2 aliases + harry
        assert stats["resolutions_made"] == 2
    
    def test_cross_chapter_alias_accumulation(self):
        """Test that aliases accumulate across chapters."""
        resolver = AliasResolver()
        
        # Chapter 0: Initial character introduction
        extraction0 = {
            "entities": {
                "characters": [
                    {"id": "vernon_dursley", "name": "Vernon Dursley", "aliases": ["uncle_vernon"]},
                ],
            },
            "events": [],
            "initial_rules": [],
        }
        resolver.normalize_extraction(extraction0, 0)
        
        # Chapter 1: Same character, new alias
        extraction1 = {
            "entities": {
                "characters": [
                    {"id": "vernon_dursley", "name": "Vernon Dursley", "aliases": ["mr_dursley"]},
                ],
            },
            "events": [
                {"id": "e1", "agent": "mr_dursley", "patient": None, "type": "talk"},
            ],
            "initial_rules": [],
        }
        normalized, conflicts = resolver.normalize_extraction(extraction1, 1)
        
        assert len(conflicts) == 0
        
        # All aliases should resolve to canonical
        assert resolver.resolve("uncle_vernon") == "vernon_dursley"
        assert resolver.resolve("mr_dursley") == "vernon_dursley"
        
        # Event should be normalized
        assert normalized["events"][0]["agent"] == "vernon_dursley"
