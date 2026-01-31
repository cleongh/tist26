"""
Item Tracker - Item Lifecycle Management & Filtering

Responsibilities:
    - Track item lifecycle states (introduced, carried, used, discarded)
    - Filter items based on relevance (causal vs latent)
    - Suppress background items with no narrative significance
    - Maintain item->event references for Chekhov's Gun detection

Per LOGIC_DESIGN.md Section 3.2 (Relations):
    - carries(Character, Item, Time)
    - Item presence is derived from character presence + carrying

Per LOGIC_DESIGN.md Section 6 (Final Chapter Analysis):
    - Detect unresolved items (Chekhov's Gun violations)
    - Track introduced but unused entities

Phase 4: Item Filtering & Classification Logic
    - Trust LLM's relevance field as a hint, not a rule
    - causal items are always kept
    - latent items are kept but marked inactive
    - Background items are suppressed if no events reference them
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ItemLifecycleState(Enum):
    """
    Item lifecycle states for narrative tracking.
    
    Per LOGIC_DESIGN.md: items follow characters unless explicitly dropped.
    """
    INTRODUCED = "introduced"    # Item first mentioned
    CARRIED = "carried"          # Item being carried by a character
    USED = "used"                # Item was used in an event
    DISCARDED = "discarded"      # Item explicitly dropped/lost
    DESTROYED = "destroyed"      # Item destroyed
    GIVEN = "given"              # Item transferred to another character
    LATENT = "latent"            # Item introduced but not yet used (Chekhov tracking)


class ItemRelevance(Enum):
    """
    Item relevance classification.
    
    - CAUSAL: Item participates in events, always kept
    - LATENT: Item may become relevant later (Chekhov's Gun)
    - BACKGROUND: Scene dressing, may be suppressed
    """
    CAUSAL = "causal"
    LATENT = "latent"
    BACKGROUND = "background"


@dataclass
class TrackedItem:
    """
    Represents a tracked item with its lifecycle state.
    """
    item_id: str
    name: Optional[str] = None
    relevance: ItemRelevance = ItemRelevance.BACKGROUND
    original_relevance: ItemRelevance = ItemRelevance.BACKGROUND  # Phase 6: Track original
    lifecycle_state: ItemLifecycleState = ItemLifecycleState.INTRODUCED
    introduced_chapter: int = 0
    last_mentioned_chapter: int = 0
    promoted_to_causal_chapter: Optional[int] = None  # Phase 6: When upgraded to causal
    carrier: Optional[str] = None  # Character currently carrying the item
    event_references: List[str] = field(default_factory=list)  # Event IDs that reference this item
    suppressed: bool = False
    
    def is_active(self) -> bool:
        """Check if item is actively in play (not suppressed or destroyed)."""
        return (not self.suppressed and 
                self.lifecycle_state not in (ItemLifecycleState.DESTROYED, ItemLifecycleState.DISCARDED))
    
    def has_narrative_significance(self) -> bool:
        """Check if item has narrative significance (events reference it or causal)."""
        return (self.relevance == ItemRelevance.CAUSAL or 
                len(self.event_references) > 0 or
                self.carrier is not None)
    
    def was_promoted_from_latent(self) -> bool:
        """Check if item was promoted from latent to causal (Phase 6)."""
        return (self.original_relevance == ItemRelevance.LATENT and 
                self.relevance == ItemRelevance.CAUSAL)
    
    def remained_latent(self) -> bool:
        """Check if item remained latent (never promoted to causal) - Phase 6."""
        return (self.relevance == ItemRelevance.LATENT and 
                self.promoted_to_causal_chapter is None)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "relevance": self.relevance.value,
            "original_relevance": self.original_relevance.value,
            "lifecycle_state": self.lifecycle_state.value,
            "introduced_chapter": self.introduced_chapter,
            "last_mentioned_chapter": self.last_mentioned_chapter,
            "promoted_to_causal_chapter": self.promoted_to_causal_chapter,
            "carrier": self.carrier,
            "event_references": self.event_references,
            "suppressed": self.suppressed,
        }


# Event types that indicate item usage
ITEM_USE_EVENTS = {
    "give", "take", "use", "destroy", "drop", "discover", 
    "wield", "drink", "eat", "read", "open", "break"
}

# Event types that indicate item transfer
ITEM_TRANSFER_EVENTS = {"give", "take", "steal", "receive"}

# Event types that indicate item destruction
ITEM_DESTROY_EVENTS = {"destroy", "break", "burn", "consume"}


class ItemTracker:
    """
    Tracks item lifecycle and filters background items.
    
    Responsibilities:
        1. Trust LLM's relevance field as a hint
        2. Post-process items based on relevance
        3. Track item lifecycle across chapters
        4. Suppress background items with no narrative significance
        5. Phase 6: Auto-upgrade items to causal when they appear in events
    
    Does NOT:
        - Make narrative judgments (delegated to ASP)
        - Override explicit LLM classifications without cause
    """
    
    def __init__(self):
        # item_id -> TrackedItem
        self._items: Dict[str, TrackedItem] = {}
        
        # Statistics
        self._items_introduced: int = 0
        self._items_suppressed: int = 0
        self._items_promoted: int = 0  # background/latent -> causal
        
        # Phase 6: Track relevance transitions
        self._relevance_transitions: List[Dict[str, Any]] = []
    
    def reset(self) -> None:
        """Reset tracker to initial state."""
        self._items.clear()
        self._items_introduced = 0
        self._items_suppressed = 0
        self._items_promoted = 0
        self._relevance_transitions.clear()
    
    def process_extraction(
        self,
        extraction: Dict[str, Any],
        chapter_num: int,
    ) -> Dict[str, Any]:
        """
        Process extracted items and filter based on relevance.
        
        This is the main entry point for Phase 4 integration.
        
        1. Register all extracted items
        2. Analyze events for item references
        3. Classify items based on relevance + event references
        4. Suppress background items with no significance
        5. Return filtered extraction
        
        Args:
            extraction: The normalized extraction dict
            chapter_num: Current chapter number
            
        Returns:
            Filtered extraction with suppressed items removed
        """
        import copy
        filtered = copy.deepcopy(extraction)
        
        entities = filtered.get("entities", {})
        events = filtered.get("events", [])
        
        # Step 1: Find all item references in events
        event_item_refs = self._find_item_references_in_events(events)
        
        # Step 2: Register and classify extracted items
        items = entities.get("items", [])
        for item in items:
            item_id = self._normalize_id(item.get("id", "") or item.get("name", ""))
            if not item_id or item_id == "unknown":
                continue
            
            # Get LLM's relevance hint
            llm_relevance = item.get("relevance", "").lower()
            if llm_relevance == "causal":
                relevance = ItemRelevance.CAUSAL
            elif llm_relevance == "latent":
                relevance = ItemRelevance.LATENT
            else:
                relevance = ItemRelevance.BACKGROUND
            
            # Register or update item
            self._register_item(
                item_id=item_id,
                name=item.get("name"),
                relevance=relevance,
                chapter_num=chapter_num,
                event_refs=event_item_refs.get(item_id, []),
            )
        
        # Step 3: Check for items referenced in events but not explicitly extracted
        for item_id, event_ids in event_item_refs.items():
            if item_id not in self._items:
                # Item referenced in events but not extracted - promote to causal
                self._register_item(
                    item_id=item_id,
                    name=None,
                    relevance=ItemRelevance.CAUSAL,
                    chapter_num=chapter_num,
                    event_refs=event_ids,
                )
                self._items_promoted += 1
            else:
                # Phase 6: Item exists - update with event references to trigger promotion
                self._register_item(
                    item_id=item_id,
                    name=self._items[item_id].name,
                    relevance=self._items[item_id].relevance,
                    chapter_num=chapter_num,
                    event_refs=event_ids,
                )
        
        # Step 4: Update lifecycle states based on events
        self._update_lifecycle_from_events(events, chapter_num)
        
        # Step 5: Suppress background items with no significance
        self._apply_suppression()
        
        # Step 6: Filter extraction to remove suppressed items
        filtered_items = []
        for item in items:
            item_id = self._normalize_id(item.get("id", "") or item.get("name", ""))
            if item_id and item_id != "unknown":
                tracked = self._items.get(item_id)
                if tracked and not tracked.suppressed:
                    filtered_items.append(item)
        
        entities["items"] = filtered_items
        
        return filtered
    
    def _register_item(
        self,
        item_id: str,
        name: Optional[str],
        relevance: ItemRelevance,
        chapter_num: int,
        event_refs: List[str],
    ) -> TrackedItem:
        """Register or update an item."""
        if item_id in self._items:
            # Update existing item
            item = self._items[item_id]
            item.last_mentioned_chapter = chapter_num
            
            # Phase 6: Promote relevance if events reference it (including latent→causal)
            if event_refs and item.relevance in (ItemRelevance.BACKGROUND, ItemRelevance.LATENT):
                old_relevance = item.relevance
                item.relevance = ItemRelevance.CAUSAL
                item.promoted_to_causal_chapter = chapter_num
                self._items_promoted += 1
                
                # Log the transition
                self._relevance_transitions.append({
                    "item_id": item_id,
                    "from": old_relevance.value,
                    "to": ItemRelevance.CAUSAL.value,
                    "chapter": chapter_num,
                    "trigger_events": event_refs,
                })
                logger.info(f"Phase 6: Item '{item_id}' promoted {old_relevance.value} → causal (chapter {chapter_num})")
            
            # Add new event references
            for ref in event_refs:
                if ref not in item.event_references:
                    item.event_references.append(ref)
        else:
            # New item - track original relevance
            original_relevance = relevance
            promoted_chapter = None
            
            # Phase 6: Promote to CAUSAL if events reference it
            if event_refs and relevance in (ItemRelevance.BACKGROUND, ItemRelevance.LATENT):
                old_relevance = relevance
                relevance = ItemRelevance.CAUSAL
                promoted_chapter = chapter_num
                self._items_promoted += 1
                
                # Log the transition
                self._relevance_transitions.append({
                    "item_id": item_id,
                    "from": old_relevance.value,
                    "to": ItemRelevance.CAUSAL.value,
                    "chapter": chapter_num,
                    "trigger_events": event_refs,
                })
                logger.info(f"Phase 6: New item '{item_id}' promoted {old_relevance.value} → causal (chapter {chapter_num})")
            
            item = TrackedItem(
                item_id=item_id,
                name=name,
                relevance=relevance,
                original_relevance=original_relevance,
                lifecycle_state=ItemLifecycleState.INTRODUCED,
                introduced_chapter=chapter_num,
                last_mentioned_chapter=chapter_num,
                promoted_to_causal_chapter=promoted_chapter,
                event_references=event_refs,
            )
            self._items[item_id] = item
            self._items_introduced += 1
            
            logger.debug(f"Registered item '{item_id}' with relevance {relevance.value}")
        
        return item
    
    def _find_item_references_in_events(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        """
        Find items referenced in events.
        
        Items can be referenced as:
            - Direct object (patient) in give/take/use events
            - Named in event type (use_wand, break_window)
            - Mentioned in source_text (heuristic)
        
        Returns:
            Dict mapping item_id -> list of event_ids that reference it
        """
        item_refs: Dict[str, List[str]] = {}
        
        for event in events:
            event_id = event.get("id", "")
            event_type = event.get("type", "").lower()
            patient = event.get("patient", "")
            
            # Check if this is an item-related event type
            is_item_event = any(t in event_type for t in ITEM_USE_EVENTS)
            
            if is_item_event and patient:
                patient_id = self._normalize_id(patient)
                if patient_id and patient_id != "unknown":
                    if patient_id not in item_refs:
                        item_refs[patient_id] = []
                    if event_id not in item_refs[patient_id]:
                        item_refs[patient_id].append(event_id)
            
            # Check for "item" field in event (some extractions include this)
            item_field = event.get("item", "")
            if item_field:
                item_id = self._normalize_id(item_field)
                if item_id and item_id != "unknown":
                    if item_id not in item_refs:
                        item_refs[item_id] = []
                    if event_id not in item_refs[item_id]:
                        item_refs[item_id].append(event_id)
        
        return item_refs
    
    def _update_lifecycle_from_events(
        self,
        events: List[Dict[str, Any]],
        chapter_num: int,
    ) -> None:
        """Update item lifecycle states based on events."""
        for event in events:
            event_type = event.get("type", "").lower()
            agent = self._normalize_id(event.get("agent", ""))
            patient = self._normalize_id(event.get("patient", ""))
            
            # Give event: item transfers from agent to patient
            if event_type in ("give", "hand", "pass"):
                # Find what item was given (check patient or item field)
                item_id = self._normalize_id(event.get("item", ""))
                if item_id and item_id in self._items:
                    item = self._items[item_id]
                    item.lifecycle_state = ItemLifecycleState.GIVEN
                    item.carrier = patient if patient != "unknown" else None
            
            # Take event: agent takes item
            elif event_type in ("take", "pick_up", "grab", "receive"):
                item_id = self._normalize_id(event.get("item", patient))
                if item_id and item_id in self._items:
                    item = self._items[item_id]
                    item.lifecycle_state = ItemLifecycleState.CARRIED
                    item.carrier = agent if agent != "unknown" else None
            
            # Destroy events (check before generic use events)
            elif event_type in ITEM_DESTROY_EVENTS:
                item_id = self._normalize_id(event.get("item", patient))
                if item_id and item_id in self._items:
                    item = self._items[item_id]
                    item.lifecycle_state = ItemLifecycleState.DESTROYED
            
            # Drop/discard events
            elif event_type in ("drop", "discard", "lose", "abandon"):
                item_id = self._normalize_id(event.get("item", patient))
                if item_id and item_id in self._items:
                    item = self._items[item_id]
                    item.lifecycle_state = ItemLifecycleState.DISCARDED
                    item.carrier = None
            
            # Use event: item was used (generic catch-all)
            elif event_type in ITEM_USE_EVENTS:
                item_id = self._normalize_id(event.get("item", patient))
                if item_id and item_id in self._items:
                    item = self._items[item_id]
                    item.lifecycle_state = ItemLifecycleState.USED
    
    def _apply_suppression(self) -> None:
        """
        Suppress background items with no narrative significance.
        
        An item is suppressed if:
            1. Relevance is BACKGROUND (not causal or latent)
            2. No events reference it
            3. It's not being carried
        """
        for item_id, item in self._items.items():
            if item.suppressed:
                continue
            
            # Never suppress causal or latent items
            if item.relevance in (ItemRelevance.CAUSAL, ItemRelevance.LATENT):
                continue
            
            # Suppress if no narrative significance
            if not item.has_narrative_significance():
                item.suppressed = True
                self._items_suppressed += 1
                logger.debug(f"Suppressed background item '{item_id}'")
    
    def get_item(self, item_id: str) -> Optional[TrackedItem]:
        """Get a tracked item by ID."""
        return self._items.get(self._normalize_id(item_id))
    
    def get_active_items(self) -> List[TrackedItem]:
        """Get all active (non-suppressed) items."""
        return [item for item in self._items.values() if item.is_active()]
    
    def get_latent_items(self) -> List[TrackedItem]:
        """Get items marked as latent (for Chekhov tracking)."""
        return [
            item for item in self._items.values() 
            if item.relevance == ItemRelevance.LATENT and item.is_active()
        ]
    
    def get_carried_items(self, character_id: str) -> List[TrackedItem]:
        """Get items currently carried by a character."""
        char_id = self._normalize_id(character_id)
        return [
            item for item in self._items.values() 
            if item.carrier == char_id and item.is_active()
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        return {
            "total_items": len(self._items),
            "active_items": len(self.get_active_items()),
            "suppressed_items": self._items_suppressed,
            "promoted_items": self._items_promoted,
            "causal_items": sum(1 for i in self._items.values() if i.relevance == ItemRelevance.CAUSAL),
            "latent_items": sum(1 for i in self._items.values() if i.relevance == ItemRelevance.LATENT),
            "background_items": sum(1 for i in self._items.values() if i.relevance == ItemRelevance.BACKGROUND),
            "relevance_transitions": len(self._relevance_transitions),
        }
    
    def get_relevance_transitions(self) -> List[Dict[str, Any]]:
        """
        Get log of all relevance transitions (Phase 6).
        
        Returns list of dicts with:
            - item_id: str
            - from: str (original relevance)
            - to: str (new relevance)
            - chapter: int
            - trigger_events: List[str]
        """
        return list(self._relevance_transitions)
    
    def get_chekhov_candidates(self) -> List[TrackedItem]:
        """
        Get items that are Chekhov's Gun violations.
        
        Phase 6: These are items that:
            1. Were originally introduced as latent
            2. NEVER got promoted to causal (never appeared in events)
            3. Are still active (not suppressed/destroyed)
        
        This excludes items that appeared in events (and thus were promoted).
        """
        return [
            item for item in self._items.values()
            if item.remained_latent() and item.is_active()
        ]
    
    def get_promoted_latent_items(self) -> List[TrackedItem]:
        """
        Get items that were promoted from latent to causal (Phase 6).
        
        These are NOT Chekhov violations - they fulfilled their narrative purpose.
        """
        return [
            item for item in self._items.values()
            if item.was_promoted_from_latent()
        ]
    
    def format_known_items_with_states(self) -> str:
        """
        Format known items with their states for injection into the extraction prompt.
        
        Returns a compact, deterministic string with one item per line in the format:
            - item_id (lifecycle_state)
        
        If no items are known yet, returns a placeholder message.
        
        Per LOGIC_DESIGN.md Section 3.2: item(X) is a core entity type that
        should be tracked across chapters.
        """
        # Get all non-suppressed items, sorted for determinism
        active_items = sorted(
            [item for item in self._items.values() if not item.suppressed],
            key=lambda x: x.item_id
        )
        
        if not active_items:
            return "(No items established yet)"
        
        lines = []
        for item in active_items:
            # Format: - item_id (lifecycle_state)
            state = item.lifecycle_state.value
            lines.append(f"- {item.item_id} ({state})")
        
        return "\n".join(lines)
    
    def to_asp_facts(self) -> List[str]:
        """Generate ASP facts for tracked items."""
        facts = []
        
        for item in self._items.values():
            if item.suppressed:
                continue
            
            # Item existence
            facts.append(f"item({item.item_id}).")
            
            # Relevance
            facts.append(f"item_relevance({item.item_id}, {item.relevance.value}).")
            
            # Lifecycle state
            facts.append(f"item_lifecycle({item.item_id}, {item.lifecycle_state.value}).")
            
            # Carrier
            if item.carrier:
                facts.append(f"carries({item.carrier}, {item.item_id}).")
            
            # Latent marker for Chekhov tracking
            if item.relevance == ItemRelevance.LATENT:
                facts.append(f"latent_item({item.item_id}).")
        
        return facts
    
    @staticmethod
    def _normalize_id(value: Any) -> str:
        """Normalize an identifier."""
        import re
        if not value:
            return "unknown"
        s = str(value).lower()
        s = re.sub(r'[^a-z0-9_]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        return s or "unknown"
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"ItemTracker(total={stats['total_items']}, "
            f"active={stats['active_items']}, "
            f"suppressed={stats['suppressed_items']})"
        )
