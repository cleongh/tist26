"""
Alias Resolver - Core Canonical Identity & Alias Resolution

Responsibilities:
    - Maintain mapping from aliases to canonical IDs
    - Normalize all references to canonical IDs
    - Determine if a canonical ID is inferior to another
    - Promote canonical IDs when better ones are found
    - Guarantee: one entity = one logic symbol

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
    - Logic-first architecture: ASP is the source of truth

This is the base class for alias resolution. Entity-specific managers
(CharacterAliasManager, LocationAliasManager) use this class for
core alias operations.
"""

from typing import Dict, Set, Optional, Tuple, List, Any
import re
import logging

from ..domain import PromotionReason, CanonicalPromotion

logger = logging.getLogger(__name__)


class AliasResolver:
    """
    Core alias resolution functionality.
    
    Maintains a bidirectional mapping:
    - alias_to_canonical: alias -> canonical_id
    - canonical_to_aliases: canonical_id -> set of aliases
    
    All references are normalized to canonical IDs before being sent 
    to the ASP solver.
    
    Per LOGIC_DESIGN.md Section 3.2:
    - Each entity has exactly one canonical ID
    """
    
    def __init__(self):
        # alias -> canonical_id
        self._alias_to_canonical: Dict[str, str] = {}
        
        # canonical_id -> set of known aliases
        self._canonical_to_aliases: Dict[str, Set[str]] = {}
        
        # canonical_id -> full name (for promotion comparisons)
        self._canonical_to_full_name: Dict[str, str] = {}
        
        # Track when aliases were first seen
        self._alias_first_seen: Dict[str, int] = {}
        
        # Track entities that have been promoted (max once per entity)
        self._promoted_entities: Set[str] = set()
        
        # Promotion log for auditing
        self._promotions: List[CanonicalPromotion] = []
        
        # Statistics
        self._resolutions_made: int = 0
    
    def reset(self) -> None:
        """Reset the resolver to initial state."""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._canonical_to_full_name.clear()
        self._alias_first_seen.clear()
        self._promoted_entities.clear()
        self._promotions.clear()
        self._resolutions_made = 0
    
    # =========================================================================
    # CORE RESOLUTION METHODS
    # =========================================================================
    
    def resolve(self, identifier: str) -> str:
        """
        Resolve an identifier to its canonical ID.
        
        If the identifier is unknown, returns it unchanged (assumed canonical).
        """
        if not identifier:
            return identifier
            
        normalized = self.normalize_id(identifier)
        
        if normalized in self._alias_to_canonical:
            self._resolutions_made += 1
            return self._alias_to_canonical[normalized]
        
        # Unknown identifier - return as-is (might be new entity)
        return normalized
    
    def get_canonical_id(self, identifier: str) -> Optional[str]:
        """
        Get canonical ID for an identifier, or None if unknown.
        """
        if not identifier:
            return None
        normalized = self.normalize_id(identifier)
        return self._alias_to_canonical.get(normalized)
    
    def get_aliases(self, canonical_id: str) -> Set[str]:
        """
        Get all known aliases for a canonical ID.
        """
        normalized = self.normalize_id(canonical_id)
        return self._canonical_to_aliases.get(normalized, set())
    
    def get_all_canonical_ids(self) -> Set[str]:
        """
        Get all registered canonical IDs.
        
        Returns:
            Set of all canonical IDs
        """
        return set(self._canonical_to_aliases.keys())
    
    def get_all_aliases(self) -> Dict[str, str]:
        """
        Get all alias-to-canonical mappings.
        
        Returns:
            Dict mapping alias to canonical ID
        """
        return dict(self._alias_to_canonical)
    
    def is_known(self, identifier: str) -> bool:
        """Check if an identifier (alias or canonical) is known."""
        return self.normalize_id(identifier) in self._alias_to_canonical
    
    # =========================================================================
    # ALIAS REGISTRATION (used by entity-specific managers)
    # =========================================================================
    
    def register_character(
        self,
        canonical_id: str,
        aliases: List[str],
        chapter_num: int,
        full_name: Optional[str] = None,
    ) -> None:
        """
        Register a character with aliases (convenience method for backward compatibility).
        
        Args:
            canonical_id: The canonical character ID
            aliases: List of aliases for this character
            chapter_num: Chapter number where first seen
            full_name: Optional full name for the character
        """
        # Normalize canonical_id
        canonical = self.normalize_id(canonical_id)
        
        # Register canonical as its own alias
        self.register_alias(canonical, canonical, chapter_num)
        
        # Register all provided aliases
        for alias in aliases:
            norm_alias = self.normalize_id(alias)
            if norm_alias:
                self.register_alias(norm_alias, canonical, chapter_num)
        
        # Store full name if provided
        if full_name:
            self.set_full_name(canonical, full_name)
    
    def register_alias(
        self,
        alias: str,
        canonical_id: str,
        chapter_num: int,
    ) -> None:
        """
        Register an alias -> canonical_id mapping.
        
        Args:
            alias: The alias to register
            canonical_id: The canonical ID this alias maps to
            chapter_num: Chapter where this was first seen
        """
        if not alias:
            return
        
        self._alias_to_canonical[alias] = canonical_id
        
        if canonical_id not in self._canonical_to_aliases:
            self._canonical_to_aliases[canonical_id] = set()
        self._canonical_to_aliases[canonical_id].add(alias)
        
        if alias not in self._alias_first_seen:
            self._alias_first_seen[alias] = chapter_num
    
    def unregister_canonical(self, canonical_id: str) -> Set[str]:
        """
        Remove a canonical ID and return its aliases.
        
        Args:
            canonical_id: The canonical ID to remove
            
        Returns:
            The set of aliases that were registered to this canonical
        """
        aliases = self._canonical_to_aliases.pop(canonical_id, set())
        
        if canonical_id in self._canonical_to_full_name:
            del self._canonical_to_full_name[canonical_id]
        
        return aliases
    
    def set_full_name(self, canonical_id: str, full_name: str) -> None:
        """Store the full name for a canonical ID."""
        self._canonical_to_full_name[canonical_id] = full_name
    
    def get_full_name(self, canonical_id: str) -> Optional[str]:
        """Get the full name for a canonical ID."""
        return self._canonical_to_full_name.get(canonical_id)
    
    def get_first_seen_chapter(self, alias: str) -> Optional[int]:
        """Get the chapter where an alias was first seen."""
        return self._alias_first_seen.get(alias)
    
    def set_first_seen_chapter(self, alias: str, chapter: int) -> None:
        """Set the first-seen chapter for an alias."""
        self._alias_first_seen[alias] = chapter
    
    def mark_promoted(self, normalized_full_name: str) -> None:
        """Mark an entity (by normalized full name) as promoted."""
        self._promoted_entities.add(normalized_full_name)
    
    def is_promoted(self, normalized_full_name: str) -> bool:
        """Check if an entity has already been promoted."""
        return normalized_full_name in self._promoted_entities
    
    def add_promotion(self, promotion: CanonicalPromotion) -> None:
        """Add a promotion record to the audit log."""
        self._promotions.append(promotion)
    
    def get_promotions(self) -> List[CanonicalPromotion]:
        """Get all promotion records."""
        return list(self._promotions)
    
    # =========================================================================
    # PROMOTION LOGIC
    # =========================================================================
    
    def is_inferior_canonical(
        self,
        existing_id: str,
        new_id: str,
        existing_full_name: str,
        new_full_name: str,
    ) -> Tuple[bool, Optional[PromotionReason]]:
        """
        Determine if an existing canonical ID is inferior to a new one.
        
        Uses conservative heuristics to prevent false promotions:
        1. Both full names must match exactly (normalized)
        2. The existing ID must be clearly inferior
        
        Args:
            existing_id: Current canonical ID
            new_id: Proposed new canonical ID
            existing_full_name: Full name of existing entity
            new_full_name: Full name of new entity
            
        Returns:
            Tuple of (is_inferior, reason) where reason is None if not inferior
        """
        # Normalize full names for comparison
        norm_existing_name = self.normalize_id(existing_full_name)
        norm_new_name = self.normalize_id(new_full_name)
        
        # CRITICAL: Full names must match exactly for promotion
        if norm_existing_name != norm_new_name:
            return False, None
        
        # If IDs are identical, no promotion needed
        if existing_id == new_id:
            return False, None
        
        # Count underscores (proxy for full snake_case name)
        existing_underscores = existing_id.count('_')
        new_underscores = new_id.count('_')
        
        # Heuristic 1: Shorter ID vs longer descriptive ID
        # e.g., "potter" vs "harry_potter"
        if len(new_id) > len(existing_id) * 1.5 and new_underscores > existing_underscores:
            return True, PromotionReason.LONGER_DESCRIPTIVE_ID
        
        # Heuristic 2: Partial name vs full name
        # e.g., "harry" vs "harry_potter", "potter" vs "harry_potter"
        if existing_underscores == 0 and new_underscores >= 1:
            # Check if existing is a substring of new
            if existing_id in new_id:
                return True, PromotionReason.FULL_NAME_VS_PARTIAL
        
        # Heuristic 3: Generic single token vs descriptive snake_case
        # e.g., "shop" vs "ollivanders_shop"
        if (existing_underscores == 0 and 
            new_underscores >= 1 and 
            len(existing_id) < 10 and
            len(new_id) > len(existing_id) + 3):
            return True, PromotionReason.SNAKE_CASE_VS_GENERIC
        
        return False, None
    
    def promote_canonical(
        self,
        old_canonical: str,
        new_canonical: str,
        full_name: str,
        chapter: int,
        reason: PromotionReason,
        entity_type: str,
    ) -> None:
        """
        Promote a canonical ID to a better one.
        
        This:
        1. Migrates old canonical to be an alias of new canonical
        2. Updates all alias mappings to point to new canonical
        3. Logs the promotion as a structured warning
        
        Args:
            old_canonical: The inferior canonical ID being replaced
            new_canonical: The superior canonical ID to use
            full_name: The entity's full name
            chapter: Chapter where promotion occurred
            reason: Why the promotion is happening
            entity_type: "character" or "location"
        """
        # Record promotion for audit trail
        promotion = CanonicalPromotion(
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            full_name=full_name,
            chapter=chapter,
            reason=reason,
            entity_type=entity_type,
        )
        self._promotions.append(promotion)
        
        # Mark this entity as promoted (by normalized full name)
        self._promoted_entities.add(self.normalize_id(full_name))
        
        logger.warning(
            f"CANONICAL PROMOTION ({entity_type}): '{old_canonical}' -> '{new_canonical}' "
            f"(entity='{full_name}', reason={reason.value}, chapter={chapter})"
        )
        
        # Gather all aliases that pointed to old canonical
        old_aliases = self._canonical_to_aliases.get(old_canonical, set()).copy()
        
        # Initialize new canonical entry if not exists
        if new_canonical not in self._canonical_to_aliases:
            self._canonical_to_aliases[new_canonical] = set()
        
        # Migrate all aliases to new canonical
        for alias in old_aliases:
            self._alias_to_canonical[alias] = new_canonical
            self._canonical_to_aliases[new_canonical].add(alias)
        
        # Add old canonical as an alias of new canonical
        self._alias_to_canonical[old_canonical] = new_canonical
        self._canonical_to_aliases[new_canonical].add(old_canonical)
        
        # Add new canonical as alias of itself
        self._alias_to_canonical[new_canonical] = new_canonical
        self._canonical_to_aliases[new_canonical].add(new_canonical)
        
        # Remove old canonical entry
        if old_canonical in self._canonical_to_aliases:
            del self._canonical_to_aliases[old_canonical]
        
        # Update full name mapping
        if old_canonical in self._canonical_to_full_name:
            del self._canonical_to_full_name[old_canonical]
        self._canonical_to_full_name[new_canonical] = full_name
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    @staticmethod
    def normalize_id(identifier: str) -> str:
        """Normalize an identifier to snake_case."""
        if not identifier:
            return ""
        # Convert to lowercase
        normalized = identifier.lower()
        # Replace spaces and special chars with underscores
        normalized = re.sub(r'[^a-z0-9]+', '_', normalized)
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        # Collapse multiple underscores
        normalized = re.sub(r'_+', '_', normalized)
        return normalized
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get resolver statistics."""
        return {
            "total_canonical_ids": len(self._canonical_to_aliases),
            "total_aliases": len(self._alias_to_canonical),
            "resolutions_made": self._resolutions_made,
            "promotions_made": len(self._promotions),
        }
    
    def __repr__(self) -> str:
        return (
            f"AliasResolver(canonical={len(self._canonical_to_aliases)}, "
            f"aliases={len(self._alias_to_canonical)})"
        )
