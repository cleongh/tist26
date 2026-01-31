"""
Phase 3: Entity Registry for canonical entity management.

The EntityRegistry manages canonical IDs for characters, locations, and items.
It is built immediately after the first two extraction phases (characters+locations, items)
and is used to validate downstream phases (relationships, events).

Per LOGIC_DESIGN.md:
- "character(X)", "location(X)", "item(X)" are the entity node types
- Each entity has exactly one canonical ID
- Alias resolution maps alternate names to canonical IDs
- Downstream phases MUST NOT create new entities
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..state.logging import log


def _normalize_id(identifier: str) -> str:
    """
    Normalize an identifier to canonical snake_case form.
    
    - Lowercase
    - Replace spaces and hyphens with underscores
    - Remove special characters
    - Collapse multiple underscores
    """
    if not identifier:
        return ""
    s = str(identifier).lower().strip()
    s = re.sub(r'[\s\-]+', '_', s)
    s = re.sub(r'[^a-z0-9_]', '', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')
    return s


@dataclass
class ValidationWarning:
    """Records a validation warning for unknown entity references."""
    phase: str  # "relationships", "events", "initial_rules"
    entity_type: str  # "character", "location", "item"
    unknown_id: str  # The ID that was not found
    context: str  # Description of where the reference occurred
    action: str  # "dropped" or "kept"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "entity_type": self.entity_type,
            "unknown_id": self.unknown_id,
            "context": self.context,
            "action": self.action,
        }
    
    def __str__(self) -> str:
        return f"[{self.phase}] Unknown {self.entity_type} '{self.unknown_id}' in {self.context} ({self.action})"


class EntityRegistry:
    """
    Registry for canonical entities (characters, locations, items).
    
    Built after the first two extraction phases:
    1. Characters + Locations extraction
    2. Items extraction
    
    Used to validate downstream phases:
    - Relationships (from/to must be known characters)
    - Events (agent/patient must be known characters or items, location must be known)
    - Initial rules (subject/object must be known if they're entity references)
    
    Key guarantees:
    - One canonical ID per entity
    - Alias resolution for alternate names
    - Unknown entity references are flagged with warnings
    """
    
    def __init__(self):
        # Canonical ID -> entity data
        self._characters: Dict[str, Dict[str, Any]] = {}
        self._locations: Dict[str, Dict[str, Any]] = {}
        self._items: Dict[str, Dict[str, Any]] = {}
        
        # Alias mappings: alias -> canonical_id
        self._character_aliases: Dict[str, str] = {}
        self._location_aliases: Dict[str, str] = {}
        self._item_aliases: Dict[str, str] = {}
        
        # Validation warnings
        self._warnings: List[ValidationWarning] = []
        
        # Statistics
        self._resolutions_made: int = 0
    
    def reset(self) -> None:
        """Reset the registry to initial state."""
        self._characters.clear()
        self._locations.clear()
        self._items.clear()
        self._character_aliases.clear()
        self._location_aliases.clear()
        self._item_aliases.clear()
        self._warnings.clear()
        self._resolutions_made = 0
    
    # =========================================================================
    # Registration (called after extraction phases 1 and 2)
    # =========================================================================
    
    def register_characters(self, characters: List[Dict[str, Any]]) -> None:
        """
        Register characters from extraction phase 1.
        
        Each character's 'id' becomes the canonical ID.
        The 'name' and any 'aliases' are registered for resolution.
        """
        for char in characters:
            canonical_id = _normalize_id(char.get("id", ""))
            if not canonical_id:
                log(f"    [EntityRegistry] Skipping character with empty ID: {char}", "WARN")
                continue
            
            # Store the full entity data
            self._characters[canonical_id] = char
            
            # Register the canonical ID as an alias of itself
            self._character_aliases[canonical_id] = canonical_id
            
            # Register the display name as an alias
            name = char.get("name", "")
            if name:
                name_normalized = _normalize_id(name)
                if name_normalized and name_normalized not in self._character_aliases:
                    self._character_aliases[name_normalized] = canonical_id
            
            # Register any explicit aliases
            for alias in char.get("aliases", []):
                alias_normalized = _normalize_id(alias)
                if alias_normalized and alias_normalized not in self._character_aliases:
                    self._character_aliases[alias_normalized] = canonical_id
    
    def register_locations(self, locations: List[Dict[str, Any]]) -> None:
        """
        Register locations from extraction phase 1.
        
        Each location's 'id' becomes the canonical ID.
        The 'name' is registered for resolution.
        """
        for loc in locations:
            canonical_id = _normalize_id(loc.get("id", ""))
            if not canonical_id:
                log(f"    [EntityRegistry] Skipping location with empty ID: {loc}", "WARN")
                continue
            
            self._locations[canonical_id] = loc
            self._location_aliases[canonical_id] = canonical_id
            
            name = loc.get("name", "")
            if name:
                name_normalized = _normalize_id(name)
                if name_normalized and name_normalized not in self._location_aliases:
                    self._location_aliases[name_normalized] = canonical_id
    
    def register_items(self, items: List[Dict[str, Any]]) -> None:
        """
        Register items from extraction phase 2.
        
        Each item's 'id' becomes the canonical ID.
        The 'name' is registered for resolution.
        """
        for item in items:
            canonical_id = _normalize_id(item.get("id", ""))
            if not canonical_id:
                log(f"    [EntityRegistry] Skipping item with empty ID: {item}", "WARN")
                continue
            
            self._items[canonical_id] = item
            self._item_aliases[canonical_id] = canonical_id
            
            name = item.get("name", "")
            if name:
                name_normalized = _normalize_id(name)
                if name_normalized and name_normalized not in self._item_aliases:
                    self._item_aliases[name_normalized] = canonical_id
    
    # =========================================================================
    # Resolution (called to normalize IDs)
    # =========================================================================
    
    def resolve_character(self, identifier: str) -> Optional[str]:
        """
        Resolve a character identifier to its canonical ID.
        
        Returns None if the identifier is not a known character.
        """
        if not identifier:
            return None
        normalized = _normalize_id(identifier)
        canonical = self._character_aliases.get(normalized)
        if canonical:
            self._resolutions_made += 1
        return canonical
    
    def resolve_location(self, identifier: str) -> Optional[str]:
        """
        Resolve a location identifier to its canonical ID.
        
        Returns None if the identifier is not a known location.
        """
        if not identifier:
            return None
        normalized = _normalize_id(identifier)
        canonical = self._location_aliases.get(normalized)
        if canonical:
            self._resolutions_made += 1
        return canonical
    
    def resolve_item(self, identifier: str) -> Optional[str]:
        """
        Resolve an item identifier to its canonical ID.
        
        Returns None if the identifier is not a known item.
        """
        if not identifier:
            return None
        normalized = _normalize_id(identifier)
        canonical = self._item_aliases.get(normalized)
        if canonical:
            self._resolutions_made += 1
        return canonical
    
    def resolve_entity(self, identifier: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve an identifier that could be a character, item, or location.
        
        Tries characters first, then items, then locations.
        
        Returns:
            (canonical_id, entity_type) or (None, None) if not found
        """
        if not identifier:
            return None, None
        
        # Try character first (most common for agent/patient)
        canonical = self.resolve_character(identifier)
        if canonical:
            return canonical, "character"
        
        # Try item
        canonical = self.resolve_item(identifier)
        if canonical:
            return canonical, "item"
        
        # Try location
        canonical = self.resolve_location(identifier)
        if canonical:
            return canonical, "location"
        
        return None, None
    
    # =========================================================================
    # Validation (called to check downstream extraction results)
    # =========================================================================
    
    def validate_relationships(
        self,
        relationships: List[Dict[str, Any]],
        drop_invalid: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Validate relationships and optionally drop those with unknown entities.
        
        Relationships require both 'from' and 'to' to be known characters.
        
        Args:
            relationships: List of relationship dicts from extraction
            drop_invalid: If True, drop invalid relationships; if False, keep them
            
        Returns:
            List of validated relationships (with IDs normalized to canonical form)
        """
        validated = []
        
        for rel in relationships:
            from_id = rel.get("from", "")
            to_id = rel.get("to", "")
            
            from_canonical = self.resolve_character(from_id)
            to_canonical = self.resolve_character(to_id)
            
            has_error = False
            
            if not from_canonical:
                warning = ValidationWarning(
                    phase="relationships",
                    entity_type="character",
                    unknown_id=from_id,
                    context=f"relationship from '{from_id}' to '{to_id}'",
                    action="dropped" if drop_invalid else "kept",
                )
                self._warnings.append(warning)
                log(f"    [EntityRegistry] {warning}", "WARN")
                has_error = True
            
            if not to_canonical:
                warning = ValidationWarning(
                    phase="relationships",
                    entity_type="character",
                    unknown_id=to_id,
                    context=f"relationship from '{from_id}' to '{to_id}'",
                    action="dropped" if drop_invalid else "kept",
                )
                self._warnings.append(warning)
                log(f"    [EntityRegistry] {warning}", "WARN")
                has_error = True
            
            if has_error and drop_invalid:
                continue
            
            # Normalize IDs to canonical form
            validated_rel = dict(rel)
            if from_canonical:
                validated_rel["from"] = from_canonical
            if to_canonical:
                validated_rel["to"] = to_canonical
            validated.append(validated_rel)
        
        return validated
    
    def validate_initial_rules(
        self,
        initial_rules: List[Dict[str, Any]],
        drop_invalid: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Validate initial rules and optionally drop those with unknown entities.
        
        Initial rules have 'subject' (character) and 'object' (character or "true" for traits).
        
        Args:
            initial_rules: List of initial rule dicts from extraction
            drop_invalid: If True, drop invalid rules; if False, keep them
            
        Returns:
            List of validated rules (with IDs normalized to canonical form)
        """
        validated = []
        
        for rule in initial_rules:
            subject = rule.get("subject", "")
            obj = rule.get("object", "")
            predicate = rule.get("predicate", "")
            
            subject_canonical = self.resolve_character(subject)
            
            # Object can be "true" for traits, or a character ID for relationships
            obj_is_trait = obj.lower() in ("true", "false", "yes", "no")
            obj_canonical = None if obj_is_trait else self.resolve_character(obj)
            
            has_error = False
            
            if not subject_canonical:
                warning = ValidationWarning(
                    phase="initial_rules",
                    entity_type="character",
                    unknown_id=subject,
                    context=f"rule '{subject} {predicate} {obj}'",
                    action="dropped" if drop_invalid else "kept",
                )
                self._warnings.append(warning)
                log(f"    [EntityRegistry] {warning}", "WARN")
                has_error = True
            
            if not obj_is_trait and not obj_canonical:
                warning = ValidationWarning(
                    phase="initial_rules",
                    entity_type="character",
                    unknown_id=obj,
                    context=f"rule '{subject} {predicate} {obj}'",
                    action="dropped" if drop_invalid else "kept",
                )
                self._warnings.append(warning)
                log(f"    [EntityRegistry] {warning}", "WARN")
                has_error = True
            
            if has_error and drop_invalid:
                continue
            
            # Normalize IDs to canonical form
            validated_rule = dict(rule)
            if subject_canonical:
                validated_rule["subject"] = subject_canonical
            if obj_canonical:
                validated_rule["object"] = obj_canonical
            validated.append(validated_rule)
        
        return validated
    
    def validate_events(
        self,
        events: List[Dict[str, Any]],
        drop_invalid: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Validate events and optionally drop those with unknown entities.
        
        Events have:
        - agent: must be a known character
        - patient: can be a character, item, or null
        - location: must be a known location or null
        
        Args:
            events: List of event dicts from extraction
            drop_invalid: If True, drop invalid events; if False, keep them with warnings
            
        Returns:
            List of validated events (with IDs normalized to canonical form)
        """
        validated = []
        
        for event in events:
            event_id = event.get("id", "?")
            agent = event.get("agent", "")
            patient = event.get("patient")
            location = event.get("location")
            event_type = event.get("type", "?")
            
            has_error = False
            validated_event = dict(event)
            
            # Validate agent (required, must be character)
            agent_canonical = self.resolve_character(agent)
            if not agent_canonical:
                warning = ValidationWarning(
                    phase="events",
                    entity_type="character",
                    unknown_id=agent,
                    context=f"event {event_id} ({event_type}) agent",
                    action="dropped" if drop_invalid else "kept",
                )
                self._warnings.append(warning)
                log(f"    [EntityRegistry] {warning}", "WARN")
                has_error = True
            else:
                validated_event["agent"] = agent_canonical
            
            # Validate patient (optional, can be character or item)
            if patient and patient.lower() not in ("null", "none", ""):
                patient_canonical, patient_type = self.resolve_entity(patient)
                if not patient_canonical:
                    warning = ValidationWarning(
                        phase="events",
                        entity_type="character/item",
                        unknown_id=patient,
                        context=f"event {event_id} ({event_type}) patient",
                        action="dropped" if drop_invalid else "kept",
                    )
                    self._warnings.append(warning)
                    log(f"    [EntityRegistry] {warning}", "WARN")
                    has_error = True
                else:
                    validated_event["patient"] = patient_canonical
            
            # Validate location (optional)
            if location and location.lower() not in ("null", "none", ""):
                location_canonical = self.resolve_location(location)
                if not location_canonical:
                    warning = ValidationWarning(
                        phase="events",
                        entity_type="location",
                        unknown_id=location,
                        context=f"event {event_id} ({event_type}) location",
                        action="dropped" if drop_invalid else "kept",
                    )
                    self._warnings.append(warning)
                    log(f"    [EntityRegistry] {warning}", "WARN")
                    has_error = True
                else:
                    validated_event["location"] = location_canonical
            
            if has_error and drop_invalid:
                continue
            
            validated.append(validated_event)
        
        return validated
    
    # =========================================================================
    # Queries
    # =========================================================================
    
    def is_known_character(self, identifier: str) -> bool:
        """Check if an identifier is a known character."""
        return self.resolve_character(identifier) is not None
    
    def is_known_location(self, identifier: str) -> bool:
        """Check if an identifier is a known location."""
        return self.resolve_location(identifier) is not None
    
    def is_known_item(self, identifier: str) -> bool:
        """Check if an identifier is a known item."""
        return self.resolve_item(identifier) is not None
    
    def is_known_entity(self, identifier: str) -> bool:
        """Check if an identifier is any known entity type."""
        canonical, _ = self.resolve_entity(identifier)
        return canonical is not None
    
    def get_all_character_ids(self) -> Set[str]:
        """Get all canonical character IDs."""
        return set(self._characters.keys())
    
    def get_all_location_ids(self) -> Set[str]:
        """Get all canonical location IDs."""
        return set(self._locations.keys())
    
    def get_all_item_ids(self) -> Set[str]:
        """Get all canonical item IDs."""
        return set(self._items.keys())
    
    def get_warnings(self) -> List[ValidationWarning]:
        """Get all validation warnings."""
        return list(self._warnings)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "characters": len(self._characters),
            "locations": len(self._locations),
            "items": len(self._items),
            "character_aliases": len(self._character_aliases),
            "location_aliases": len(self._location_aliases),
            "item_aliases": len(self._item_aliases),
            "resolutions_made": self._resolutions_made,
            "warnings": len(self._warnings),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry state as dict."""
        return {
            "characters": list(self._characters.keys()),
            "locations": list(self._locations.keys()),
            "items": list(self._items.keys()),
            "character_aliases": dict(self._character_aliases),
            "location_aliases": dict(self._location_aliases),
            "item_aliases": dict(self._item_aliases),
            "warnings": [w.to_dict() for w in self._warnings],
            "statistics": self.get_statistics(),
        }
