"""
Final Chapter Analysis - Story-Wide Consistency Checking

Per LOGIC_DESIGN.md Section 6 (Final Chapter Analysis):
    After the final chapter:
        - Audit all active and deactivated rules
        - Detect loose ends:
            - Unresolved items
            - Introduced but unused entities
            - Chekhov-style artifacts
        - Detect long-range inconsistencies not visible at chapter scope

Phase 5 Refactoring (Step 5.2):
    - Implement rule auditing with provenance
    - Implement loose ends detection
    - Implement long-range inconsistency detection

Does NOT:
    - Generate natural language explanations
    - Make subjective judgments about story quality
    - Modify any state (read-only analysis)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, TYPE_CHECKING
from datetime import datetime
import json

if TYPE_CHECKING:
    from .state_manager import StateManager
    from .rule_registry import RuleRegistry


# =============================================================================
# STRUCTURED OUTPUT TYPES FOR FINAL ANALYSIS
# =============================================================================

@dataclass
class RuleAuditEntry:
    """
    Audit entry for a single rule.
    
    Tracks whether a rule is active, deactivated, or overridden,
    and records how often it was applied.
    """
    rule_id: str
    rule_layer: str  # "universal", "learned", "story"
    active: bool
    overridden_by: Optional[str] = None
    override_reason: Optional[str] = None
    times_applied: int = 0
    times_triggered_violation: int = 0
    chapters_active: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_layer": self.rule_layer,
            "active": self.active,
            "overridden_by": self.overridden_by,
            "override_reason": self.override_reason,
            "times_applied": self.times_applied,
            "times_triggered_violation": self.times_triggered_violation,
            "chapters_active": self.chapters_active,
        }


@dataclass
class LooseEnd:
    """
    A loose end detected in the story.
    
    Types:
        - unresolved_item: Item introduced but never used
        - unused_entity: Character/location introduced but not active
        - chekhov: Significant object mentioned but never resolved
        - chekhov_latent: Phase 5/6 - Latent item never promoted to causal
        - dangling_relationship: Relationship established but not concluded
    
    Phase 7: Enhanced with canonical IDs, aliases, and item lifecycle.
    """
    loose_end_type: str
    entity_id: str  # Always canonical ID (Phase 7)
    entity_type: str  # "character", "item", "location", "relationship"
    introduced_chapter: int
    introduced_event: Optional[str] = None
    last_referenced_chapter: Optional[int] = None
    expected_resolution: Optional[str] = None  # What we expected to happen
    # Phase 7: Enhanced diagnostics
    aliases: List[str] = field(default_factory=list)
    item_relevance: Optional[str] = None  # "causal", "latent", "background"
    item_lifecycle: Optional[str] = None  # "introduced", "carried", "used", etc.
    item_original_relevance: Optional[str] = None  # Original relevance before promotion
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.loose_end_type,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "introduced_chapter": self.introduced_chapter,
            "introduced_event": self.introduced_event,
            "last_referenced_chapter": self.last_referenced_chapter,
            "expected_resolution": self.expected_resolution,
        }
        # Phase 7: Include enhanced diagnostics
        if self.aliases:
            result["aliases"] = self.aliases
        if self.item_relevance:
            result["item_relevance"] = self.item_relevance
        if self.item_lifecycle:
            result["item_lifecycle"] = self.item_lifecycle
        if self.item_original_relevance:
            result["item_original_relevance"] = self.item_original_relevance
        return result


@dataclass
class LongRangeInconsistency:
    """
    An inconsistency that spans multiple chapters.
    
    These are inconsistencies not visible at single-chapter scope.
    """
    inconsistency_type: str
    description: str  # Structured description (not natural language)
    first_chapter: int
    second_chapter: int
    entities_involved: List[str] = field(default_factory=list)
    first_event: Optional[str] = None
    second_event: Optional[str] = None
    severity: str = "soft"  # "hard" or "soft"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.inconsistency_type,
            "description": self.description,
            "first_chapter": self.first_chapter,
            "second_chapter": self.second_chapter,
            "entities_involved": self.entities_involved,
            "first_event": self.first_event,
            "second_event": self.second_event,
            "severity": self.severity,
        }


@dataclass
class FinalAnalysisResult:
    """
    Complete result of final chapter analysis.
    
    Per LOGIC_DESIGN.md Section 6:
        - Rule audit
        - Loose ends
        - Long-range inconsistencies
    """
    story_id: str
    total_chapters: int
    total_events: int
    total_violations: int
    
    # Rule audit
    rule_audit: List[RuleAuditEntry] = field(default_factory=list)
    active_rules_count: int = 0
    deactivated_rules_count: int = 0
    learned_rules_count: int = 0
    
    # Loose ends
    loose_ends: List[LooseEnd] = field(default_factory=list)
    
    # Long-range inconsistencies
    long_range_inconsistencies: List[LongRangeInconsistency] = field(default_factory=list)
    
    # Statistics
    entities_introduced: Dict[str, int] = field(default_factory=dict)  # type -> count
    entities_resolved: Dict[str, int] = field(default_factory=dict)
    
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_id": self.story_id,
            "total_chapters": self.total_chapters,
            "total_events": self.total_events,
            "total_violations": self.total_violations,
            "rule_audit": {
                "active_count": self.active_rules_count,
                "deactivated_count": self.deactivated_rules_count,
                "learned_count": self.learned_rules_count,
                "rules": [r.to_dict() for r in self.rule_audit],
            },
            "loose_ends": {
                "count": len(self.loose_ends),
                "items": [le.to_dict() for le in self.loose_ends],
            },
            "long_range_inconsistencies": {
                "count": len(self.long_range_inconsistencies),
                "items": [lri.to_dict() for lri in self.long_range_inconsistencies],
            },
            "statistics": {
                "entities_introduced": self.entities_introduced,
                "entities_resolved": self.entities_resolved,
            },
            "timestamp": self.timestamp,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# FINAL ANALYSIS ENGINE
# =============================================================================

class FinalAnalyzer:
    """
    Performs final chapter analysis after processing all chapters.
    
    Per LOGIC_DESIGN.md Section 6:
        - Audit all active and deactivated rules
        - Detect loose ends
        - Detect long-range inconsistencies
    
    Phase 5: Also detects Chekhov's Gun violations from ItemTracker
    Phase 7: Enhanced diagnostics with canonical IDs, aliases, item lifecycle
    
    Uses data from StateManager and RuleRegistry.
    Does NOT perform any reasoning - only aggregates and reports.
    
    Phase 8.4: Can also read from PersistentContext for cross-session analysis.
    """
    
    def __init__(self, state_manager: 'StateManager', rule_registry: 'RuleRegistry',
                 item_tracker: 'ItemTracker' = None, alias_resolver: 'AliasResolver' = None):
        from .state_manager import StateManager
        from .rule_registry import RuleRegistry
        
        self.state_manager = state_manager
        self.rule_registry = rule_registry
        self.item_tracker = item_tracker  # Phase 5: Optional ItemTracker for Chekhov detection
        self.alias_resolver = alias_resolver  # Phase 7: Optional AliasResolver for canonical IDs
        self._persistent_context = None  # Phase 8.4: Optional PersistentContext
        
        # Track entities across chapters
        self.entity_introductions: Dict[str, Dict[str, Any]] = {}  # entity_id -> {chapter, event, type}
        self.entity_references: Dict[str, List[int]] = {}  # entity_id -> [chapters where referenced]
        self.entity_resolutions: Dict[str, Dict[str, Any]] = {}  # entity_id -> {chapter, event, resolution_type}
        
        # Phase 5: Track latent items for Chekhov detection
        self.latent_items: Dict[str, Dict[str, Any]] = {}  # item_id -> {introduced_chapter, ...}
        
        # Track rule usage
        self.rule_usage: Dict[str, Dict[str, Any]] = {}  # rule_id -> {applied, violations, chapters}
        
        # Track violations per chapter
        self.chapter_violations: Dict[int, List[Dict]] = {}  # chapter -> violations
        
        # Total event count
        self.total_events: int = 0
    
    def set_persistent_context(self, context) -> None:
        """
        Set the persistent context for cross-session analysis.
        
        Phase 8.4: Allows FinalAnalyzer to read from persisted context
        instead of requiring all data in memory.
        
        Args:
            context: PersistentContext instance (must be loaded)
        """
        self._persistent_context = context
    
    def set_item_tracker(self, item_tracker: 'ItemTracker') -> None:
        """Set the item tracker (for late initialization)."""
        self.item_tracker = item_tracker
    
    def set_alias_resolver(self, alias_resolver: 'AliasResolver') -> None:
        """Set the alias resolver (for late initialization). Phase 7."""
        self.alias_resolver = alias_resolver
    
    def get_entity_aliases(self, entity_id: str) -> List[str]:
        """
        Phase 7: Get aliases for an entity.
        
        Returns list of aliases (excluding the canonical ID itself).
        """
        if not self.alias_resolver:
            return []
        aliases = self.alias_resolver.get_aliases(entity_id)
        # Exclude the canonical ID itself from the alias list
        return [a for a in aliases if a != entity_id]
    
    def get_item_diagnostics(self, item_id: str) -> Dict[str, Any]:
        """
        Phase 7: Get item diagnostics (relevance, lifecycle, carrier).
        
        Returns dict with item info or empty dict if not tracked.
        """
        if not self.item_tracker:
            return {}
        item = self.item_tracker.get_item(item_id)
        if not item:
            return {}
        return {
            "relevance": item.relevance.value,
            "lifecycle": item.lifecycle_state.value,
            "carrier": item.carrier,
            "original_relevance": item.original_relevance.value,
            "promoted_chapter": item.promoted_to_causal_chapter,
        }
    
    def record_chapter_evaluation(self, chapter_num: int, 
                                   events: List[Dict], 
                                   violations: List[Dict],
                                   entities: Dict[str, Any]) -> None:
        """
        Record results from a chapter evaluation for later analysis.
        
        Called after each chapter is processed.
        
        Args:
            chapter_num: The chapter number (0-indexed)
            events: List of events in the chapter
            violations: List of violations detected
            entities: Dict of entities (characters, locations, items)
        """
        self.total_events += len(events)
        
        # Record violations
        self.chapter_violations[chapter_num] = violations
        
        # Track entity introductions and references
        self._track_entities(chapter_num, entities)
        
        # Track entity references in events
        for event in events:
            self._track_event_references(chapter_num, event)
    
    def _track_entities(self, chapter_num: int, entities: Dict[str, Any]) -> None:
        """Track entity introductions from structured data."""
        for char in entities.get("characters", []):
            char_id = char.get("id") or char.get("name", "")
            if char_id and char_id not in self.entity_introductions:
                self.entity_introductions[char_id] = {
                    "chapter": chapter_num,
                    "type": "character",
                    "event": None,
                }
            if char_id:
                if char_id not in self.entity_references:
                    self.entity_references[char_id] = []
                if chapter_num not in self.entity_references[char_id]:
                    self.entity_references[char_id].append(chapter_num)
        
        for item in entities.get("items", []):
            item_id = item.get("id") or item.get("name", "")
            if item_id and item_id not in self.entity_introductions:
                self.entity_introductions[item_id] = {
                    "chapter": chapter_num,
                    "type": "item",
                    "event": None,
                }
            if item_id:
                if item_id not in self.entity_references:
                    self.entity_references[item_id] = []
                if chapter_num not in self.entity_references[item_id]:
                    self.entity_references[item_id].append(chapter_num)
        
        for loc in entities.get("locations", []):
            loc_id = loc.get("id") or loc.get("name", "")
            if loc_id and loc_id not in self.entity_introductions:
                self.entity_introductions[loc_id] = {
                    "chapter": chapter_num,
                    "type": "location",
                    "event": None,
                }
            if loc_id:
                if loc_id not in self.entity_references:
                    self.entity_references[loc_id] = []
                if chapter_num not in self.entity_references[loc_id]:
                    self.entity_references[loc_id].append(chapter_num)
    
    def _track_event_references(self, chapter_num: int, event: Dict) -> None:
        """Track entity references in an event."""
        for field in ["agent", "patient", "location"]:
            entity_id = event.get(field)
            if entity_id:
                if entity_id not in self.entity_references:
                    self.entity_references[entity_id] = []
                if chapter_num not in self.entity_references[entity_id]:
                    self.entity_references[entity_id].append(chapter_num)
                
                # Check for resolution events (death, destruction, etc.)
                event_type = event.get("type", "").lower()
                if event_type in ("die", "dies", "death", "destroy", "destroyed", "consumed", "used"):
                    if entity_id not in self.entity_resolutions:
                        self.entity_resolutions[entity_id] = {
                            "chapter": chapter_num,
                            "event": event.get("global_id"),
                            "resolution_type": event_type,
                        }
    
    def record_rule_usage(self, rule_id: str, chapter_num: int, 
                          triggered_violation: bool = False) -> None:
        """Record that a rule was applied in a chapter."""
        if rule_id not in self.rule_usage:
            self.rule_usage[rule_id] = {
                "applied": 0,
                "violations": 0,
                "chapters": set(),
            }
        
        self.rule_usage[rule_id]["applied"] += 1
        self.rule_usage[rule_id]["chapters"].add(chapter_num)
        if triggered_violation:
            self.rule_usage[rule_id]["violations"] += 1
    
    def analyze(self, story_id: str, total_chapters: int, 
                use_lifecycle: bool = True) -> FinalAnalysisResult:
        """
        Perform final analysis after all chapters are processed.
        
        Returns structured result per LOGIC_DESIGN.md Section 6.
        
        Args:
            story_id: Story identifier
            total_chapters: Total number of chapters processed
            use_lifecycle: If True (default), use lifecycle-based detection
                          which operates on final state only. If False, use
                          legacy tracking-based detection.
        
        Phase 8.5: Prefers lifecycle-based detection that operates ONLY on
        final WorldState, EntityRegistry, and ItemTracker. No historical
        snapshots required.
        """
        if use_lifecycle:
            return self.analyze_from_lifecycle(story_id, total_chapters)
        
        # Legacy mode: uses entity_introductions tracking from record_chapter_evaluation
        result = FinalAnalysisResult(
            story_id=story_id,
            total_chapters=total_chapters,
            total_events=self.total_events,
            total_violations=sum(len(v) for v in self.chapter_violations.values()),
            timestamp=datetime.now().isoformat(),
        )
        
        # Perform rule audit
        self._audit_rules(result)
        
        # Detect loose ends
        self._detect_loose_ends(result, total_chapters)
        
        # Detect long-range inconsistencies
        self._detect_long_range_inconsistencies(result)
        
        # Compute statistics
        self._compute_statistics(result)
        
        return result
    
    def _audit_rules(self, result: FinalAnalysisResult) -> None:
        """Audit all rules from the registry."""
        for rule_id, rule in self.rule_registry.rules.items():
            usage = self.rule_usage.get(rule_id, {"applied": 0, "violations": 0, "chapters": set()})
            
            entry = RuleAuditEntry(
                rule_id=rule_id,
                rule_layer=rule.layer.name.lower(),
                active=rule.active,
                overridden_by=rule.overridden_by,
                override_reason=None,  # Could be added if we track this
                times_applied=usage["applied"],
                times_triggered_violation=usage["violations"],
                chapters_active=sorted(list(usage["chapters"])),
            )
            
            result.rule_audit.append(entry)
            
            if rule.active:
                result.active_rules_count += 1
            else:
                result.deactivated_rules_count += 1
            
            if rule.layer.name.lower() == "learned":
                result.learned_rules_count += 1
    
    def _detect_loose_ends(self, result: FinalAnalysisResult, total_chapters: int) -> None:
        """Detect loose ends in the story."""
        for entity_id, intro in self.entity_introductions.items():
            refs = self.entity_references.get(entity_id, [])
            resolution = self.entity_resolutions.get(entity_id)
            
            # Unresolved items (items introduced but never used/resolved)
            if intro["type"] == "item" and not resolution:
                # Only flag if item was only referenced in a few chapters
                if len(refs) <= 2:
                    result.loose_ends.append(LooseEnd(
                        loose_end_type="unresolved_item",
                        entity_id=entity_id,
                        entity_type="item",
                        introduced_chapter=intro["chapter"],
                        introduced_event=intro.get("event"),
                        last_referenced_chapter=max(refs) if refs else intro["chapter"],
                        expected_resolution="Item should be used or resolved",
                    ))
            
            # Unused entities (introduced but never actively used after introduction)
            if intro["type"] == "character" and len(refs) == 1 and refs[0] == intro["chapter"]:
                # Character only appears in introduction chapter
                result.loose_ends.append(LooseEnd(
                    loose_end_type="unused_entity",
                    entity_id=entity_id,
                    entity_type="character",
                    introduced_chapter=intro["chapter"],
                    introduced_event=intro.get("event"),
                    last_referenced_chapter=intro["chapter"],
                    expected_resolution="Character introduced but never used",
                ))
            
            # Chekhov's gun - significant items mentioned early but not resolved
            if intro["type"] == "item":
                # If item is introduced early (first quarter) and not resolved
                early_threshold = max(1, total_chapters // 4)
                if intro["chapter"] <= early_threshold and not resolution:
                    if len(refs) > 2:  # Item was mentioned multiple times
                        result.loose_ends.append(LooseEnd(
                            loose_end_type="chekhov",
                            entity_id=entity_id,
                            entity_type="item",
                            introduced_chapter=intro["chapter"],
                            introduced_event=intro.get("event"),
                            last_referenced_chapter=max(refs) if refs else intro["chapter"],
                            expected_resolution="Chekhov's gun: item mentioned multiple times but not resolved",
                        ))
        
        # Phase 5: Detect Chekhov violations from ItemTracker latent items
        self._detect_chekhov_from_item_tracker(result, total_chapters)
    
    def _detect_chekhov_from_item_tracker(self, result: FinalAnalysisResult, 
                                           total_chapters: int) -> None:
        """
        Detect Chekhov's Gun violations from ItemTracker's latent items.
        
        Phase 5: Unused latent items are reported as causality errors
        attributed to the chapter where they were introduced.
        
        Phase 6: Only items that REMAINED latent (never transitioned to causal)
        are flagged. Items that appeared in events get promoted to causal
        automatically and are NOT considered Chekhov violations.
        
        This is a POST-STORY check, not a chapter-local logical contradiction.
        """
        if not self.item_tracker:
            return
        
        # Get Chekhov candidates (latent items that remained latent - never used in events)
        chekhov_candidates = self.item_tracker.get_chekhov_candidates()
        
        for tracked_item in chekhov_candidates:
            # Phase 7: Include enhanced item diagnostics
            result.loose_ends.append(LooseEnd(
                loose_end_type="chekhov_latent",
                entity_id=tracked_item.item_id,  # Canonical ID
                entity_type="item",
                introduced_chapter=tracked_item.introduced_chapter,
                introduced_event=None,
                last_referenced_chapter=tracked_item.last_mentioned_chapter,
                expected_resolution=f"Latent item '{tracked_item.item_id}' was introduced but never used (Chekhov's Gun violation)",
                # Phase 7: Item lifecycle and relevance info
                item_relevance=tracked_item.relevance.value,
                item_lifecycle=tracked_item.lifecycle_state.value,
                item_original_relevance=tracked_item.original_relevance.value,
            ))
            
            # Also add as a violation to the introduction chapter
            intro_chapter = tracked_item.introduced_chapter
            if intro_chapter not in self.chapter_violations:
                self.chapter_violations[intro_chapter] = []
            
            # Phase 7: Add Chekhov violation with enhanced diagnostics
            self.chapter_violations[intro_chapter].append({
                "category": "causality",
                "type": "chekhov_gun",
                "rule": "items_chekhov_gun",
                "entity": tracked_item.item_id,  # Canonical ID
                "entity_type": "item",
                "detail": f"Latent item '{tracked_item.item_id}' introduced in chapter {intro_chapter} but never used",
                "severity": "soft",
                "introduced_chapter": intro_chapter,
                "last_mentioned_chapter": tracked_item.last_mentioned_chapter,
                # Phase 7: Item diagnostics
                "item_relevance": tracked_item.relevance.value,
                "item_lifecycle": tracked_item.lifecycle_state.value,
                "item_original_relevance": tracked_item.original_relevance.value,
            })
    
    def _detect_long_range_inconsistencies(self, result: FinalAnalysisResult) -> None:
        """Detect inconsistencies that span multiple chapters."""
        # Look for patterns across chapter violations
        entity_states: Dict[str, Dict[int, str]] = {}  # entity -> {chapter -> state}
        
        # Build entity state history from violations
        for chapter_num, violations in self.chapter_violations.items():
            for v in violations:
                detail = v.get("detail", "")
                event_id = v.get("event", "")
                
                # Track dead character violations
                if v.get("type") == "dead_agent" or v.get("type") == "dead_patient":
                    if detail:
                        if detail not in entity_states:
                            entity_states[detail] = {}
                        entity_states[detail][chapter_num] = "dead_acting"
        
        # Check for resurrection-like patterns (entity dead then active)
        for entity_id, states in entity_states.items():
            chapters = sorted(states.keys())
            for i in range(len(chapters) - 1):
                if states[chapters[i]] == "dead_acting":
                    # This is already a violation, but mark it as long-range if chapters are far apart
                    for j in range(i + 1, len(chapters)):
                        if chapters[j] - chapters[i] > 1:
                            result.long_range_inconsistencies.append(LongRangeInconsistency(
                                inconsistency_type="repeated_dead_action",
                                description=f"Entity {entity_id} acts while dead across multiple chapters",
                                first_chapter=chapters[i],
                                second_chapter=chapters[j],
                                entities_involved=[entity_id],
                                severity="hard",
                            ))
                            break
        
        # Check for location inconsistencies across chapters
        # (entity in location A in chapter X, but immediately in distant location B in chapter X+1)
        # This would require more detailed tracking in StateManager
    
    def _compute_statistics(self, result: FinalAnalysisResult) -> None:
        """Compute summary statistics."""
        for entity_id, intro in self.entity_introductions.items():
            entity_type = intro["type"]
            if entity_type not in result.entities_introduced:
                result.entities_introduced[entity_type] = 0
            result.entities_introduced[entity_type] += 1
        
        for entity_id, resolution in self.entity_resolutions.items():
            entity_type = self.entity_introductions.get(entity_id, {}).get("type", "unknown")
            if entity_type not in result.entities_resolved:
                result.entities_resolved[entity_type] = 0
            result.entities_resolved[entity_type] += 1
    
    # =========================================================================
    # PersistentContext Integration (Phase 8.4)
    # =========================================================================
    
    def detect_chekhov_from_persistent_context(self) -> List[LooseEnd]:
        """
        Detect Chekhov's Gun violations from PersistentContext.
        
        Phase 8.4: Allows analysis without ItemTracker in memory.
        Reads from persisted item tracker data.
        
        Returns:
            List of LooseEnd objects for Chekhov violations
        """
        if not self._persistent_context:
            return []
        
        violations = []
        for item_data in self._persistent_context.get_chekhov_candidates():
            violations.append(LooseEnd(
                loose_end_type="chekhov_latent",
                entity_id=item_data["item_id"],
                entity_type="item",
                introduced_chapter=item_data.get("introduced_chapter", 0),
                introduced_event=None,
                last_referenced_chapter=item_data.get("last_mentioned_chapter"),
                expected_resolution=f"Latent item '{item_data['item_id']}' was introduced but never used",
                item_relevance=item_data.get("relevance"),
                item_lifecycle=item_data.get("lifecycle_state"),
                item_original_relevance=item_data.get("original_relevance"),
            ))
        
        return violations
    
    def get_lifecycle_summary_from_context(self) -> Dict[str, int]:
        """
        Get entity lifecycle summary from PersistentContext.
        
        Phase 8.4: Returns counts of active/latent/frozen entities.
        """
        if not self._persistent_context:
            return {"active": 0, "latent": 0, "frozen": 0}
        
        return self._persistent_context.get_lifecycle_summary()
    
    def get_context_statistics(self) -> Dict[str, Any]:
        """
        Get statistics from PersistentContext.
        
        Phase 8.4: Returns context metadata and counts.
        """
        if not self._persistent_context:
            return {}
        
        return self._persistent_context.get_statistics()
    
    # =========================================================================
    # Lifecycle-Based Detection (Phase 8.5)
    # =========================================================================
    
    def detect_unused_characters_from_registry(self) -> List[LooseEnd]:
        """
        Detect unused characters using EntityRegistry lifecycle states.
        
        Phase 8.5: Characters in LATENT or FROZEN state that never acted
        (last_acted_chapter is None or equals first_seen_chapter) are unused.
        
        This operates on final WorldState + EntityRegistry only.
        No historical snapshots required.
        """
        from .entity_registry import EntityType, LifecycleState
        
        unused = []
        registry = self.state_manager.entity_registry
        
        for entity in registry.get_all_characters():
            # Skip dead characters - they were resolved
            if entity.state == "dead":
                continue
            
            # Character is unused if:
            # 1. Never acted (last_acted_chapter is None)
            # 2. Only acted in introduction chapter
            acted_once_only = (
                entity.last_acted_chapter is None or
                entity.last_acted_chapter == entity.first_seen_chapter
            )
            
            # Only flag if in LATENT or FROZEN state (not actively participating)
            if acted_once_only and entity.lifecycle_state in (LifecycleState.LATENT, LifecycleState.FROZEN):
                unused.append(LooseEnd(
                    loose_end_type="unused_entity",
                    entity_id=entity.canonical_id,
                    entity_type="character",
                    introduced_chapter=entity.first_seen_chapter,
                    introduced_event=None,
                    last_referenced_chapter=entity.last_seen_chapter,
                    expected_resolution="Character introduced but never used in story",
                    aliases=list(entity.aliases),
                ))
        
        return unused
    
    def detect_unresolved_items_from_registry(self) -> List[LooseEnd]:
        """
        Detect unresolved items (Chekhov violations) from ItemTracker.
        
        Phase 8.5: Items that remained LATENT (never promoted to CAUSAL)
        are Chekhov's Gun violations.
        
        This operates on final ItemTracker state only.
        No historical snapshots required.
        
        Also populates chapter_violations for backwards compatibility.
        """
        if not self.item_tracker:
            return []
        
        unresolved = []
        
        # Get Chekhov candidates (latent items never used)
        for item in self.item_tracker.get_chekhov_candidates():
            unresolved.append(LooseEnd(
                loose_end_type="chekhov_latent",
                entity_id=item.item_id,
                entity_type="item",
                introduced_chapter=item.introduced_chapter,
                introduced_event=None,
                last_referenced_chapter=item.last_mentioned_chapter,
                expected_resolution=f"Latent item '{item.item_id}' was introduced but never used",
                item_relevance=item.relevance.value,
                item_lifecycle=item.lifecycle_state.value,
                item_original_relevance=item.original_relevance.value,
            ))
            
            # Also add to chapter_violations for backwards compatibility
            intro_chapter = item.introduced_chapter
            if intro_chapter not in self.chapter_violations:
                self.chapter_violations[intro_chapter] = []
            
            self.chapter_violations[intro_chapter].append({
                "category": "causality",
                "type": "chekhov_gun",
                "rule": "items_chekhov_gun",
                "entity": item.item_id,
                "entity_type": "item",
                "detail": f"Latent item '{item.item_id}' introduced in chapter {intro_chapter} but never used",
                "severity": "soft",
                "introduced_chapter": intro_chapter,
                "last_mentioned_chapter": item.last_mentioned_chapter,
                "item_relevance": item.relevance.value,
                "item_lifecycle": item.lifecycle_state.value,
                "item_original_relevance": item.original_relevance.value,
            })
        
        return unresolved
    
    def detect_dangling_relationships(self) -> List[LooseEnd]:
        """
        Detect dangling relationships from StateManager.
        
        Phase 8.5: Relationships where one party is FROZEN or dead
        but the relationship persists are flagged.
        
        This operates on final WorldState + EntityRegistry only.
        No historical snapshots required.
        """
        from .entity_registry import LifecycleState
        
        dangling = []
        registry = self.state_manager.entity_registry
        
        for (char1, char2), rel_type in self.state_manager.persistent_relationships.items():
            entity1 = registry.get_entity(char1)
            entity2 = registry.get_entity(char2)
            
            # Check if either party is problematic
            issues = []
            
            if entity1:
                if entity1.state == "dead":
                    issues.append(f"{char1} is dead")
                elif entity1.lifecycle_state == LifecycleState.FROZEN:
                    issues.append(f"{char1} is FROZEN (inactive for 10+ chapters)")
            else:
                issues.append(f"{char1} not in registry")
            
            if entity2:
                if entity2.state == "dead":
                    issues.append(f"{char2} is dead")
                elif entity2.lifecycle_state == LifecycleState.FROZEN:
                    issues.append(f"{char2} is FROZEN (inactive for 10+ chapters)")
            else:
                issues.append(f"{char2} not in registry")
            
            if issues:
                # Determine introduced chapter from earliest entity
                intro_chapter = 0
                if entity1:
                    intro_chapter = entity1.first_seen_chapter
                if entity2 and entity2.first_seen_chapter < intro_chapter:
                    intro_chapter = entity2.first_seen_chapter
                
                dangling.append(LooseEnd(
                    loose_end_type="dangling_relationship",
                    entity_id=f"{char1}->{char2}",
                    entity_type="relationship",
                    introduced_chapter=intro_chapter,
                    introduced_event=None,
                    last_referenced_chapter=None,
                    expected_resolution=f"Relationship '{rel_type}' between {char1} and {char2}: {'; '.join(issues)}",
                ))
        
        return dangling
    
    def analyze_from_lifecycle(self, story_id: str, total_chapters: int) -> FinalAnalysisResult:
        """
        Perform final analysis using only lifecycle states.
        
        Phase 8.5: This is the preferred analysis method.
        Operates ONLY on:
            - Final WorldState (not historical snapshots)
            - EntityRegistry lifecycle states
            - ItemTracker final state
            - Persistent relationships
        
        Does NOT:
            - Re-run ASP
            - Access historical WorldState snapshots
            - Require chapter-by-chapter tracking data
        
        Args:
            story_id: Story identifier
            total_chapters: Total number of chapters processed
            
        Returns:
            FinalAnalysisResult with all detected issues
        """
        from datetime import datetime
        
        result = FinalAnalysisResult(
            story_id=story_id,
            total_chapters=total_chapters,
            total_events=self.total_events,  # From chapter recordings if available
            total_violations=sum(len(v) for v in self.chapter_violations.values()),
            timestamp=datetime.now().isoformat(),
        )
        
        # Perform rule audit (uses RuleRegistry, no snapshots)
        self._audit_rules(result)
        
        # Detect loose ends using lifecycle-based methods
        # These operate on final state only
        unused_chars = self.detect_unused_characters_from_registry()
        unresolved_items = self.detect_unresolved_items_from_registry()
        dangling_rels = self.detect_dangling_relationships()
        
        result.loose_ends.extend(unused_chars)
        result.loose_ends.extend(unresolved_items)
        result.loose_ends.extend(dangling_rels)
        
        # Also include Chekhov from persistent context if available
        if self._persistent_context:
            context_chekhov = self.detect_chekhov_from_persistent_context()
            # Avoid duplicates by checking entity_id
            existing_ids = {le.entity_id for le in result.loose_ends}
            for le in context_chekhov:
                if le.entity_id not in existing_ids:
                    result.loose_ends.append(le)
        
        # Compute statistics from registry
        self._compute_statistics_from_registry(result)
        
        return result
    
    def _compute_statistics_from_registry(self, result: FinalAnalysisResult) -> None:
        """
        Compute statistics from EntityRegistry.
        
        Phase 8.5: Uses registry data instead of entity_introductions dict.
        """
        registry = self.state_manager.entity_registry
        
        # Count entities by type
        result.entities_introduced = {
            "character": len(registry.get_all_characters()),
            "location": len(registry.get_all_locations()),
            "item": len(registry.get_all_items()),
        }
        
        # Count resolved (dead characters, destroyed items)
        result.entities_resolved = {
            "character": len(registry.get_dead_characters()),
            "item": 0,
        }
        
        if self.item_tracker:
            # Count destroyed/discarded items
            from .item_tracker import ItemLifecycleState
            destroyed = sum(
                1 for item in self.item_tracker._items.values()
                if item.lifecycle_state in (ItemLifecycleState.DESTROYED, ItemLifecycleState.DISCARDED)
            )
            result.entities_resolved["item"] = destroyed
    
    def reset(self) -> None:
        """Reset analyzer for a new story."""
        self.entity_introductions.clear()
        self.entity_references.clear()
        self.entity_resolutions.clear()
        self.rule_usage.clear()
        self.chapter_violations.clear()
        self.total_events = 0
        self._persistent_context = None
