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

from typing import Dict, List, Optional, Any, TYPE_CHECKING
import logging

from .domain import ItemLifecycleState, ItemRelevance, TrackedItem
from .utils import sanitize_id

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult
    from .preprocessors import AspConverter


def _get_asp_converter() -> 'AspConverter':
    """Lazy import to avoid circular dependency."""
    from .preprocessors import AspConverter
    return AspConverter()


logger = logging.getLogger(__name__)


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
            return self._update_existing_item(item_id, chapter_num, event_refs)
        return self._create_new_item(item_id, name, relevance, chapter_num, event_refs)
    
    def _update_existing_item(
        self,
        item_id: str,
        chapter_num: int,
        event_refs: List[str],
    ) -> TrackedItem:
        """Update an existing item with new information."""
        item = self._items[item_id]
        item.last_mentioned_chapter = chapter_num
        
        # Phase 6: Promote relevance if events reference it (including latent→causal)
        if event_refs and item.relevance in (ItemRelevance.BACKGROUND, ItemRelevance.LATENT):
            self._promote_item_to_causal(item, chapter_num, event_refs)
        
        # Add new event references
        for ref in event_refs:
            if ref not in item.event_references:
                item.event_references.append(ref)
        
        return item
    
    def _create_new_item(
        self,
        item_id: str,
        name: Optional[str],
        relevance: ItemRelevance,
        chapter_num: int,
        event_refs: List[str],
    ) -> TrackedItem:
        """Create and register a new item."""
        original_relevance = relevance
        promoted_chapter = None
        
        # Phase 6: Promote to CAUSAL if events reference it
        if event_refs and relevance in (ItemRelevance.BACKGROUND, ItemRelevance.LATENT):
            old_relevance = relevance
            relevance = ItemRelevance.CAUSAL
            promoted_chapter = chapter_num
            self._items_promoted += 1
            self._log_relevance_transition(item_id, old_relevance, chapter_num, event_refs)
        
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
    
    def _promote_item_to_causal(
        self,
        item: TrackedItem,
        chapter_num: int,
        event_refs: List[str],
    ) -> None:
        """Promote an item from background/latent to causal."""
        old_relevance = item.relevance
        item.relevance = ItemRelevance.CAUSAL
        item.promoted_to_causal_chapter = chapter_num
        self._items_promoted += 1
        self._log_relevance_transition(item.item_id, old_relevance, chapter_num, event_refs)
    
    def _log_relevance_transition(
        self,
        item_id: str,
        old_relevance: ItemRelevance,
        chapter_num: int,
        event_refs: List[str],
    ) -> None:
        """Log a relevance transition for tracking."""
        self._relevance_transitions.append({
            "item_id": item_id,
            "from": old_relevance.value,
            "to": ItemRelevance.CAUSAL.value,
            "chapter": chapter_num,
            "trigger_events": event_refs,
        })
        logger.info(f"Phase 6: Item '{item_id}' promoted {old_relevance.value} → causal (chapter {chapter_num})")
    
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
        return self._items.get(sanitize_id(item_id))
    
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
        char_id = sanitize_id(character_id)
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
    
    def to_asp_facts(
        self,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> List[str]:
        """
        Generate ASP facts for tracked items.
        
        Phase 8.6: If active_universe is provided, only facts for items
        in that universe are included.
        
        Args:
            active_universe: Optional filter - only include items in this universe.
        """
        asp_converter = _get_asp_converter()
        return asp_converter.tracked_items_to_asp(self._items, active_universe)
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"ItemTracker(total={stats['total_items']}, "
            f"active={stats['active_items']}, "
            f"suppressed={stats['suppressed_items']})"
        )
