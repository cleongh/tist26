"""
Relationship Projector - Re-projects persistent relationships into current ASP context.

Phase 8.10: Ensures relationships are included in ASP only when:
1. BOTH endpoints are in the active ASP universe
2. The relationship has not been invalidated or superseded
3. Relationships are emitted as current-time facts (no historical index)

Phase 8.11.2: Added debug instrumentation for relationship projection validation.
- Optional per-chapter logging of projection statistics
- Zero runtime cost when disabled
- No entity names logged by default

Per LOGIC_DESIGN.md Section 3.2:
- relationship(Character1, Character2, Type, Time) is a core relation
- Relationships must only involve valid, active entities

Per LOGIC_DESIGN.md Section 8:
- Python orchestrates; ASP reasons
- No relationship inference or modification in Python
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult
    from .state_manager import StateManager

logger = logging.getLogger(__name__)


# =============================================================================
# DEBUG INSTRUMENTATION (Phase 8.11.2)
# =============================================================================
# Zero-cost debug flag for relationship projection validation.
# When disabled (default), no debug code is executed.

_DEBUG_RELATIONSHIP_PROJECTION = False
_debug_chapter_stats: Dict[int, Dict[str, int]] = {}


def enable_relationship_debug() -> None:
    """Enable debug instrumentation for relationship projection."""
    global _DEBUG_RELATIONSHIP_PROJECTION
    _DEBUG_RELATIONSHIP_PROJECTION = True
    logger.info("Relationship projection debug enabled")


def disable_relationship_debug() -> None:
    """Disable debug instrumentation for relationship projection."""
    global _DEBUG_RELATIONSHIP_PROJECTION
    _DEBUG_RELATIONSHIP_PROJECTION = False


def is_relationship_debug_enabled() -> bool:
    """Check if relationship debug is enabled."""
    return _DEBUG_RELATIONSHIP_PROJECTION


def reset_relationship_debug_stats() -> None:
    """Reset debug statistics for a new story."""
    global _debug_chapter_stats
    _debug_chapter_stats = {}


def get_relationship_debug_stats() -> Dict[int, Dict[str, int]]:
    """
    Get per-chapter relationship projection statistics.
    
    Returns:
        Dict mapping chapter_number -> {
            'examined': count of persistent relationships examined,
            'projected': count of relationships projected into ASP,
            'filtered': count of relationships filtered out
        }
    """
    # Return deep copy to prevent external modification
    return {ch: stats.copy() for ch, stats in _debug_chapter_stats.items()}


def _log_chapter_stats(chapter: int, examined: int, projected: int, filtered: int) -> None:
    """
    Log relationship projection stats for a chapter (debug mode only).
    
    Args:
        chapter: Chapter number
        examined: Number of persistent relationships examined
        projected: Number of relationships projected into ASP
        filtered: Number of relationships filtered out
    """
    if not _DEBUG_RELATIONSHIP_PROJECTION:
        return
    
    # Store stats
    _debug_chapter_stats[chapter] = {
        'examined': examined,
        'projected': projected,
        'filtered': filtered,
    }
    
    # Log without entity names (privacy/security)
    logger.info(
        f"[RelProj Ch{chapter}] examined={examined} projected={projected} filtered={filtered}"
    )


@dataclass
class ProjectedRelationship:
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
    
    def to_relationship_fact(self) -> str:
        """Generate relationship/3 fact (no time index)."""
        return f"relationship({self.source}, {self.target}, {self.rel_type})."
    
    def to_initial_relationship_fact(self) -> str:
        """Generate initial_relationship fact for EC framework."""
        return f"initial_relationship({self.source}, {self.target}, {self.rel_type})."
    
    def to_previous_relationship_fact(self) -> str:
        """Generate previous_relationship fact for cross-chapter continuity."""
        return f"previous_relationship({self.source}, {self.target}, {self.rel_type})."


@dataclass
class RelationshipProjectionResult:
    """
    Result of relationship projection.
    
    Attributes:
        projected: Relationships that passed the active universe filter
        filtered_count: Number of relationships filtered out
        total_in_registry: Total relationships in the persistent registry
    """
    projected: List[ProjectedRelationship] = field(default_factory=list)
    filtered_count: int = 0
    total_in_registry: int = 0
    
    @property
    def projected_count(self) -> int:
        return len(self.projected)
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for diagnostics."""
        return {
            "total_in_registry": self.total_in_registry,
            "projected_count": self.projected_count,
            "filtered_count": self.filtered_count,
            "projected": [
                {"source": r.source, "target": r.target, "type": r.rel_type}
                for r in self.projected
            ],
        }


def project_relationships(
    persistent_relationships: Dict[Tuple[str, str], str],
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> RelationshipProjectionResult:
    """
    Project persistent relationships into the current ASP context.
    
    This is the main projection function. It reads from the persistent
    relationship registry and filters by the active universe.
    
    A relationship R(A, B, Type) is included IFF:
    1. A is in the active ASP universe
    2. B is in the active ASP universe
    
    Args:
        persistent_relationships: Dict of (char1, char2) -> rel_type
        active_universe: The active entity universe. If None, all relationships
                       are projected (no filtering).
        
    Returns:
        RelationshipProjectionResult with projected relationships
    """
    result = RelationshipProjectionResult()
    result.total_in_registry = len(persistent_relationships)
    
    # Get the active entity set (if filtering)
    all_entities: Optional[Set[str]] = None
    if active_universe is not None:
        all_entities = active_universe.all_entities
    
    # Project each relationship
    for (char1, char2), rel_type in persistent_relationships.items():
        # Check if both endpoints are in the active universe
        if all_entities is not None:
            if char1 not in all_entities or char2 not in all_entities:
                result.filtered_count += 1
                continue
        
        # Create projected relationship
        projected = ProjectedRelationship(
            source=char1,
            target=char2,
            rel_type=rel_type,
            provenance="persistent_registry",
        )
        result.projected.append(projected)
    
    logger.debug(
        f"Relationship projection: {result.projected_count} projected, "
        f"{result.filtered_count} filtered out of {result.total_in_registry} total"
    )
    
    return result


def project_relationships_to_asp_facts(
    persistent_relationships: Dict[Tuple[str, str], str],
    active_universe: Optional['ActiveUniverseResult'] = None,
    include_initial: bool = True,
    include_previous: bool = True,
    include_current: bool = False,
    chapter: Optional[int] = None,
) -> List[str]:
    """
    Project persistent relationships directly to ASP facts.
    
    Convenience function combining projection and fact generation.
    
    Phase 8.11.2: When debug is enabled and chapter is provided, logs
    projection statistics for validation.
    
    Args:
        persistent_relationships: Dict of (char1, char2) -> rel_type
        active_universe: Active entity universe for filtering
        include_initial: If True, include initial_relationship facts
        include_previous: If True, include previous_relationship facts
        include_current: If True, include relationship/3 facts
        chapter: Optional chapter number for debug logging
        
    Returns:
        List of ASP fact strings
    """
    result = project_relationships(persistent_relationships, active_universe)
    
    # Debug instrumentation (zero cost when disabled)
    if _DEBUG_RELATIONSHIP_PROJECTION and chapter is not None:
        _log_chapter_stats(
            chapter=chapter,
            examined=result.total_in_registry,
            projected=result.projected_count,
            filtered=result.filtered_count,
        )
    
    facts = []
    for rel in result.projected:
        if include_previous:
            facts.append(rel.to_previous_relationship_fact())
        if include_initial:
            facts.append(rel.to_initial_relationship_fact())
        if include_current:
            facts.append(rel.to_relationship_fact())
    
    return facts


# =============================================================================
# Universe Guard Functions
# =============================================================================

def is_relationship_in_universe(
    source: str,
    target: str,
    active_universe: Optional['ActiveUniverseResult'],
) -> bool:
    """
    Check if a relationship should be included based on active universe.
    
    A relationship is included IFF both endpoints are in the active universe.
    If no active universe is provided, all relationships are included.
    
    Args:
        source: First entity in the relationship
        target: Second entity in the relationship
        active_universe: The active entity universe (or None for no filtering)
        
    Returns:
        True if the relationship should be included in ASP
    """
    if active_universe is None:
        return True
    
    all_entities = active_universe.all_entities
    return source in all_entities and target in all_entities


def filter_relationship_facts(
    facts: List[str],
    active_universe: Optional['ActiveUniverseResult'],
) -> List[str]:
    """
    Filter relationship facts by active universe.
    
    Parses relationship facts and filters out those where either
    endpoint is not in the active universe.
    
    Args:
        facts: List of ASP fact strings
        active_universe: The active entity universe
        
    Returns:
        Filtered list of facts
    """
    if active_universe is None:
        return facts
    
    import re
    all_entities = active_universe.all_entities
    filtered = []
    
    # Pattern matches: relationship(A, B, ...) or initial_relationship(A, B, ...) etc.
    rel_pattern = re.compile(
        r'^(relationship|initial_relationship|previous_relationship)\(([^,]+),\s*([^,\)]+)'
    )
    
    for fact in facts:
        match = rel_pattern.match(fact)
        if match:
            source = match.group(2).strip()
            target = match.group(3).strip()
            if source in all_entities and target in all_entities:
                filtered.append(fact)
            # Silently skip relationships with inactive endpoints
        else:
            # Not a relationship fact, keep it
            filtered.append(fact)
    
    return filtered
