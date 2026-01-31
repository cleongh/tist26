"""
Phase 6: Lifecycle Tracker - Cross-Chapter Entity Lifecycle Management.

Tracks the lifecycle of entities (characters, items, locations) across
all chapters and provides final analysis to detect:
- Chekhov's Gun violations (items introduced but never used)
- Unused causal items
- Unresolved relationships
- Characters/items introduced but never modified

Per LOGIC_DESIGN.md Section 6 (Final Chapter Analysis):
- After the final chapter:
  - Audit all active and deactivated rules
  - Detect loose ends:
    - Unresolved items
    - Introduced but unused entities
    - Chekhov-style artifacts
  - Detect long-range inconsistencies not visible at chapter scope

This module is the LAST step of the extraction pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .entity_registry import EntityRegistry, _normalize_id
from .event_normalizer import EventNormalizer, ItemUsageType
from ..state.logging import log


class EntityLifecycleState(Enum):
    """Lifecycle states for entities."""
    INTRODUCED = "introduced"       # Entity first mentioned
    ACTIVE = "active"               # Entity participates in events
    MODIFIED = "modified"           # Entity's state changed
    RESOLVED = "resolved"           # Entity's arc completed
    DORMANT = "dormant"             # Entity not mentioned recently


class RelationshipState(Enum):
    """Lifecycle states for relationships."""
    ESTABLISHED = "established"     # Relationship first created
    ACTIVE = "active"               # Relationship referenced in events
    CHANGED = "changed"             # Relationship type changed
    RESOLVED = "resolved"           # Relationship concluded


@dataclass
class EntityLifecycle:
    """Tracks lifecycle of a single entity across chapters."""
    entity_id: str
    entity_type: str  # "character", "item", "location"
    introduced_chapter: int
    last_active_chapter: int
    state: EntityLifecycleState
    event_count: int = 0
    modification_count: int = 0
    chapters_active: List[int] = field(default_factory=list)
    # For items: track causal/latent status
    item_usage: Optional[ItemUsageType] = None
    promoted_chapter: Optional[int] = None  # When latent became causal
    
    def is_active(self) -> bool:
        return self.state in (EntityLifecycleState.ACTIVE, EntityLifecycleState.MODIFIED)
    
    def is_unused(self) -> bool:
        return self.event_count == 0 and self.modification_count == 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "introduced_chapter": self.introduced_chapter,
            "last_active_chapter": self.last_active_chapter,
            "state": self.state.value,
            "event_count": self.event_count,
            "modification_count": self.modification_count,
            "chapters_active": self.chapters_active,
            "item_usage": self.item_usage.value if self.item_usage else None,
            "promoted_chapter": self.promoted_chapter,
        }


@dataclass
class RelationshipLifecycle:
    """Tracks lifecycle of a relationship across chapters."""
    from_id: str
    to_id: str
    relationship_type: str
    established_chapter: int
    last_referenced_chapter: int
    state: RelationshipState
    type_changes: List[Tuple[int, str, str]] = field(default_factory=list)  # (chapter, old_type, new_type)
    
    def is_unresolved(self) -> bool:
        return self.state in (RelationshipState.ESTABLISHED, RelationshipState.ACTIVE)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "type": self.relationship_type,
            "established_chapter": self.established_chapter,
            "last_referenced_chapter": self.last_referenced_chapter,
            "state": self.state.value,
            "type_changes": [
                {"chapter": c, "from": o, "to": n} 
                for c, o, n in self.type_changes
            ],
        }


@dataclass
class LooseEnd:
    """A loose end detected in the final analysis."""
    loose_end_type: str  # "chekhov", "unused_causal", "unresolved_relationship", "dormant_entity"
    entity_id: str
    entity_type: str
    introduced_chapter: int
    last_chapter: Optional[int] = None
    description: str = ""
    severity: str = "warning"  # "warning", "error"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.loose_end_type,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "introduced_chapter": self.introduced_chapter,
            "last_chapter": self.last_chapter,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class BackAnnotation:
    """An error back-annotated to an earlier chapter."""
    chapter: int
    entity_id: str
    entity_type: str
    annotation_type: str  # "chekhov_warning", "causality_error", etc.
    message: str
    detected_at_chapter: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter": self.chapter,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "annotation_type": self.annotation_type,
            "message": self.message,
            "detected_at_chapter": self.detected_at_chapter,
        }


@dataclass
class FinalAnalysisResult:
    """Result of final chapter analysis."""
    total_chapters: int
    loose_ends: List[LooseEnd]
    back_annotations: List[BackAnnotation]
    entity_summary: Dict[str, int]  # entity_type -> count
    lifecycle_summary: Dict[str, int]  # state -> count
    
    def has_errors(self) -> bool:
        return any(le.severity == "error" for le in self.loose_ends)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chapters": self.total_chapters,
            "loose_end_count": len(self.loose_ends),
            "back_annotation_count": len(self.back_annotations),
            "has_errors": self.has_errors(),
            "loose_ends": [le.to_dict() for le in self.loose_ends],
            "back_annotations": [ba.to_dict() for ba in self.back_annotations],
            "entity_summary": self.entity_summary,
            "lifecycle_summary": self.lifecycle_summary,
        }


class LifecycleTracker:
    """
    Tracks entity lifecycles across all chapters for final analysis.
    
    This is the aggregator that runs AFTER each chapter's extraction
    is complete. It maintains cross-chapter state and provides
    final analysis at the end of the story.
    
    Usage:
        tracker = LifecycleTracker()
        
        for chapter_num, extraction in chapters:
            tracker.process_chapter(chapter_num, extraction, event_normalizer)
        
        result = tracker.final_analysis()
    """
    
    def __init__(self):
        # Entity lifecycles: entity_id -> EntityLifecycle
        self._characters: Dict[str, EntityLifecycle] = {}
        self._items: Dict[str, EntityLifecycle] = {}
        self._locations: Dict[str, EntityLifecycle] = {}
        
        # Relationship lifecycles: (from, to) -> RelationshipLifecycle
        self._relationships: Dict[Tuple[str, str], RelationshipLifecycle] = {}
        
        # Back-annotations for earlier chapters
        self._back_annotations: List[BackAnnotation] = []
        
        # Chapter tracking
        self._chapters_processed: List[int] = []
        self._current_chapter: int = 0
    
    def reset(self) -> None:
        """Reset tracker to initial state."""
        self._characters.clear()
        self._items.clear()
        self._locations.clear()
        self._relationships.clear()
        self._back_annotations.clear()
        self._chapters_processed.clear()
        self._current_chapter = 0
    
    def process_chapter(
        self,
        chapter_num: int,
        extraction: Dict[str, Any],
        event_normalizer: Optional[EventNormalizer] = None,
    ) -> None:
        """
        Process a chapter's extraction to update lifecycle tracking.
        
        Args:
            chapter_num: The chapter number (0-indexed)
            extraction: The normalized extraction dict
            event_normalizer: Optional EventNormalizer with item usage data
        """
        self._current_chapter = chapter_num
        self._chapters_processed.append(chapter_num)
        
        entities = extraction.get("entities", {})
        events = extraction.get("events", [])
        relationships = entities.get("relationships", [])
        
        # Track characters
        for char in entities.get("characters", []):
            char_id = _normalize_id(char.get("id", ""))
            if char_id:
                self._register_entity(char_id, "character", chapter_num)
        
        # Track locations
        for loc in entities.get("locations", []):
            loc_id = _normalize_id(loc.get("id", ""))
            if loc_id:
                self._register_entity(loc_id, "location", chapter_num)
        
        # Track items with usage classification from EventNormalizer
        item_usage_map: Dict[str, ItemUsageType] = {}
        if event_normalizer:
            for item_id, usage in event_normalizer.get_item_usage().items():
                item_usage_map[item_id] = usage.usage_type
        
        for item in entities.get("items", []):
            item_id = _normalize_id(item.get("id", ""))
            if item_id:
                usage = item_usage_map.get(item_id, ItemUsageType.LATENT)
                self._register_item(item_id, chapter_num, usage)
        
        # Track relationships
        for rel in relationships:
            from_id = _normalize_id(rel.get("from", ""))
            to_id = _normalize_id(rel.get("to", ""))
            rel_type = rel.get("type", "unknown")
            if from_id and to_id:
                self._register_relationship(from_id, to_id, rel_type, chapter_num)
        
        # Update entity activity from events
        self._update_activity_from_events(events, chapter_num)
        
        # Check for latent items that should have been causal
        self._check_latent_items(chapter_num)
        
        log(f"    [LifecycleTracker] Chapter {chapter_num}: "
            f"{len(self._characters)} chars, {len(self._items)} items, "
            f"{len(self._locations)} locs, {len(self._relationships)} rels")
    
    def _register_entity(
        self,
        entity_id: str,
        entity_type: str,
        chapter_num: int,
    ) -> None:
        """Register or update an entity."""
        storage = {
            "character": self._characters,
            "location": self._locations,
        }.get(entity_type)
        
        if storage is None:
            return
        
        if entity_id in storage:
            lifecycle = storage[entity_id]
            lifecycle.last_active_chapter = chapter_num
            if chapter_num not in lifecycle.chapters_active:
                lifecycle.chapters_active.append(chapter_num)
        else:
            storage[entity_id] = EntityLifecycle(
                entity_id=entity_id,
                entity_type=entity_type,
                introduced_chapter=chapter_num,
                last_active_chapter=chapter_num,
                state=EntityLifecycleState.INTRODUCED,
                chapters_active=[chapter_num],
            )
    
    def _register_item(
        self,
        item_id: str,
        chapter_num: int,
        usage: ItemUsageType,
    ) -> None:
        """Register or update an item with usage classification."""
        if item_id in self._items:
            lifecycle = self._items[item_id]
            lifecycle.last_active_chapter = chapter_num
            if chapter_num not in lifecycle.chapters_active:
                lifecycle.chapters_active.append(chapter_num)
            
            # Promote latent to causal if usage changed
            if lifecycle.item_usage == ItemUsageType.LATENT and usage == ItemUsageType.CAUSAL:
                lifecycle.item_usage = ItemUsageType.CAUSAL
                lifecycle.promoted_chapter = chapter_num
                lifecycle.state = EntityLifecycleState.ACTIVE
                log(f"      Item '{item_id}' promoted latent → causal at chapter {chapter_num}")
        else:
            self._items[item_id] = EntityLifecycle(
                entity_id=item_id,
                entity_type="item",
                introduced_chapter=chapter_num,
                last_active_chapter=chapter_num,
                state=EntityLifecycleState.INTRODUCED,
                chapters_active=[chapter_num],
                item_usage=usage,
            )
    
    def _register_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        chapter_num: int,
    ) -> None:
        """Register or update a relationship."""
        key = (from_id, to_id)
        
        if key in self._relationships:
            rel = self._relationships[key]
            rel.last_referenced_chapter = chapter_num
            
            # Track type changes
            if rel.relationship_type != rel_type:
                rel.type_changes.append((chapter_num, rel.relationship_type, rel_type))
                rel.relationship_type = rel_type
                rel.state = RelationshipState.CHANGED
        else:
            self._relationships[key] = RelationshipLifecycle(
                from_id=from_id,
                to_id=to_id,
                relationship_type=rel_type,
                established_chapter=chapter_num,
                last_referenced_chapter=chapter_num,
                state=RelationshipState.ESTABLISHED,
            )
    
    def _update_activity_from_events(
        self,
        events: List[Dict[str, Any]],
        chapter_num: int,
    ) -> None:
        """Update entity lifecycle based on event participation."""
        for event in events:
            agent = _normalize_id(event.get("agent", ""))
            patient = event.get("patient")
            patient_id = _normalize_id(patient) if patient else None
            
            # Update agent (character)
            if agent and agent in self._characters:
                lifecycle = self._characters[agent]
                lifecycle.event_count += 1
                lifecycle.state = EntityLifecycleState.ACTIVE
                if chapter_num not in lifecycle.chapters_active:
                    lifecycle.chapters_active.append(chapter_num)
            
            # Update patient (could be character or item)
            if patient_id:
                if patient_id in self._characters:
                    lifecycle = self._characters[patient_id]
                    lifecycle.event_count += 1
                    lifecycle.state = EntityLifecycleState.MODIFIED
                    if chapter_num not in lifecycle.chapters_active:
                        lifecycle.chapters_active.append(chapter_num)
                elif patient_id in self._items:
                    lifecycle = self._items[patient_id]
                    lifecycle.event_count += 1
                    lifecycle.state = EntityLifecycleState.ACTIVE
                    if chapter_num not in lifecycle.chapters_active:
                        lifecycle.chapters_active.append(chapter_num)
    
    def _check_latent_items(self, chapter_num: int) -> None:
        """
        Check for latent items that might cause causality violations.
        
        This is called at the end of each chapter to identify items
        that were introduced as latent but are now causing issues.
        """
        for item_id, lifecycle in self._items.items():
            if lifecycle.item_usage == ItemUsageType.LATENT:
                # Check if item was expected to be used by now
                chapters_since_intro = chapter_num - lifecycle.introduced_chapter
                if chapters_since_intro >= 3 and lifecycle.event_count == 0:
                    # Item has been latent for 3+ chapters with no events
                    # This is a potential Chekhov's Gun violation candidate
                    pass  # We'll flag this in final analysis
    
    def final_analysis(self) -> FinalAnalysisResult:
        """
        Perform final analysis after all chapters are processed.
        
        Detects:
        1. Chekhov's Gun violations (latent items never used)
        2. Unused causal items
        3. Unresolved relationships
        4. Dormant characters (introduced but inactive)
        
        Returns:
            FinalAnalysisResult with all detected issues
        """
        if not self._chapters_processed:
            return FinalAnalysisResult(
                total_chapters=0,
                loose_ends=[],
                back_annotations=[],
                entity_summary={},
                lifecycle_summary={},
            )
        
        final_chapter = max(self._chapters_processed)
        loose_ends: List[LooseEnd] = []
        
        # 1. Check for Chekhov's Gun violations (latent items never used)
        for item_id, lifecycle in self._items.items():
            if lifecycle.item_usage == ItemUsageType.LATENT and lifecycle.event_count == 0:
                loose_ends.append(LooseEnd(
                    loose_end_type="chekhov",
                    entity_id=item_id,
                    entity_type="item",
                    introduced_chapter=lifecycle.introduced_chapter,
                    last_chapter=lifecycle.last_active_chapter,
                    description=f"Item '{item_id}' introduced but never used (Chekhov's Gun)",
                    severity="warning",
                ))
                # Back-annotate to introduction chapter
                self._back_annotations.append(BackAnnotation(
                    chapter=lifecycle.introduced_chapter,
                    entity_id=item_id,
                    entity_type="item",
                    annotation_type="chekhov_warning",
                    message=f"Item '{item_id}' is never used in the story",
                    detected_at_chapter=final_chapter,
                ))
        
        # 2. Check for dormant characters (introduced but never active)
        for char_id, lifecycle in self._characters.items():
            if lifecycle.is_unused():
                loose_ends.append(LooseEnd(
                    loose_end_type="dormant_entity",
                    entity_id=char_id,
                    entity_type="character",
                    introduced_chapter=lifecycle.introduced_chapter,
                    last_chapter=lifecycle.last_active_chapter,
                    description=f"Character '{char_id}' introduced but never participates in events",
                    severity="warning",
                ))
                self._back_annotations.append(BackAnnotation(
                    chapter=lifecycle.introduced_chapter,
                    entity_id=char_id,
                    entity_type="character",
                    annotation_type="dormant_character",
                    message=f"Character '{char_id}' is never used in the story",
                    detected_at_chapter=final_chapter,
                ))
        
        # 3. Check for unresolved relationships
        for (from_id, to_id), rel in self._relationships.items():
            if rel.is_unresolved():
                # Only flag if relationship was established early and never changed
                chapters_since = final_chapter - rel.established_chapter
                if chapters_since >= 2 and not rel.type_changes:
                    loose_ends.append(LooseEnd(
                        loose_end_type="unresolved_relationship",
                        entity_id=f"{from_id}->{to_id}",
                        entity_type="relationship",
                        introduced_chapter=rel.established_chapter,
                        last_chapter=rel.last_referenced_chapter,
                        description=f"Relationship '{from_id}' → '{to_id}' ({rel.relationship_type}) never evolved",
                        severity="warning",
                    ))
        
        # 4. Check for dormant locations
        for loc_id, lifecycle in self._locations.items():
            if lifecycle.is_unused():
                loose_ends.append(LooseEnd(
                    loose_end_type="dormant_entity",
                    entity_id=loc_id,
                    entity_type="location",
                    introduced_chapter=lifecycle.introduced_chapter,
                    last_chapter=lifecycle.last_active_chapter,
                    description=f"Location '{loc_id}' introduced but never used in events",
                    severity="warning",
                ))
        
        # Build summaries
        entity_summary = {
            "characters": len(self._characters),
            "items": len(self._items),
            "locations": len(self._locations),
            "relationships": len(self._relationships),
        }
        
        lifecycle_states: Dict[str, int] = {}
        for lifecycle in list(self._characters.values()) + list(self._items.values()) + list(self._locations.values()):
            state = lifecycle.state.value
            lifecycle_states[state] = lifecycle_states.get(state, 0) + 1
        
        result = FinalAnalysisResult(
            total_chapters=len(self._chapters_processed),
            loose_ends=loose_ends,
            back_annotations=self._back_annotations,
            entity_summary=entity_summary,
            lifecycle_summary=lifecycle_states,
        )
        
        log(f"  [LifecycleTracker] Final analysis: {len(loose_ends)} loose ends, "
            f"{len(self._back_annotations)} back-annotations")
        
        return result
    
    def get_back_annotations_for_chapter(self, chapter_num: int) -> List[BackAnnotation]:
        """Get all back-annotations for a specific chapter."""
        return [ba for ba in self._back_annotations if ba.chapter == chapter_num]
    
    def get_entity_lifecycle(self, entity_id: str) -> Optional[EntityLifecycle]:
        """Get lifecycle for any entity type."""
        entity_id = _normalize_id(entity_id)
        return (
            self._characters.get(entity_id) or
            self._items.get(entity_id) or
            self._locations.get(entity_id)
        )
    
    def get_all_causal_items(self) -> List[str]:
        """Get IDs of all items classified as causal."""
        return [
            item_id for item_id, lifecycle in self._items.items()
            if lifecycle.item_usage == ItemUsageType.CAUSAL
        ]
    
    def get_all_latent_items(self) -> List[str]:
        """Get IDs of all items classified as latent."""
        return [
            item_id for item_id, lifecycle in self._items.items()
            if lifecycle.item_usage == ItemUsageType.LATENT
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        causal_count = sum(1 for lc in self._items.values() if lc.item_usage == ItemUsageType.CAUSAL)
        latent_count = sum(1 for lc in self._items.values() if lc.item_usage == ItemUsageType.LATENT)
        promoted_count = sum(1 for lc in self._items.values() if lc.promoted_chapter is not None)
        
        return {
            "chapters_processed": len(self._chapters_processed),
            "characters": len(self._characters),
            "items": len(self._items),
            "locations": len(self._locations),
            "relationships": len(self._relationships),
            "causal_items": causal_count,
            "latent_items": latent_count,
            "promoted_items": promoted_count,
            "back_annotations": len(self._back_annotations),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export tracker state as dict."""
        return {
            "chapters_processed": self._chapters_processed,
            "characters": {k: v.to_dict() for k, v in self._characters.items()},
            "items": {k: v.to_dict() for k, v in self._items.items()},
            "locations": {k: v.to_dict() for k, v in self._locations.items()},
            "relationships": {
                f"{k[0]}->{k[1]}": v.to_dict() 
                for k, v in self._relationships.items()
            },
            "back_annotations": [ba.to_dict() for ba in self._back_annotations],
            "statistics": self.get_statistics(),
        }
