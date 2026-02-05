"""
Relationship Manager - Filters and manages relationship projections.

Phase 8.10: Ensures relationships are included in ASP only when:
1. BOTH endpoints are in the active ASP universe
2. The relationship has not been invalidated or superseded
3. Relationships are emitted as current-time facts (no historical index)

Phase 8.11.2: Debug instrumentation for relationship projection validation.
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
import re
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from ..domain import Relationship, FilteredRelationshipResult
from ..config import relationship_manager_config as rel_config

if TYPE_CHECKING:
    from ..active_universe import ActiveUniverseResult

logger = logging.getLogger(__name__)


class RelationshipManager:
    """
    Manages relationship filtering and projection into ASP context.
    
    Provides:
        - Filtering relationships by active universe
        - Debug instrumentation for validation
        - ASP fact filtering
    
    Does NOT:
        - Store relationships (handled by StateManager)
        - Infer new relationships
        - Modify relationship content
    """
    
    def __init__(self):
        """Initialize the RelationshipManager."""
        pass
    
    # =========================================================================
    # DEBUG INSTRUMENTATION (Phase 8.11.2)
    # =========================================================================
    
    @staticmethod
    def enable_relationship_debug() -> None:
        """Enable debug instrumentation for relationship filtering."""
        rel_config._DEBUG_RELATIONSHIP = True
        logger.info("Relationship filtering debug enabled")
    
    @staticmethod
    def disable_relationship_debug() -> None:
        """Disable debug instrumentation for relationship filtering."""
        rel_config._DEBUG_RELATIONSHIP = False
    
    @staticmethod
    def is_relationship_debug_enabled() -> bool:
        """Check if relationship debug is enabled."""
        return rel_config._DEBUG_RELATIONSHIP
    
    @staticmethod
    def reset_relationship_debug_stats() -> None:
        """Reset debug statistics for a new story."""
        rel_config._debug_chapter_stats.clear()
    
    @staticmethod
    def get_relationship_debug_stats() -> Dict[int, Dict[str, int]]:
        """
        Get per-chapter relationship filtering statistics.
        
        Returns:
            Dict mapping chapter_number -> {
                'examined': count of persistent relationships examined,
                'projected': count of relationships projected into ASP,
                'filtered': count of relationships filtered out
            }
        """
        # Return deep copy to prevent external modification
        return {ch: stats.copy() for ch, stats in rel_config._debug_chapter_stats.items()}
    
    @staticmethod
    def _log_chapter_stats(chapter: int, examined: int, projected: int, filtered: int) -> None:
        """
        Log relationship filtering stats for a chapter (debug mode only).
        
        Args:
            chapter: Chapter number
            examined: Number of persistent relationships examined
            projected: Number of relationships projected into ASP
            filtered: Number of relationships filtered out
        """
        if not rel_config._DEBUG_RELATIONSHIP:
            return
        
        # Store stats
        rel_config._debug_chapter_stats[chapter] = {
            'examined': examined,
            'projected': projected,
            'filtered': filtered,
        }
        
        # Log without entity names (privacy/security)
        logger.info(
            f"[RelFilter Ch{chapter}] examined={examined} projected={projected} filtered={filtered}"
        )
    
    # =========================================================================
    # RELATIONSHIP FILTERING
    # =========================================================================
    
    @staticmethod
    def filter_active_relationships(
        persistent_relationships: Dict[Tuple[str, str], str],
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> FilteredRelationshipResult:
        """
        Filter persistent relationships by the active ASP universe.
        
        A relationship R(A, B, Type) is included IFF:
        1. A is in the active ASP universe
        2. B is in the active ASP universe
        
        Args:
            persistent_relationships: Dict of (char1, char2) -> rel_type
            active_universe: The active entity universe. If None, all relationships
                           are included (no filtering).
            
        Returns:
            FilteredRelationshipResult with filtered relationships
        """
        result = FilteredRelationshipResult()
        result.total_in_registry = len(persistent_relationships)
        
        # Get the active entity set (if filtering)
        all_entities: Optional[Set[str]] = None
        if active_universe is not None:
            all_entities = active_universe.all_entities
        
        # Filter each relationship
        for (char1, char2), rel_type in persistent_relationships.items():
            # Check if both endpoints are in the active universe
            if all_entities is not None:
                if char1 not in all_entities or char2 not in all_entities:
                    result.filtered_count += 1
                    continue
            
            # Create relationship
            relationship = Relationship(
                source=char1,
                target=char2,
                rel_type=rel_type,
                provenance="persistent_registry",
            )
            result.projected.append(relationship)
        
        logger.debug(
            f"Relationship filtering: {result.projected_count} included, "
            f"{result.filtered_count} filtered out of {result.total_in_registry} total"
        )
        
        return result
    
    @staticmethod
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
    
    @staticmethod
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
