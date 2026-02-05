"""
Relationship - A relationship projected into the current ASP context.

Phase 8.10: Represents character relationships that pass the active universe filter.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..preprocessors import AspConverter


@dataclass
class Relationship:
    """
    A relationship projected into the current ASP context.
    
    Attributes:
        source: First character in the relationship
        target: Second character in the relationship
        rel_type: Type of relationship (friend, enemy, family, etc.)
        provenance: How this relationship was established
    """
    source: str
    target: str
    rel_type: str
    provenance: str = "persistent_registry"
    
    def to_relationship_fact(self, asp_converter: 'AspConverter' = None) -> str:
        """
        Generate relationship/3 fact (no time index).
        
        Args:
            asp_converter: Optional AspConverter instance
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.relationship_to_asp(self)
    
    def to_initial_relationship_fact(self, asp_converter: 'AspConverter' = None) -> str:
        """
        Generate initial_relationship fact for EC framework.
        
        Args:
            asp_converter: Optional AspConverter instance
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.initial_relationship_to_asp(self)
    
    def to_previous_relationship_fact(self, asp_converter: 'AspConverter' = None) -> str:
        """
        Generate previous_relationship fact for cross-chapter continuity.
        
        Args:
            asp_converter: Optional AspConverter instance
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        return asp_converter.previous_relationship_to_asp(self)
