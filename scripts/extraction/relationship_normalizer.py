"""
Phase 4: Relationship Normalizer.

Normalizes relationships to ensure they:
1. Only reference entities in the EntityRegistry
2. Expand group references to individual members
3. Are normalized to character→character or character→item
4. Merge duplicates (same from, to, type)
5. Preserve conflicts (different types for same from/to pair)

Per LOGIC_DESIGN.md:
- relationship(Character1, Character2, Type, Time)
- Relationships are edges in the Logic Knowledge Graph
- Only valid entity references are allowed
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .entity_registry import EntityRegistry, ValidationWarning, _normalize_id
from ..state.logging import log


# Valid relationship types per LOGIC_DESIGN.md and extraction prompt
VALID_RELATIONSHIP_TYPES = frozenset({
    "hostile", "friendly", "family", "love", "fear",
    "ally", "enemy", "mentor", "student", "servant", "master",
    "sibling", "parent", "child", "spouse",
})


@dataclass
class RelationshipConflict:
    """Records conflicting relationship types for the same entity pair."""
    from_id: str
    to_id: str
    types: List[str]
    sources: List[Dict[str, Any]]  # Original relationship dicts
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "types": self.types,
            "sources": self.sources,
        }


@dataclass
class NormalizationResult:
    """Result of relationship normalization."""
    relationships: List[Dict[str, Any]]
    conflicts: List[RelationshipConflict]
    dropped_count: int
    merged_count: int
    expanded_count: int  # Number of relationships created from group expansion
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_count": len(self.relationships),
            "conflict_count": len(self.conflicts),
            "dropped_count": self.dropped_count,
            "merged_count": self.merged_count,
            "expanded_count": self.expanded_count,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


class RelationshipNormalizer:
    """
    Normalizes relationships using an EntityRegistry.
    
    Features:
    - Validates entity references against registry
    - Expands group references (e.g., "the_family" → individual members)
    - Normalizes relationship types
    - Merges duplicate relationships
    - Preserves conflicting relationships for logic resolution
    
    Usage:
        normalizer = RelationshipNormalizer(entity_registry)
        result = normalizer.normalize(relationships)
        # result.relationships contains the normalized list
        # result.conflicts contains pairs with multiple relationship types
    """
    
    def __init__(self, registry: EntityRegistry):
        """
        Initialize the normalizer with an EntityRegistry.
        
        Args:
            registry: EntityRegistry with registered characters, locations, items
        """
        self._registry = registry
        
        # Group definitions: group_id -> list of member canonical IDs
        # Groups are defined by entities with type "group" or explicit group markers
        self._groups: Dict[str, Set[str]] = {}
        
        # Build groups from registry (characters with type="group" or specific patterns)
        self._build_groups()
    
    def _build_groups(self) -> None:
        """
        Build group definitions from the registry.
        
        Groups are identified by:
        1. Characters with type="group" or kind="group"
        2. Family relationships (characters sharing family name)
        3. Explicit group patterns in character data
        """
        # Look for explicit groups in characters
        for canonical_id, char_data in self._registry._characters.items():
            char_type = char_data.get("type", "").lower()
            char_kind = char_data.get("kind", "").lower()
            
            if char_type == "group" or char_kind == "group":
                # This is a group entity - look for members
                members = char_data.get("members", [])
                if members:
                    self._groups[canonical_id] = set()
                    for member in members:
                        member_canonical = self._registry.resolve_character(member)
                        if member_canonical:
                            self._groups[canonical_id].add(member_canonical)
        
        # Build family groups based on shared family names
        # e.g., "the_dursleys" -> {uncle_vernon, aunt_petunia, dudley}
        family_groups: Dict[str, Set[str]] = {}
        for canonical_id, char_data in self._registry._characters.items():
            # Skip group entities
            if char_data.get("type", "").lower() == "group":
                continue
            
            # Look for family name pattern
            aliases = char_data.get("aliases", [])
            for alias in aliases:
                alias_norm = _normalize_id(alias)
                # Check for family name patterns: "the_X", "X_family"
                if alias_norm.startswith("the_"):
                    family_name = alias_norm
                    if family_name not in family_groups:
                        family_groups[family_name] = set()
                    family_groups[family_name].add(canonical_id)
                elif alias_norm.endswith("_family"):
                    family_name = alias_norm
                    if family_name not in family_groups:
                        family_groups[family_name] = set()
                    family_groups[family_name].add(canonical_id)
        
        # Add family groups with 2+ members
        for group_name, members in family_groups.items():
            if len(members) >= 2:
                self._groups[group_name] = members
    
    def add_group(self, group_id: str, member_ids: List[str]) -> None:
        """
        Manually add a group definition.
        
        Args:
            group_id: The group identifier (e.g., "the_dursleys")
            member_ids: List of character IDs that belong to the group
        """
        normalized_group = _normalize_id(group_id)
        members = set()
        for member_id in member_ids:
            member_canonical = self._registry.resolve_character(member_id)
            if member_canonical:
                members.add(member_canonical)
        
        if members:
            self._groups[normalized_group] = members
            log(f"    [RelationshipNormalizer] Added group '{normalized_group}' with {len(members)} members")
    
    def get_groups(self) -> Dict[str, Set[str]]:
        """Get all defined groups and their members."""
        return dict(self._groups)
    
    def _is_group(self, identifier: str) -> bool:
        """Check if an identifier refers to a group."""
        normalized = _normalize_id(identifier)
        return normalized in self._groups
    
    def _expand_group(self, identifier: str) -> Set[str]:
        """
        Expand a group identifier to its members.
        
        Returns a set of canonical character IDs.
        If not a group, returns a set with the single character ID (if valid).
        """
        normalized = _normalize_id(identifier)
        
        # Check if it's a known group
        if normalized in self._groups:
            return self._groups[normalized]
        
        # Check if it's a valid character
        canonical = self._registry.resolve_character(identifier)
        if canonical:
            return {canonical}
        
        return set()
    
    def _normalize_type(self, rel_type: str) -> str:
        """
        Normalize relationship type to canonical form.
        
        Maps synonyms to standard types.
        """
        type_lower = rel_type.lower().strip()
        
        # Type mappings
        mappings = {
            "hatred": "hostile",
            "hate": "hostile",
            "hates": "hostile",
            "enemies": "hostile",
            "enemy": "hostile",
            "antagonistic": "hostile",
            "friend": "friendly",
            "friends": "friendly",
            "friendship": "friendly",
            "allies": "ally",
            "alliance": "ally",
            "loves": "love",
            "romantic": "love",
            "romance": "love",
            "married": "spouse",
            "marriage": "spouse",
            "fears": "fear",
            "afraid": "fear",
            "scared": "fear",
            "parent_of": "parent",
            "child_of": "child",
            "brother": "sibling",
            "sister": "sibling",
            "siblings": "sibling",
        }
        
        return mappings.get(type_lower, type_lower)
    
    def _validate_and_resolve(
        self,
        rel: Dict[str, Any],
    ) -> List[Tuple[str, str, str, Dict[str, Any]]]:
        """
        Validate and resolve a single relationship.
        
        Handles group expansion - if either endpoint is a group,
        expands to individual relationships.
        
        Returns:
            List of (from_canonical, to_canonical, type, original_rel) tuples.
            Empty list if validation fails.
        """
        from_id = rel.get("from", "")
        to_id = rel.get("to", "")
        rel_type = rel.get("type", "")
        
        if not from_id or not to_id or not rel_type:
            return []
        
        normalized_type = self._normalize_type(rel_type)
        
        # Expand both endpoints (handles groups)
        from_entities = self._expand_group(from_id)
        to_entities = self._expand_group(to_id)
        
        results = []
        for from_canonical in from_entities:
            for to_canonical in to_entities:
                # Skip self-relationships
                if from_canonical == to_canonical:
                    continue
                results.append((from_canonical, to_canonical, normalized_type, rel))
        
        return results
    
    def normalize(
        self,
        relationships: List[Dict[str, Any]],
        drop_invalid: bool = True,
    ) -> NormalizationResult:
        """
        Normalize a list of relationships.
        
        Steps:
        1. Validate entity references against registry
        2. Expand group references to individuals
        3. Normalize relationship types
        4. Merge duplicates (same from, to, type)
        5. Identify conflicts (same from/to, different types)
        
        Args:
            relationships: List of relationship dicts from extraction
            drop_invalid: If True, drop invalid relationships
            
        Returns:
            NormalizationResult with normalized relationships and metadata
        """
        # Track all validated relationships: (from, to, type) -> source relationships
        validated: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
        
        # Track relationships by pair for conflict detection: (from, to) -> set of types
        pair_types: Dict[Tuple[str, str], Set[str]] = {}
        pair_sources: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        
        dropped_count = 0
        expanded_count = 0
        
        for rel in relationships:
            if not isinstance(rel, dict):
                log(f"    [RelationshipNormalizer] Skipping non-dict relationship entry: {rel!r}", "WARN")
                continue
            from_id = rel.get("from", "")
            to_id = rel.get("to", "")
            
            # Check for group or character in registry
            from_is_valid = self._is_group(from_id) or self._registry.resolve_character(from_id) is not None
            to_is_valid = self._is_group(to_id) or self._registry.resolve_character(to_id) is not None
            
            # Also allow character→item relationships
            if not to_is_valid:
                to_is_valid = self._registry.resolve_item(to_id) is not None
            
            if not from_is_valid:
                self._registry._warnings.append(ValidationWarning(
                    phase="relationships",
                    entity_type="character",
                    unknown_id=from_id,
                    context=f"relationship from '{from_id}' to '{to_id}'",
                    action="dropped" if drop_invalid else "kept",
                ))
                if drop_invalid:
                    dropped_count += 1
                    continue
            
            if not to_is_valid:
                self._registry._warnings.append(ValidationWarning(
                    phase="relationships",
                    entity_type="character/item",
                    unknown_id=to_id,
                    context=f"relationship from '{from_id}' to '{to_id}'",
                    action="dropped" if drop_invalid else "kept",
                ))
                if drop_invalid:
                    dropped_count += 1
                    continue
            
            # Validate and expand
            expanded = self._validate_and_resolve(rel)
            
            if not expanded:
                dropped_count += 1
                continue
            
            # Count expansions (more than 1 result means group was expanded)
            if len(expanded) > 1:
                expanded_count += len(expanded) - 1
            
            for from_canonical, to_canonical, rel_type, original in expanded:
                key = (from_canonical, to_canonical, rel_type)
                pair_key = (from_canonical, to_canonical)
                
                if key not in validated:
                    validated[key] = []
                validated[key].append(original)
                
                if pair_key not in pair_types:
                    pair_types[pair_key] = set()
                    pair_sources[pair_key] = []
                pair_types[pair_key].add(rel_type)
                if original not in pair_sources[pair_key]:
                    pair_sources[pair_key].append(original)
        
        # Build final relationship list
        normalized_rels: List[Dict[str, Any]] = []
        for (from_id, to_id, rel_type), sources in validated.items():
            normalized_rels.append({
                "from": from_id,
                "to": to_id,
                "type": rel_type,
            })
        
        # Identify conflicts (pairs with multiple types)
        conflicts: List[RelationshipConflict] = []
        for (from_id, to_id), types in pair_types.items():
            if len(types) > 1:
                conflicts.append(RelationshipConflict(
                    from_id=from_id,
                    to_id=to_id,
                    types=sorted(types),
                    sources=pair_sources[(from_id, to_id)],
                ))
        
        # Calculate merge count (original count - final count + expanded - dropped)
        original_count = len(relationships)
        final_count = len(normalized_rels)
        merged_count = max(0, original_count + expanded_count - dropped_count - final_count)
        
        result = NormalizationResult(
            relationships=normalized_rels,
            conflicts=conflicts,
            dropped_count=dropped_count,
            merged_count=merged_count,
            expanded_count=expanded_count,
        )
        
        log(f"    [RelationshipNormalizer] Normalized: {len(normalized_rels)} relationships, "
            f"{len(conflicts)} conflicts, {dropped_count} dropped, {merged_count} merged, {expanded_count} expanded")
        
        return result
    
    def normalize_initial_rules(
        self,
        initial_rules: List[Dict[str, Any]],
        drop_invalid: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Normalize initial rules using the same entity validation.
        
        Initial rules follow the format:
        {subject: str, predicate: str, object: str}
        
        Where object can be:
        - "true"/"false" for traits (e.g., "cruel": "true")
        - A character ID for relationships (e.g., "hates": "harry_potter")
        
        Args:
            initial_rules: List of initial rule dicts
            drop_invalid: If True, drop invalid rules
            
        Returns:
            List of validated and normalized initial rules
        """
        validated = []
        
        for rule in initial_rules:
            if not isinstance(rule, dict):
                log(f"    [RelationshipNormalizer] Skipping non-dict initial_rule entry: {rule!r}", "WARN")
                continue
            subject = rule.get("subject", "")
            obj = rule.get("object", "")
            predicate = rule.get("predicate", "")
            
            if not subject or not predicate:
                continue
            
            # Resolve subject (must be a character)
            subject_canonical = self._registry.resolve_character(subject)
            
            if not subject_canonical:
                # Try group expansion for subject
                if self._is_group(subject):
                    members = self._expand_group(subject)
                    for member in members:
                        expanded_rule = dict(rule)
                        expanded_rule["subject"] = member
                        # Recursively validate the expanded rule
                        expanded_validated = self.normalize_initial_rules([expanded_rule], drop_invalid)
                        validated.extend(expanded_validated)
                    continue
                
                self._registry._warnings.append(ValidationWarning(
                    phase="initial_rules",
                    entity_type="character",
                    unknown_id=subject,
                    context=f"rule '{subject} {predicate} {obj}'",
                    action="dropped" if drop_invalid else "kept",
                ))
                if drop_invalid:
                    continue
            
            # Check if object is a trait value or entity reference
            obj_lower = obj.lower() if obj else ""
            is_trait = obj_lower in ("true", "false", "yes", "no", "")
            
            if is_trait:
                # Trait rule - just validate subject
                validated_rule = dict(rule)
                if subject_canonical:
                    validated_rule["subject"] = subject_canonical
                validated.append(validated_rule)
            else:
                # Relationship rule - validate object as character
                obj_canonical = self._registry.resolve_character(obj)
                
                if not obj_canonical:
                    # Try group expansion for object
                    if self._is_group(obj):
                        members = self._expand_group(obj)
                        for member in members:
                            expanded_rule = dict(rule)
                            if subject_canonical:
                                expanded_rule["subject"] = subject_canonical
                            expanded_rule["object"] = member
                            validated.append(expanded_rule)
                        continue
                    
                    self._registry._warnings.append(ValidationWarning(
                        phase="initial_rules",
                        entity_type="character",
                        unknown_id=obj,
                        context=f"rule '{subject} {predicate} {obj}'",
                        action="dropped" if drop_invalid else "kept",
                    ))
                    if drop_invalid:
                        continue
                
                validated_rule = dict(rule)
                if subject_canonical:
                    validated_rule["subject"] = subject_canonical
                if obj_canonical:
                    validated_rule["object"] = obj_canonical
                validated.append(validated_rule)
        
        return validated
