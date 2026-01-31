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
import re
import logging

logger = logging.getLogger(__name__)


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
    Resolves character aliases to canonical IDs.
    
    Maintains a bidirectional mapping:
    - alias_to_canonical: alias -> canonical_id
    - canonical_to_aliases: canonical_id -> set of aliases
    
    All character references (events, relationships, rules) are normalized
    to canonical IDs before being sent to the ASP solver.
    """
    
    def __init__(self):
        # alias -> canonical_id
        self._alias_to_canonical: Dict[str, str] = {}
        
        # canonical_id -> set of known aliases
        self._canonical_to_aliases: Dict[str, Set[str]] = {}
        
        # Track when aliases were first seen
        self._alias_first_seen: Dict[str, int] = {}
        
        # Conflicts detected
        self._conflicts: List[AliasConflict] = []
        
        # Statistics
        self._resolutions_made: int = 0
        self._chapters_processed: int = 0
    
    def reset(self) -> None:
        """Reset the resolver to initial state."""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._alias_first_seen.clear()
        self._conflicts.clear()
        self._resolutions_made = 0
        self._chapters_processed = 0
    
    def register_character(
        self,
        canonical_id: str,
        aliases: List[str],
        chapter_num: int,
    ) -> List[AliasConflict]:
        """
        Register a character's canonical ID and aliases.
        
        Args:
            canonical_id: The canonical snake_case character ID
            aliases: List of alternate names/IDs for this character
            chapter_num: Chapter number where this was extracted
            
        Returns:
            List of any conflicts detected during registration
        """
        new_conflicts = []
        canonical_id = self._normalize_id(canonical_id)
        
        # The canonical ID is always an alias of itself
        all_aliases = [canonical_id] + [self._normalize_id(a) for a in aliases if a]
        all_aliases = [a for a in all_aliases if a]  # Filter empty
        
        # Initialize canonical entry if new
        if canonical_id not in self._canonical_to_aliases:
            self._canonical_to_aliases[canonical_id] = set()
        
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
        Normalize all character references in an extraction to canonical IDs.
        
        This is the main entry point for Phase 2 integration.
        
        1. Registers all characters and their aliases
        2. Normalizes event agent/patient fields
        3. Normalizes relationship from/to fields
        4. Normalizes initial_rules subject/object fields
        
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
            
            conflicts = self.register_character(char_id, aliases, chapter_num)
            all_conflicts.extend(conflicts)
        
        # Step 2: Normalize character IDs in character list
        for char in entities.get("characters", []):
            char["id"] = self.resolve(char.get("id", ""))
        
        # Step 3: Normalize event agent/patient
        for event in normalized.get("events", []):
            if "agent" in event and event["agent"]:
                event["agent"] = self.resolve(event["agent"])
            if "patient" in event and event["patient"]:
                event["patient"] = self.resolve(event["patient"])
        
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
            "resolutions_made": self._resolutions_made,
            "conflicts_detected": len(self._conflicts),
            "chapters_processed": self._chapters_processed,
        }
    
    def get_conflicts(self) -> List[AliasConflict]:
        """Get all detected conflicts."""
        return list(self._conflicts)
    
    def get_alias_map(self) -> Dict[str, str]:
        """Get the full alias -> canonical mapping."""
        return dict(self._alias_to_canonical)
    
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
    
    def to_asp_facts(self) -> List[str]:
        """
        Generate ASP facts for alias resolution.
        
        Produces: alias(AliasId, CanonicalId).
        """
        facts = []
        for alias, canonical in self._alias_to_canonical.items():
            if alias != canonical:  # Don't generate self-aliases
                facts.append(f"alias({alias}, {canonical}).")
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
