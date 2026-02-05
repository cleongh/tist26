"""
Relation - Represents a time-indexed relation in the LKG.

Part of the domain model for state management.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Relation:
    """
    Represents a time-indexed relation in the Logic Knowledge Graph.
    
    Relations encode facts like:
        - relationship(C1, C2, Type, T) - Character relationships
        - present(E, L, T) - Entity presence at location
        - carries(C, I, T) - Character possession of item
        - connected(L1, L2, T) - Location connectivity
    
    Attributes:
        predicate: The relation type ('relationship', 'present', 'carries', 'connected')
        args: Tuple of arguments to the predicate
        time: Time index when this relation holds
        source_event: Optional event ID that established this relation
    """
    predicate: str  # 'relationship', 'present', 'carries', 'connected'
    args: Tuple[str, ...]
    time: int
    source_event: Optional[str] = None
