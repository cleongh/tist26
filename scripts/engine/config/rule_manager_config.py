"""
Rule Manager Configuration - Patterns and constants for rule projection.

Phase 8.11: Entity extraction patterns for ASP rules.
"""

import re
from typing import FrozenSet, List, Pattern

# Regex patterns for extracting entity references from ASP rules
# These patterns match common entity-referencing facts in story rules
ENTITY_PATTERNS: List[Pattern] = [
    # story_exception(violation_type, entity).
    re.compile(r'story_exception\s*\(\s*\w+\s*,\s*(\w+)\s*\)'),
    # is_ghost(entity). or is_vampire(entity). etc.
    re.compile(r'is_\w+\s*\(\s*(\w+)\s*\)'),
    # can_fly(entity). or can_use_magic(entity). etc.
    re.compile(r'can_\w+\s*\(\s*(\w+)\s*\)'),
    # has_trait(entity, trait). or has_ability(entity, ability). etc.
    re.compile(r'has_\w+\s*\(\s*(\w+)\s*\)'),
    # typically_friendly(entity1, entity2). or typically_hostile(entity1, entity2).
    re.compile(r'typically_\w+\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    # relationship_rule(subject, predicate, object, event).
    re.compile(r'relationship_rule\s*\(\s*(\w+)\s*,\s*\w+\s*,\s*(\w+)\s*,'),
    # trait_rule(subject, trait, event).
    re.compile(r'trait_rule\s*\(\s*(\w+)\s*,'),
    # location_rule(subject, location, event).
    re.compile(r'location_rule\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # possession_rule(subject, item, event).
    re.compile(r'possession_rule\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # character(entity). or location(entity). or item(entity).
    re.compile(r'(?:character|location|item)\s*\(\s*(\w+)\s*\)'),
    # trait(entity, trait).
    re.compile(r'trait\s*\(\s*(\w+)\s*,'),
    # is_dead(entity).
    re.compile(r'is_dead\s*\(\s*(\w+)\s*\)'),
    # present(entity, location, time).
    re.compile(r'present\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # relationship(char1, char2, type, ...).
    re.compile(r'relationship\s*\(\s*(\w+)\s*,\s*(\w+)\s*,'),
    # Generic single-argument fact: predicate(entity).
    # This catches patterns like can_fly(entity), typically_friendly(entity), etc.
    re.compile(r'(\w+)\s*\(\s*(\w+)\s*\)\.'),
    # Generic two-argument fact: predicate(entity1, entity2).
    # This catches patterns like typically_friendly(char1, char2), etc.
    re.compile(r'(\w+)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\.'),
]

# Reserved ASP keywords and built-ins that are NOT entities
RESERVED_WORDS: FrozenSet[str] = frozenset({
    # ASP keywords
    'not', 'true', 'false', 
    # Common predicates (these are predicate names, not entities)
    'violation', 'story_override', 'story_exception',
    'is_ghost', 'is_dead', 'is_alive', 'is_vampire',
    'can_fly', 'can_use_magic', 'can_teleport',
    'has_trait', 'has_ability', 'has_power',
    'gravity_applies', 'cannot_fly',
    'character', 'location', 'item', 'trait', 'present',
    'relationship', 'relationship_rule', 'trait_rule',
    'location_rule', 'possession_rule', 'temporal_rule',
    'friends_help_friends', 'typically_friendly',
    # Categories
    'causality', 'coherence', 'temporal', 'emotional',
    # Variables (uppercase single letters)
    'x', 'y', 'z', 'c', 'e', 'd', 't', 'l',
    # Generic placeholders
    'entity', 'category', 'type', 'time', 'event', 'unknown',
    # Generic nouns that are not entities
    'object', 'human', 'person', 'thing',
})
