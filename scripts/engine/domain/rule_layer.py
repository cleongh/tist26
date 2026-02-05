"""
Rule Layer Enum.

Rule layer priority for ASP rules.
"""

from enum import Enum


class RuleLayer(Enum):
    """
    Rule layer priority (higher = more priority).
    
    Per LOGIC_DESIGN.md Section 3.1:
        Rule Layers (Priority Order):
            1. Story-Specific Rules - override all others
            2. Learned Rules - inferred via ILASP
            3. Universal Rules - default assumptions
    """
    UNIVERSAL = 1
    LEARNED = 2
    STORY = 3
