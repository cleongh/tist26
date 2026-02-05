"""
Location Alias Manager - Manages Location Aliases and Containment

Responsibilities:
    - Register location aliases to canonical IDs
    - Handle location containment relationships (parent/child)
    - Unify conflicting location canonical IDs
    - Provide location-specific query methods

Per LOGIC_DESIGN.md Section 3.2:
    - location(X) is a core entity type
    - Each location has exactly one canonical ID
"""

from typing import Dict, Set, List, Optional, Any
import logging

from ..domain import (
    PromotionReason,
    UnificationReason,
    AliasUnification,
    CanonicalPromotion,
    AliasConflict,
)
from ..resolvers import AliasResolver

logger = logging.getLogger(__name__)


class LocationAliasManager:
    """
    Manages location aliases and containment relationships.
    
    Works with AliasResolver for core alias functionality, but maintains
    its own location-specific mappings for:
    - Location containment (parent/child relationships)
    - Location-specific unifications and conflicts
    
    Per LOGIC_DESIGN.md Section 3.2:
        location(X) is a core entity node type
    """
    
    def __init__(self, alias_resolver: AliasResolver):
        """
        Initialize the LocationAliasManager.
        
        Args:
            alias_resolver: The core AliasResolver for alias operations
        """
        self._resolver = alias_resolver
        
        # Location-specific mappings (separate from character aliases)
        self._alias_to_canonical: Dict[str, str] = {}
        self._canonical_to_aliases: Dict[str, Set[str]] = {}
        self._canonical_to_full_name: Dict[str, str] = {}
        self._alias_first_seen: Dict[str, int] = {}
        self._promoted_entities: Set[str] = set()
        
        # Location containment: child -> parent (1-level containment)
        # e.g., {"kitchen": "house", "hallway": "house", "cupboard": "house"}
        self._location_containment: Dict[str, str] = {}
        
        # Reverse mapping: parent -> set of children
        # e.g., {"house": {"kitchen", "hallway", "cupboard"}}
        self._location_children: Dict[str, Set[str]] = {}
        
        # Location-specific tracking
        self._promotions: List[CanonicalPromotion] = []
        self._unifications: List[AliasUnification] = []
        self._conflicts: List[AliasConflict] = []
        
        # Statistics
        self._resolutions_made: int = 0
    
    def reset(self) -> None:
        """Reset all location-specific data."""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._canonical_to_full_name.clear()
        self._alias_first_seen.clear()
        self._promoted_entities.clear()
        self._location_containment.clear()
        self._location_children.clear()
        self._promotions.clear()
        self._unifications.clear()
        self._conflicts.clear()
        self._resolutions_made = 0
    
    # =========================================================================
    # REGISTRATION
    # =========================================================================
    
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
        
        Args:
            canonical_id: The canonical snake_case location ID
            aliases: List of alternate names/IDs for this location
            chapter_num: Chapter number where this was extracted
            full_name: The full display name of the location
            parent_location: Optional parent/container location ID
            
        Returns:
            List of any conflicts detected during registration
        """
        new_conflicts = []
        canonical_id = self._resolver.normalize_id(canonical_id)
        
        # The canonical ID is always an alias of itself
        all_aliases = [canonical_id] + [self._resolver.normalize_id(a) for a in aliases if a]
        all_aliases = [a for a in all_aliases if a]  # Filter empty
        
        # Derive full_name if not provided
        if not full_name:
            full_name = canonical_id.replace('_', ' ').title()
        
        normalized_full_name = self._resolver.normalize_id(full_name)
        
        # Check for promotion opportunity BEFORE registering
        if normalized_full_name not in self._promoted_entities:
            for existing_canonical, existing_full in self._canonical_to_full_name.items():
                is_inferior, reason = self._resolver.is_inferior_canonical(
                    existing_canonical, canonical_id, existing_full, full_name
                )
                
                if is_inferior and reason:
                    self._promote_canonical(
                        old_canonical=existing_canonical,
                        new_canonical=canonical_id,
                        full_name=full_name,
                        chapter=chapter_num,
                        reason=reason,
                    )
                    break
        
        # Initialize canonical entry if new
        if canonical_id not in self._canonical_to_aliases:
            self._canonical_to_aliases[canonical_id] = set()
        
        # Store full name for future promotion checks
        if canonical_id not in self._canonical_to_full_name:
            self._canonical_to_full_name[canonical_id] = full_name
        
        # Register containment if parent provided
        if parent_location:
            self.set_location_containment(canonical_id, parent_location)
        
        for alias in all_aliases:
            if not alias:
                continue
            
            # Check for conflict: alias already maps to different canonical
            if alias in self._alias_to_canonical:
                existing_canonical = self._alias_to_canonical[alias]
                if existing_canonical != canonical_id:
                    # UNIFY: merge the two canonical IDs
                    surviving = self._unify_canonicals(
                        existing_canonical=existing_canonical,
                        new_canonical=canonical_id,
                        shared_alias=alias,
                        chapter=chapter_num,
                    )
                    
                    # Record conflict with resolution info
                    conflict = AliasConflict(
                        alias=alias,
                        canonical_ids={existing_canonical, canonical_id},
                        first_seen_chapter=self._alias_first_seen.get(alias, chapter_num),
                        conflict_chapter=chapter_num,
                        chosen_canonical=surviving,
                        absorbed_canonical=canonical_id if surviving == existing_canonical else existing_canonical,
                        resolution_reason=UnificationReason.FIRST_SEEN_WINS.value,
                    )
                    new_conflicts.append(conflict)
                    self._conflicts.append(conflict)
                    
                    logger.info(
                        f"Location alias conflict RESOLVED: '{alias}' mapped to both "
                        f"'{existing_canonical}' and '{canonical_id}' -> unified to '{surviving}'"
                    )
                    
                    # Update canonical_id to the surviving one for remaining aliases
                    canonical_id = surviving
                    continue
            
            # Register the alias
            self._alias_to_canonical[alias] = canonical_id
            self._canonical_to_aliases[canonical_id].add(alias)
            
            if alias not in self._alias_first_seen:
                self._alias_first_seen[alias] = chapter_num
        
        return new_conflicts
    
    # =========================================================================
    # RESOLUTION
    # =========================================================================
    
    def resolve_location(self, identifier: str) -> str:
        """
        Resolve a location identifier to its canonical ID.
        
        If the identifier is unknown, returns it unchanged (assumed canonical).
        """
        if not identifier:
            return identifier
            
        normalized = self._resolver.normalize_id(identifier)
        
        if normalized in self._alias_to_canonical:
            self._resolutions_made += 1
            return self._alias_to_canonical[normalized]
        
        # Unknown identifier - return as-is (might be new location)
        return normalized
    
    def get_location_canonical_id(self, identifier: str) -> Optional[str]:
        """Get canonical ID for a location identifier, or None if unknown."""
        if not identifier:
            return None
        normalized = self._resolver.normalize_id(identifier)
        return self._alias_to_canonical.get(normalized)
    
    def get_location_aliases(self, canonical_id: str) -> Set[str]:
        """Get all known aliases for a location canonical ID."""
        normalized = self._resolver.normalize_id(canonical_id)
        return self._canonical_to_aliases.get(normalized, set())
    
    def is_location_known(self, identifier: str) -> bool:
        """Check if a location identifier (alias or canonical) is known."""
        return self._resolver.normalize_id(identifier) in self._alias_to_canonical
    
    def get_all_location_canonical_ids(self) -> Set[str]:
        """Get all registered location canonical IDs."""
        return set(self._canonical_to_aliases.keys())
    
    # =========================================================================
    # CONTAINMENT
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
        
        Args:
            child_location: The contained/sub-location
            parent_location: The container/parent location
        """
        child = self._resolver.normalize_id(child_location)
        parent = self._resolver.normalize_id(parent_location)
        
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
        
        Returns:
            The parent location ID, or None if location has no parent
        """
        if not location:
            return None
        normalized = self.resolve_location(self._resolver.normalize_id(location))
        return self._location_containment.get(normalized)
    
    def get_child_locations(self, location: str) -> Set[str]:
        """
        Get all direct child locations of a given location.
        
        Returns:
            Set of child location IDs (empty if no children)
        """
        if not location:
            return set()
        normalized = self.resolve_location(self._resolver.normalize_id(location))
        return self._location_children.get(normalized, set()).copy()
    
    def share_container(self, location1: str, location2: str) -> bool:
        """
        Check if two locations share the same immediate container.
        
        This is used to determine if movement between locations is coherent
        (within the same building/area) vs disjoint (across separate areas).
        
        Returns:
            True if locations share a container or one contains the other
        """
        if not location1 or not location2:
            return False
        
        loc1 = self.resolve_location(self._resolver.normalize_id(location1))
        loc2 = self.resolve_location(self._resolver.normalize_id(location2))
        
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
        
        Returns:
            List from location to root container, e.g.:
            ["cupboard", "house"] for cupboard ⊂ house
        """
        if not location:
            return []
        
        chain = []
        current = self.resolve_location(self._resolver.normalize_id(location))
        
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
    
    # =========================================================================
    # CONFLICTS AND UNIFICATIONS
    # =========================================================================
    
    def get_location_conflicts(self) -> List[AliasConflict]:
        """Get all detected location conflicts (includes resolution info)."""
        return list(self._conflicts)
    
    def get_location_unifications(self) -> List[AliasUnification]:
        """Get all location canonical ID unifications."""
        return list(self._unifications)
    
    def get_location_promotions(self) -> List[CanonicalPromotion]:
        """Get all location canonical ID promotions."""
        return list(self._promotions)
    
    def get_location_alias_map(self) -> Dict[str, str]:
        """Get the full location alias -> canonical mapping."""
        return dict(self._alias_to_canonical)
    
    # =========================================================================
    # CONTEXT FOR PROMPTS
    # =========================================================================
    
    def get_known_locations_context(self) -> List[Dict[str, Any]]:
        """
        Generate the known locations context for the extraction prompt.
        
        Returns list of dicts with canonical_id and known aliases.
        """
        result = []
        for canonical_id, aliases in self._canonical_to_aliases.items():
            result.append({
                "canonical_id": canonical_id,
                "aliases": list(aliases - {canonical_id}),  # Exclude self
            })
        return result
    
    def format_known_locations_list(self) -> str:
        """
        Format known locations for injection into the extraction prompt.
        
        Returns a compact, readable string with one ID per line.
        If no locations are known, returns a placeholder message.
        """
        canonical_ids = sorted(self._canonical_to_aliases.keys())
        if not canonical_ids:
            return "(No locations established yet)"
        return "\n".join(f"- {cid}" for cid in canonical_ids)
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def _promote_canonical(
        self,
        old_canonical: str,
        new_canonical: str,
        full_name: str,
        chapter: int,
        reason: PromotionReason,
    ) -> None:
        """Promote a location's canonical ID to a better one."""
        # Record promotion for audit trail
        promotion = CanonicalPromotion(
            old_canonical=old_canonical,
            new_canonical=new_canonical,
            full_name=full_name,
            chapter=chapter,
            reason=reason,
            entity_type="location",
        )
        self._promotions.append(promotion)
        
        # Mark this entity as promoted
        self._promoted_entities.add(self._resolver.normalize_id(full_name))
        
        logger.warning(
            f"LOCATION CANONICAL PROMOTION: '{old_canonical}' -> '{new_canonical}' "
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
    
    def _unify_canonicals(
        self,
        existing_canonical: str,
        new_canonical: str,
        shared_alias: str,
        chapter: int,
    ) -> str:
        """
        Unify two canonical location IDs when a conflict is detected.
        
        Uses FIRST-SEEN WINS strategy for determinism.
        
        Returns:
            The surviving canonical ID (always existing_canonical)
        """
        surviving = existing_canonical
        absorbed = new_canonical
        
        logger.info(
            f"UNIFYING LOCATION CANONICALS: '{absorbed}' -> '{surviving}' "
            f"(shared_alias='{shared_alias}', chapter={chapter})"
        )
        
        # Gather all aliases that pointed to absorbed canonical
        absorbed_aliases = self._canonical_to_aliases.get(absorbed, set()).copy()
        
        # Record unification for audit trail
        unification = AliasUnification(
            absorbed_canonical=absorbed,
            surviving_canonical=surviving,
            shared_alias=shared_alias,
            absorbed_aliases=absorbed_aliases,
            chapter=chapter,
            reason=UnificationReason.FIRST_SEEN_WINS,
            entity_type="location",
        )
        self._unifications.append(unification)
        
        # Initialize surviving canonical entry if not exists
        if surviving not in self._canonical_to_aliases:
            self._canonical_to_aliases[surviving] = set()
        
        # Migrate all aliases from absorbed to surviving
        for alias in absorbed_aliases:
            self._alias_to_canonical[alias] = surviving
            self._canonical_to_aliases[surviving].add(alias)
        
        # Add absorbed canonical as an alias of surviving
        self._alias_to_canonical[absorbed] = surviving
        self._canonical_to_aliases[surviving].add(absorbed)
        
        # Remove absorbed canonical entry
        if absorbed in self._canonical_to_aliases:
            del self._canonical_to_aliases[absorbed]
        
        # Merge full name if absorbed had one and surviving doesn't
        if absorbed in self._canonical_to_full_name:
            if surviving not in self._canonical_to_full_name:
                self._canonical_to_full_name[surviving] = self._canonical_to_full_name[absorbed]
            del self._canonical_to_full_name[absorbed]
        
        # Merge first-seen info: keep the earliest chapter
        if absorbed in self._alias_first_seen:
            absorbed_first = self._alias_first_seen.get(absorbed, chapter)
            surviving_first = self._alias_first_seen.get(surviving, chapter)
            self._alias_first_seen[surviving] = min(absorbed_first, surviving_first)
        
        # Handle containment: if absorbed was a child, update to surviving
        if absorbed in self._location_containment:
            parent = self._location_containment[absorbed]
            del self._location_containment[absorbed]
            if surviving not in self._location_containment:
                self._location_containment[surviving] = parent
            # Update parent's children set
            if parent in self._location_children:
                self._location_children[parent].discard(absorbed)
                self._location_children[parent].add(surviving)
        
        # Handle containment: if absorbed was a parent, migrate children
        if absorbed in self._location_children:
            children = self._location_children[absorbed]
            del self._location_children[absorbed]
            if surviving not in self._location_children:
                self._location_children[surviving] = set()
            self._location_children[surviving].update(children)
            # Update children to point to new parent
            for child in children:
                if child in self._location_containment:
                    self._location_containment[child] = surviving
        
        return surviving
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get location manager statistics."""
        return {
            "total_canonical_ids": len(self._canonical_to_aliases),
            "total_aliases": len(self._alias_to_canonical),
            "containment_relations": len(self._location_containment),
            "resolutions_made": self._resolutions_made,
            "conflicts_detected": len(self._conflicts),
            "conflicts_unified": len(self._unifications),
            "promotions_made": len(self._promotions),
        }
    
    def __repr__(self) -> str:
        return (
            f"LocationAliasManager(canonical={len(self._canonical_to_aliases)}, "
            f"aliases={len(self._alias_to_canonical)}, "
            f"containment={len(self._location_containment)})"
        )
