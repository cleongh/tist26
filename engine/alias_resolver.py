"""
Alias Resolver - Canonical Identity & Alias Resolution

Responsibilities:
    - Maintain mapping from aliases to canonical character IDs
    - Normalize all character references to canonical IDs
    - Detect and log conflicting alias mappings
    - Guarantee: one entity = one logic symbol

Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
    - Deterministic and explainable: every conclusion must trace back to rules
    - Logic-first architecture: ASP is the source of truth

Phase 2: This module ensures consistent character identity across chapters,
preventing issues like "uncle_vernon" vs "mr_dursley" referring to the same entity.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class PromotionReason(Enum):
    """Reason why a canonical ID was promoted."""
    LONGER_DESCRIPTIVE_ID = "longer_descriptive_id"
    FULL_NAME_VS_PARTIAL = "full_name_vs_partial"
    SNAKE_CASE_VS_GENERIC = "snake_case_vs_generic"


@dataclass
class CanonicalPromotion:
    """Records when a canonical ID is promoted to a better one."""
    old_canonical: str
    new_canonical: str
    full_name: str
    chapter: int
    reason: PromotionReason
    entity_type: str  # "character" or "location"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "old_canonical": self.old_canonical,
            "new_canonical": self.new_canonical,
            "full_name": self.full_name,
            "chapter": self.chapter,
            "reason": self.reason.value,
            "entity_type": self.entity_type,
        }


@dataclass
class AliasConflict:
    """Records when an alias maps to multiple canonical IDs."""
    alias: str
    canonical_ids: Set[str]
    first_seen_chapter: int
    conflict_chapter: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "canonical_ids": list(self.canonical_ids),
            "first_seen_chapter": self.first_seen_chapter,
            "conflict_chapter": self.conflict_chapter,
        }


class AliasResolver:
    """
    Resolves character and location aliases to canonical IDs.
    
    Maintains a bidirectional mapping for characters and locations:
    - alias_to_canonical: alias -> canonical_id
    - canonical_to_aliases: canonical_id -> set of aliases
    
    All character and location references (events, relationships, rules) are normalized
    to canonical IDs before being sent to the ASP solver.
    
    Per LOGIC_DESIGN.md Section 3.2:
    - character(X) and location(X) are core entity node types
    - Each entity has exactly one canonical ID
    """
    
    def __init__(self):
        # Character mappings: alias -> canonical_id
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
        
        # Location mappings: alias -> canonical_id
        self._location_alias_to_canonical: Dict[str, str] = {}
        
        # location canonical_id -> set of known aliases
        self._location_canonical_to_aliases: Dict[str, Set[str]] = {}
        
        # location canonical_id -> full name (for promotion comparisons)
        self._location_canonical_to_full_name: Dict[str, str] = {}
        
        # Track when location aliases were first seen
        self._location_alias_first_seen: Dict[str, int] = {}
        
        # Track location entities that have been promoted (max once)
        self._location_promoted_entities: Set[str] = set()
        
        # Location promotion log
        self._location_promotions: List[CanonicalPromotion] = []
        
        # Location containment: child -> parent (1-level containment)
        # e.g., {"kitchen": "house", "hallway": "house", "cupboard": "house"}
        self._location_containment: Dict[str, str] = {}
        
        # Reverse mapping: parent -> set of children
        # e.g., {"house": {"kitchen", "hallway", "cupboard"}}
        self._location_children: Dict[str, Set[str]] = {}
        
        # Conflicts detected (characters)
        self._conflicts: List[AliasConflict] = []
        
        # Location conflicts
        self._location_conflicts: List[AliasConflict] = []
        
        # Statistics
        self._resolutions_made: int = 0
        self._location_resolutions_made: int = 0
        self._chapters_processed: int = 0
    
    def reset(self) -> None:
        """Reset the resolver to initial state."""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._canonical_to_full_name.clear()
        self._alias_first_seen.clear()
        self._promoted_entities.clear()
        self._promotions.clear()
        self._location_alias_to_canonical.clear()
        self._location_canonical_to_aliases.clear()
        self._location_canonical_to_full_name.clear()
        self._location_alias_first_seen.clear()
        self._location_promoted_entities.clear()
        self._location_promotions.clear()
        self._location_containment.clear()
        self._location_children.clear()
        self._conflicts.clear()
        self._location_conflicts.clear()
        self._resolutions_made = 0
        self._location_resolutions_made = 0
        self._chapters_processed = 0

    def _is_inferior_canonical(
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
        norm_existing_name = self._normalize_id(existing_full_name)
        norm_new_name = self._normalize_id(new_full_name)
        
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

    def _promote_character_canonical(
        self,
        old_canonical: str,
        new_canonical: str,
        full_name: str,
        chapter: int,
        reason: PromotionReason,
    ) -> None:
        """
        Promote a character's canonical ID to a better one.
        
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
        """
        # Record promotion for audit trail
        promotion = CanonicalPromotion(
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            full_name=full_name,
            chapter=chapter,
            reason=reason,
            entity_type="character",
        )
        self._promotions.append(promotion)
        
        # Mark this entity as promoted (by normalized full name)
        self._promoted_entities.add(self._normalize_id(full_name))
        
        logger.warning(
            f"CANONICAL PROMOTION: '{old_canonical}' -> '{new_canonical}' "
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

    def _promote_location_canonical(
        self,
        old_canonical: str,
        new_canonical: str,
        full_name: str,
        chapter: int,
        reason: PromotionReason,
    ) -> None:
        """
        Promote a location's canonical ID to a better one.
        
        Same logic as character promotion but for locations.
        """
        # Record promotion for audit trail
        promotion = CanonicalPromotion(
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            full_name=full_name,
            chapter=chapter,
            reason=reason,
            entity_type="location",
        )
        self._location_promotions.append(promotion)
        
        # Mark this entity as promoted (by normalized full name)
        self._location_promoted_entities.add(self._normalize_id(full_name))
        
        logger.warning(
            f"LOCATION CANONICAL PROMOTION: '{old_canonical}' -> '{new_canonical}' "
            f"(entity='{full_name}', reason={reason.value}, chapter={chapter})"
        )
        
        # Gather all aliases that pointed to old canonical
        old_aliases = self._location_canonical_to_aliases.get(old_canonical, set()).copy()
        
        # Initialize new canonical entry if not exists
        if new_canonical not in self._location_canonical_to_aliases:
            self._location_canonical_to_aliases[new_canonical] = set()
        
        # Migrate all aliases to new canonical
        for alias in old_aliases:
            self._location_alias_to_canonical[alias] = new_canonical
            self._location_canonical_to_aliases[new_canonical].add(alias)
        
        # Add old canonical as an alias of new canonical
        self._location_alias_to_canonical[old_canonical] = new_canonical
        self._location_canonical_to_aliases[new_canonical].add(old_canonical)
        
        # Add new canonical as alias of itself
        self._location_alias_to_canonical[new_canonical] = new_canonical
        self._location_canonical_to_aliases[new_canonical].add(new_canonical)
        
        # Remove old canonical entry
        if old_canonical in self._location_canonical_to_aliases:
            del self._location_canonical_to_aliases[old_canonical]
        
        # Update full name mapping
        if old_canonical in self._location_canonical_to_full_name:
            del self._location_canonical_to_full_name[old_canonical]
        self._location_canonical_to_full_name[new_canonical] = full_name
    
    def register_character(
        self,
        canonical_id: str,
        aliases: List[str],
        chapter_num: int,
        full_name: Optional[str] = None,
    ) -> List[AliasConflict]:
        """
        Register a character's canonical ID and aliases.
        
        Supports canonical ID promotion: if a new canonical ID is introduced
        whose normalized full name exactly matches an existing entity's full name,
        and the existing canonical ID is inferior (shorter, partial name, etc.),
        the new ID is promoted to canonical and the old becomes an alias.
        
        Args:
            canonical_id: The canonical snake_case character ID
            aliases: List of alternate names/IDs for this character
            chapter_num: Chapter number where this was extracted
            full_name: The full display name of the character (for promotion checks)
            
        Returns:
            List of any conflicts detected during registration
        """
        new_conflicts = []
        canonical_id = self._normalize_id(canonical_id)
        
        # The canonical ID is always an alias of itself
        all_aliases = [canonical_id] + [self._normalize_id(a) for a in aliases if a]
        all_aliases = [a for a in all_aliases if a]  # Filter empty
        
        # Derive full_name if not provided
        if not full_name:
            full_name = canonical_id.replace('_', ' ').title()
        
        normalized_full_name = self._normalize_id(full_name)
        
        # Check for promotion opportunity BEFORE registering
        # Look for existing entities with the same normalized full name
        if normalized_full_name not in self._promoted_entities:
            for existing_canonical, existing_full in self._canonical_to_full_name.items():
                existing_norm_full = self._normalize_id(existing_full)
                
                # Check if this is the same entity with a potentially inferior ID
                is_inferior, reason = self._is_inferior_canonical(
                    existing_canonical, canonical_id, existing_full, full_name
                )
                
                if is_inferior and reason:
                    # Promote: new canonical ID replaces the old
                    self._promote_character_canonical(
                        old_canonical=existing_canonical,
                        new_canonical=canonical_id,
                        full_name=full_name,
                        chapter=chapter_num,
                        reason=reason,
                    )
                    # The old canonical is now an alias; continue with normal registration
                    break
        
        # Initialize canonical entry if new
        if canonical_id not in self._canonical_to_aliases:
            self._canonical_to_aliases[canonical_id] = set()
        
        # Store full name for future promotion checks
        if canonical_id not in self._canonical_to_full_name:
            self._canonical_to_full_name[canonical_id] = full_name
        
        for alias in all_aliases:
            if not alias:
                continue
                
            # Check for conflict: alias already maps to different canonical
            if alias in self._alias_to_canonical:
                existing_canonical = self._alias_to_canonical[alias]
                if existing_canonical != canonical_id:
                    conflict = AliasConflict(
                        alias=alias,
                        canonical_ids={existing_canonical, canonical_id},
                        first_seen_chapter=self._alias_first_seen.get(alias, chapter_num),
                        conflict_chapter=chapter_num,
                    )
                    new_conflicts.append(conflict)
                    self._conflicts.append(conflict)
                    logger.warning(
                        f"Alias conflict: '{alias}' maps to both "
                        f"'{existing_canonical}' and '{canonical_id}'"
                    )
                    # Keep existing mapping (first seen wins)
                    continue
            
            # Register the alias
            self._alias_to_canonical[alias] = canonical_id
            self._canonical_to_aliases[canonical_id].add(alias)
            
            if alias not in self._alias_first_seen:
                self._alias_first_seen[alias] = chapter_num
        
        return new_conflicts
    
    def register_location(
        self,
        canonical_id: str,
        aliases: List[str],
        chapter_num: int,
        full_name: Optional[str] = None,
        parent_location: Optional[str] = None,
    ) -> List[AliasConflict]:
        """
        Register a location's canonical ID and aliases.
        
        Per LOGIC_DESIGN.md Section 3.2, location(X) is a core entity type.
        
        Supports canonical ID promotion: if a new canonical ID is introduced
        whose normalized full name exactly matches an existing entity's full name,
        and the existing canonical ID is inferior (shorter, partial name, etc.),
        the new ID is promoted to canonical and the old becomes an alias.
        
        Supports location containment: if parent_location is provided, this
        location is registered as a sub-location of the parent. This enables
        coherent travel within the same container (e.g., kitchen → hallway
        within "house").
        
        Args:
            canonical_id: The canonical snake_case location ID
            aliases: List of alternate names/IDs for this location
            chapter_num: Chapter number where this was extracted
            full_name: The full display name of the location (for promotion checks)
            parent_location: Optional parent/container location ID
            
        Returns:
            List of any conflicts detected during registration
        """
        new_conflicts = []
        canonical_id = self._normalize_id(canonical_id)
        
        # The canonical ID is always an alias of itself
        all_aliases = [canonical_id] + [self._normalize_id(a) for a in aliases if a]
        all_aliases = [a for a in all_aliases if a]  # Filter empty
        
        # Derive full_name if not provided
        if not full_name:
            full_name = canonical_id.replace('_', ' ').title()
        
        normalized_full_name = self._normalize_id(full_name)
        
        # Check for promotion opportunity BEFORE registering
        # Look for existing entities with the same normalized full name
        if normalized_full_name not in self._location_promoted_entities:
            for existing_canonical, existing_full in self._location_canonical_to_full_name.items():
                existing_norm_full = self._normalize_id(existing_full)
                
                # Check if this is the same entity with a potentially inferior ID
                is_inferior, reason = self._is_inferior_canonical(
                    existing_canonical, canonical_id, existing_full, full_name
                )
                
                if is_inferior and reason:
                    # Promote: new canonical ID replaces the old
                    self._promote_location_canonical(
                        old_canonical=existing_canonical,
                        new_canonical=canonical_id,
                        full_name=full_name,
                        chapter=chapter_num,
                        reason=reason,
                    )
                    # The old canonical is now an alias; continue with normal registration
                    break
        
        # Initialize canonical entry if new
        if canonical_id not in self._location_canonical_to_aliases:
            self._location_canonical_to_aliases[canonical_id] = set()
        
        # Store full name for future promotion checks
        if canonical_id not in self._location_canonical_to_full_name:
            self._location_canonical_to_full_name[canonical_id] = full_name
        
        # Register containment if parent provided
        if parent_location:
            self.set_location_containment(canonical_id, parent_location)
        
        for alias in all_aliases:
            if not alias:
                continue
                
            # Check for conflict: alias already maps to different canonical
            if alias in self._location_alias_to_canonical:
                existing_canonical = self._location_alias_to_canonical[alias]
                if existing_canonical != canonical_id:
                    conflict = AliasConflict(
                        alias=alias,
                        canonical_ids={existing_canonical, canonical_id},
                        first_seen_chapter=self._location_alias_first_seen.get(alias, chapter_num),
                        conflict_chapter=chapter_num,
                    )
                    new_conflicts.append(conflict)
                    self._location_conflicts.append(conflict)
                    logger.warning(
                        f"Location alias conflict: '{alias}' maps to both "
                        f"'{existing_canonical}' and '{canonical_id}'"
                    )
                    # Keep existing mapping (first seen wins)
                    continue
            
            # Register the alias
            self._location_alias_to_canonical[alias] = canonical_id
            self._location_canonical_to_aliases[canonical_id].add(alias)
            
            if alias not in self._location_alias_first_seen:
                self._location_alias_first_seen[alias] = chapter_num
        
        return new_conflicts
    
    def resolve_location(self, identifier: str) -> str:
        """
        Resolve a location identifier to its canonical ID.
        
        If the identifier is unknown, returns it unchanged (assumed canonical).
        """
        if not identifier:
            return identifier
            
        normalized = self._normalize_id(identifier)
        
        if normalized in self._location_alias_to_canonical:
            self._location_resolutions_made += 1
            return self._location_alias_to_canonical[normalized]
        
        # Unknown identifier - return as-is (might be new location)
        return normalized
    
    def get_location_canonical_id(self, identifier: str) -> Optional[str]:
        """
        Get canonical ID for a location identifier, or None if unknown.
        """
        if not identifier:
            return None
        normalized = self._normalize_id(identifier)
        return self._location_alias_to_canonical.get(normalized)
    
    def get_location_aliases(self, canonical_id: str) -> Set[str]:
        """
        Get all known aliases for a location canonical ID.
        """
        normalized = self._normalize_id(canonical_id)
        return self._location_canonical_to_aliases.get(normalized, set())
    
    def is_location_known(self, identifier: str) -> bool:
        """Check if a location identifier (alias or canonical) is known."""
        return self._normalize_id(identifier) in self._location_alias_to_canonical

    # =========================================================================
    # LOCATION CONTAINMENT (Phase 2 - Travel Coherence)
    # =========================================================================
    
    def set_location_containment(
        self,
        child_location: str,
        parent_location: str,
    ) -> None:
        """
        Set a containment relationship between locations.
        
        This establishes that child_location is contained within parent_location.
        Examples:
            set_location_containment("kitchen", "house")
            set_location_containment("cupboard", "house")
            set_location_containment("shop", "diagon_alley")
        
        Containment enables coherent travel: moving between locations with the
        same parent does not trigger time_travel violations.
        
        Args:
            child_location: The contained/sub-location
            parent_location: The container/parent location
        """
        child = self._normalize_id(child_location)
        parent = self._normalize_id(parent_location)
        
        if not child or not parent:
            return
        
        # Resolve to canonical IDs if they're aliases
        child = self.resolve_location(child)
        parent = self.resolve_location(parent)
        
        # Prevent self-containment
        if child == parent:
            logger.warning(f"Cannot set location '{child}' as contained in itself")
            return
        
        # Prevent circular containment (A ⊂ B and B ⊂ A)
        if self.get_parent_location(parent) == child:
            logger.warning(
                f"Circular containment detected: '{child}' and '{parent}'"
            )
            return
        
        # Set containment
        self._location_containment[child] = parent
        
        # Update reverse mapping
        if parent not in self._location_children:
            self._location_children[parent] = set()
        self._location_children[parent].add(child)
        
        logger.debug(f"Location containment: '{child}' ⊂ '{parent}'")
    
    def get_parent_location(self, location: str) -> Optional[str]:
        """
        Get the parent/container location of a given location.
        
        Args:
            location: The location to query
            
        Returns:
            The parent location ID, or None if location has no parent
        """
        if not location:
            return None
        normalized = self.resolve_location(self._normalize_id(location))
        return self._location_containment.get(normalized)
    
    def get_child_locations(self, location: str) -> Set[str]:
        """
        Get all direct child locations of a given location.
        
        Args:
            location: The parent location to query
            
        Returns:
            Set of child location IDs (empty if no children)
        """
        if not location:
            return set()
        normalized = self.resolve_location(self._normalize_id(location))
        return self._location_children.get(normalized, set()).copy()
    
    def share_container(self, location1: str, location2: str) -> bool:
        """
        Check if two locations share the same immediate container.
        
        This is used to determine if movement between locations is coherent
        (within the same building/area) vs disjoint (across separate areas).
        
        Examples:
            share_container("kitchen", "hallway") -> True (both in "house")
            share_container("kitchen", "zoo") -> False (different containers)
            share_container("kitchen", "house") -> True (kitchen is IN house)
        
        Args:
            location1: First location
            location2: Second location
            
        Returns:
            True if locations share a container or one contains the other
        """
        if not location1 or not location2:
            return False
        
        loc1 = self.resolve_location(self._normalize_id(location1))
        loc2 = self.resolve_location(self._normalize_id(location2))
        
        if loc1 == loc2:
            return True
        
        # Check if one is the parent of the other
        parent1 = self.get_parent_location(loc1)
        parent2 = self.get_parent_location(loc2)
        
        if parent1 == loc2 or parent2 == loc1:
            return True
        
        # Check if they share the same parent
        if parent1 and parent2 and parent1 == parent2:
            return True
        
        return False
    
    def get_container_chain(self, location: str) -> List[str]:
        """
        Get the chain of containers from a location up to the root.
        
        Args:
            location: The location to query
            
        Returns:
            List from location to root container, e.g.:
            ["cupboard", "house"] for cupboard ⊂ house
        """
        if not location:
            return []
        
        chain = []
        current = self.resolve_location(self._normalize_id(location))
        
        # Limit to prevent infinite loops (max 10 levels)
        for _ in range(10):
            chain.append(current)
            parent = self._location_containment.get(current)
            if not parent:
                break
            current = parent
        
        return chain
    
    def get_location_containment_map(self) -> Dict[str, str]:
        """Get the full child -> parent containment mapping."""
        return dict(self._location_containment)

    def resolve(self, identifier: str) -> str:
        """
        Resolve an identifier to its canonical ID.
        
        If the identifier is unknown, returns it unchanged (assumed canonical).
        """
        if not identifier:
            return identifier
            
        normalized = self._normalize_id(identifier)
        
        if normalized in self._alias_to_canonical:
            self._resolutions_made += 1
            return self._alias_to_canonical[normalized]
        
        # Unknown identifier - return as-is (might be new character)
        return normalized
    
    def get_canonical_id(self, identifier: str) -> Optional[str]:
        """
        Get canonical ID for an identifier, or None if unknown.
        """
        if not identifier:
            return None
        normalized = self._normalize_id(identifier)
        return self._alias_to_canonical.get(normalized)
    
    def get_aliases(self, canonical_id: str) -> Set[str]:
        """
        Get all known aliases for a canonical ID.
        """
        normalized = self._normalize_id(canonical_id)
        return self._canonical_to_aliases.get(normalized, set())
    
    def is_known(self, identifier: str) -> bool:
        """Check if an identifier (alias or canonical) is known."""
        return self._normalize_id(identifier) in self._alias_to_canonical
    
    def normalize_extraction(
        self,
        extraction: Dict[str, Any],
        chapter_num: int,
    ) -> Tuple[Dict[str, Any], List[AliasConflict]]:
        """
        Normalize all character and location references in an extraction to canonical IDs.
        
        This is the main entry point for Phase 2 integration.
        
        1. Registers all characters and their aliases
        2. Registers all locations and their aliases
        3. Normalizes event agent/patient/location fields
        4. Normalizes relationship from/to fields
        5. Normalizes initial_rules subject/object fields
        
        Args:
            extraction: The LLM extraction dict with entities, events, initial_rules
            chapter_num: Current chapter number
            
        Returns:
            Tuple of (normalized_extraction, conflicts_detected)
        """
        import copy
        normalized = copy.deepcopy(extraction)
        all_conflicts = []
        
        entities = normalized.get("entities", {})
        
        # Step 1: Register all characters and their aliases
        for char in entities.get("characters", []):
            char_id = char.get("id", "")
            aliases = char.get("aliases", [])
            
            # Also treat the name as a potential alias
            name = char.get("name", "")
            if name:
                name_as_id = self._normalize_id(name)
                if name_as_id and name_as_id != char_id:
                    aliases = list(aliases) + [name_as_id]
            
            # Pass full_name for promotion checks
            conflicts = self.register_character(
                char_id, aliases, chapter_num, full_name=name or None
            )
            all_conflicts.extend(conflicts)
        
        # Step 1b: Register all locations and their aliases
        for loc in entities.get("locations", []):
            loc_id = loc.get("id", "")
            aliases = []
            
            # Treat the name as a potential alias
            name = loc.get("name", "")
            if name:
                name_as_id = self._normalize_id(name)
                if name_as_id and name_as_id != loc_id:
                    aliases.append(name_as_id)
            
            # Pass full_name for promotion checks
            conflicts = self.register_location(
                loc_id, aliases, chapter_num, full_name=name or None
            )
            all_conflicts.extend(conflicts)
        
        # Step 2: Normalize character IDs in character list
        for char in entities.get("characters", []):
            char["id"] = self.resolve(char.get("id", ""))
        
        # Step 2b: Normalize location IDs in location list
        for loc in entities.get("locations", []):
            loc["id"] = self.resolve_location(loc.get("id", ""))
        
        # Step 3: Normalize event agent/patient/location
        for event in normalized.get("events", []):
            if "agent" in event and event["agent"]:
                event["agent"] = self.resolve(event["agent"])
            if "patient" in event and event["patient"]:
                event["patient"] = self.resolve(event["patient"])
            if "location" in event and event["location"]:
                event["location"] = self.resolve_location(event["location"])
        
        # Step 4: Normalize relationships
        for rel in entities.get("relationships", []):
            if "from" in rel and rel["from"]:
                rel["from"] = self.resolve(rel["from"])
            if "to" in rel and rel["to"]:
                rel["to"] = self.resolve(rel["to"])
        
        # Step 5: Normalize initial_rules
        for rule in normalized.get("initial_rules", []):
            if "subject" in rule and rule["subject"]:
                rule["subject"] = self.resolve(rule["subject"])
            if "object" in rule and rule["object"]:
                rule["object"] = self.resolve(rule["object"])
        
        self._chapters_processed += 1
        
        return normalized, all_conflicts
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get resolver statistics."""
        return {
            "total_canonical_ids": len(self._canonical_to_aliases),
            "total_aliases": len(self._alias_to_canonical),
            "total_location_canonical_ids": len(self._location_canonical_to_aliases),
            "total_location_aliases": len(self._location_alias_to_canonical),
            "location_containment_relations": len(self._location_containment),
            "resolutions_made": self._resolutions_made,
            "location_resolutions_made": self._location_resolutions_made,
            "conflicts_detected": len(self._conflicts),
            "location_conflicts_detected": len(self._location_conflicts),
            "promotions_made": len(self._promotions),
            "location_promotions_made": len(self._location_promotions),
            "chapters_processed": self._chapters_processed,
        }
    
    def get_conflicts(self) -> List[AliasConflict]:
        """Get all detected character conflicts."""
        return list(self._conflicts)
    
    def get_location_conflicts(self) -> List[AliasConflict]:
        """Get all detected location conflicts."""
        return list(self._location_conflicts)
    
    def get_promotions(self) -> List[CanonicalPromotion]:
        """Get all character canonical ID promotions."""
        return list(self._promotions)
    
    def get_location_promotions(self) -> List[CanonicalPromotion]:
        """Get all location canonical ID promotions."""
        return list(self._location_promotions)
    
    def get_alias_map(self) -> Dict[str, str]:
        """Get the full character alias -> canonical mapping."""
        return dict(self._alias_to_canonical)
    
    def get_location_alias_map(self) -> Dict[str, str]:
        """Get the full location alias -> canonical mapping."""
        return dict(self._location_alias_to_canonical)
    
    def get_known_characters_context(self) -> List[Dict[str, Any]]:
        """
        Generate the known characters context for the extraction prompt.
        
        Returns list of dicts with canonical_id and known aliases.
        """
        result = []
        for canonical_id, aliases in self._canonical_to_aliases.items():
            result.append({
                "canonical_id": canonical_id,
                "aliases": list(aliases - {canonical_id}),  # Exclude self
            })
        return result
    
    def get_known_locations_context(self) -> List[Dict[str, Any]]:
        """
        Generate the known locations context for the extraction prompt.
        
        Returns list of dicts with canonical_id and known aliases.
        """
        result = []
        for canonical_id, aliases in self._location_canonical_to_aliases.items():
            result.append({
                "canonical_id": canonical_id,
                "aliases": list(aliases - {canonical_id}),  # Exclude self
            })
        return result
    
    def format_known_characters_list(self) -> str:
        """
        Format known characters for injection into the extraction prompt.
        
        Returns a compact, readable string with one ID per line.
        If no characters are known, returns a placeholder message.
        """
        canonical_ids = sorted(self._canonical_to_aliases.keys())
        if not canonical_ids:
            return "(No characters established yet)"
        return "\n".join(f"- {cid}" for cid in canonical_ids)
    
    def format_known_locations_list(self) -> str:
        """
        Format known locations for injection into the extraction prompt.
        
        Returns a compact, readable string with one ID per line.
        If no locations are known, returns a placeholder message.
        """
        canonical_ids = sorted(self._location_canonical_to_aliases.keys())
        if not canonical_ids:
            return "(No locations established yet)"
        return "\n".join(f"- {cid}" for cid in canonical_ids)
    
    def to_asp_facts(self) -> List[str]:
        """
        Generate ASP facts for alias resolution and location containment.
        
        Produces:
            - alias(AliasId, CanonicalId).
            - contains(ParentLocation, ChildLocation).
        """
        facts = []
        
        # Character alias facts
        for alias, canonical in self._alias_to_canonical.items():
            if alias != canonical:  # Don't generate self-aliases
                facts.append(f"alias({alias}, {canonical}).")
        
        # Location containment facts
        for child, parent in self._location_containment.items():
            facts.append(f"contains({parent}, {child}).")
        
        return facts
    
    @staticmethod
    def _normalize_id(identifier: str) -> str:
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
    
    def __repr__(self) -> str:
        return (
            f"AliasResolver(canonical={len(self._canonical_to_aliases)}, "
            f"aliases={len(self._alias_to_canonical)}, "
            f"conflicts={len(self._conflicts)})"
        )
