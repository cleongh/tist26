"""
Character Alias Manager - Manages Character Aliases

Responsibilities:
    - Register character aliases to canonical IDs
    - Handle character-specific unifications
    - Provide character-specific query methods

Per LOGIC_DESIGN.md Section 3.2:
    - character(X) is a core entity type
    - Each character has exactly one canonical ID

Phase 2: This module ensures consistent character identity across chapters,
preventing issues like "uncle_vernon" vs "mr_dursley" referring to the same entity.
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


class CharacterAliasManager:
    """
    Manages character aliases.
    
    Works with AliasResolver for core alias functionality, but maintains
    its own character-specific mappings for:
    - Character-specific unifications and conflicts
    - Character promotion tracking
    
    Per LOGIC_DESIGN.md Section 3.2:
        character(X) is a core entity node type
    """
    
    def __init__(self, alias_resolver: AliasResolver):
        """
        Initialize the CharacterAliasManager.
        
        Args:
            alias_resolver: The core AliasResolver for alias operations
        """
        self._resolver = alias_resolver
        
        # Character-specific mappings (separate from location aliases)
        self._alias_to_canonical: Dict[str, str] = {}
        self._canonical_to_aliases: Dict[str, Set[str]] = {}
        self._canonical_to_full_name: Dict[str, str] = {}
        self._alias_first_seen: Dict[str, int] = {}
        self._promoted_entities: Set[str] = set()
        
        # Character-specific tracking
        self._promotions: List[CanonicalPromotion] = []
        self._unifications: List[AliasUnification] = []
        self._conflicts: List[AliasConflict] = []
        
        # Statistics
        self._resolutions_made: int = 0
    
    def reset(self) -> None:
        """Reset all character-specific data."""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._canonical_to_full_name.clear()
        self._alias_first_seen.clear()
        self._promoted_entities.clear()
        self._promotions.clear()
        self._unifications.clear()
        self._conflicts.clear()
        self._resolutions_made = 0
    
    # =========================================================================
    # REGISTRATION
    # =========================================================================
    
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
            full_name: The full display name of the character
            
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
                        f"Alias conflict RESOLVED: '{alias}' mapped to both "
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
    
    def resolve(self, identifier: str) -> str:
        """
        Resolve a character identifier to its canonical ID.
        
        If the identifier is unknown, returns it unchanged (assumed canonical).
        """
        if not identifier:
            return identifier
            
        normalized = self._resolver.normalize_id(identifier)
        
        if normalized in self._alias_to_canonical:
            self._resolutions_made += 1
            return self._alias_to_canonical[normalized]
        
        # Unknown identifier - return as-is (might be new character)
        return normalized
    
    def get_canonical_id(self, identifier: str) -> Optional[str]:
        """Get canonical ID for a character identifier, or None if unknown."""
        if not identifier:
            return None
        normalized = self._resolver.normalize_id(identifier)
        return self._alias_to_canonical.get(normalized)
    
    def get_aliases(self, canonical_id: str) -> Set[str]:
        """Get all known aliases for a character canonical ID."""
        normalized = self._resolver.normalize_id(canonical_id)
        return self._canonical_to_aliases.get(normalized, set())
    
    def is_known(self, identifier: str) -> bool:
        """Check if a character identifier (alias or canonical) is known."""
        return self._resolver.normalize_id(identifier) in self._alias_to_canonical
    
    def get_all_canonical_ids(self) -> Set[str]:
        """Get all registered character canonical IDs."""
        return set(self._canonical_to_aliases.keys())
    
    # =========================================================================
    # CONFLICTS AND UNIFICATIONS
    # =========================================================================
    
    def get_conflicts(self) -> List[AliasConflict]:
        """Get all detected character conflicts (includes resolution info)."""
        return list(self._conflicts)
    
    def get_unifications(self) -> List[AliasUnification]:
        """Get all character canonical ID unifications."""
        return list(self._unifications)
    
    def get_promotions(self) -> List[CanonicalPromotion]:
        """Get all character canonical ID promotions."""
        return list(self._promotions)
    
    def get_alias_map(self) -> Dict[str, str]:
        """Get the full character alias -> canonical mapping."""
        return dict(self._alias_to_canonical)
    
    # =========================================================================
    # CONTEXT FOR PROMPTS
    # =========================================================================
    
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
        """Promote a character's canonical ID to a better one."""
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
        
        # Mark this entity as promoted
        self._promoted_entities.add(self._resolver.normalize_id(full_name))
        
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
    
    def _unify_canonicals(
        self,
        existing_canonical: str,
        new_canonical: str,
        shared_alias: str,
        chapter: int,
    ) -> str:
        """
        Unify two canonical character IDs when a conflict is detected.
        
        Per LOGIC_DESIGN.md Section 2 (Core Design Principles):
            - Deterministic and explainable: every conclusion must trace back to rules
            - Logic-first architecture: ASP is the source of truth
        
        Uses FIRST-SEEN WINS strategy for determinism.
        
        Returns:
            The surviving canonical ID (always existing_canonical)
        """
        surviving = existing_canonical
        absorbed = new_canonical
        
        logger.info(
            f"UNIFYING CANONICALS: '{absorbed}' -> '{surviving}' "
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
            entity_type="character",
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
        
        # Remove absorbed canonical entry from canonical_to_aliases
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
        
        return surviving
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get character manager statistics."""
        return {
            "total_canonical_ids": len(self._canonical_to_aliases),
            "total_aliases": len(self._alias_to_canonical),
            "resolutions_made": self._resolutions_made,
            "conflicts_detected": len(self._conflicts),
            "conflicts_unified": len(self._unifications),
            "promotions_made": len(self._promotions),
        }
    
    def __repr__(self) -> str:
        return (
            f"CharacterAliasManager(canonical={len(self._canonical_to_aliases)}, "
            f"aliases={len(self._alias_to_canonical)}, "
            f"conflicts={len(self._conflicts)})"
        )


# =============================================================================
# LEGACY CHARACTER ALIASES
# =============================================================================

# Minimal legacy aliases for backward compatibility
# These map common variations to canonical forms
# New code should use AliasResolver for dynamic alias management
_LEGACY_CHARACTER_ALIASES: Dict[str, str] = {
    # Harry Potter
    "harry_potter": "harry",
    "potter": "harry",
    "harry": "harry",
    # Hermione
    "hermione_granger": "hermione",
    "granger": "hermione",
    "hermione": "hermione",
    # Ron
    "ron_weasley": "ron",
    "ronald_weasley": "ron",
    "ron": "ron",
    # Dumbledore
    "albus_dumbledore": "dumbledore",
    "dumbledore": "dumbledore",
    # Hagrid
    "rubeus_hagrid": "hagrid",
    "hagrid": "hagrid",
}


# =============================================================================
# MODULE-LEVEL FUNCTIONS
# =============================================================================

def normalize_character_id(
    char_id: str,
    alias_resolver: Optional['AliasResolver'] = None,
) -> str:
    """
    Normalize a character ID to its canonical form.
    
    If an AliasResolver is provided, uses dynamic alias resolution.
    Otherwise, falls back to legacy hardcoded aliases.
    
    Args:
        char_id: The character ID to normalize
        alias_resolver: Optional AliasResolver for dynamic resolution
        
    Returns:
        The normalized canonical character ID
    """
    if not char_id:
        return char_id
    
    # Normalize to lowercase
    normalized = char_id.lower()
    
    # If resolver provided, use dynamic resolution
    if alias_resolver is not None:
        resolved = alias_resolver.resolve(normalized)
        if resolved:
            return resolved
    
    # Fall back to legacy aliases
    if normalized in _LEGACY_CHARACTER_ALIASES:
        return _LEGACY_CHARACTER_ALIASES[normalized]
    
    return normalized


