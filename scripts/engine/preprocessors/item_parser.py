"""
Item Parser - Process Extracted Items and Filter Based on Relevance

Responsibilities:
    - Parse extracted items from LLM output
    - Find item references in events
    - Classify items based on relevance + event references
    - Update lifecycle states based on events
    - Suppress background items with no significance

This is the main entry point for Phase 4 integration.
"""

import copy
import logging
from typing import Dict, List, Any, TYPE_CHECKING

from ..domain import ItemLifecycleState, ItemRelevance, TrackedItem
from ..config import ITEM_USE_EVENTS, ITEM_DESTROY_EVENTS
from ..utils import sanitize_id

if TYPE_CHECKING:
    from ..item_tracker import ItemTracker

logger = logging.getLogger(__name__)


class ItemParser:
    """
    Parses extracted items and filters based on relevance.
    
    Works with ItemTracker to:
        1. Register all extracted items
        2. Analyze events for item references
        3. Classify items based on relevance + event references
        4. Suppress background items with no significance
        5. Return filtered extraction
    """
    
    def __init__(self, item_tracker: 'ItemTracker'):
        """
        Initialize the ItemParser.
        
        Args:
            item_tracker: The ItemTracker to register items with
        """
        self._item_tracker = item_tracker
    
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
        filtered = copy.deepcopy(extraction)
        
        entities = filtered.get("entities", {})
        events = filtered.get("events", [])
        
        # Step 1: Find all item references in events
        event_item_refs = self._find_item_references_in_events(events)
        
        # Step 2: Register and classify extracted items
        items = entities.get("items", [])
        self._register_extracted_items(items, chapter_num, event_item_refs)
        
        # Step 3: Check for items referenced in events but not explicitly extracted
        self._register_event_referenced_items(event_item_refs, chapter_num)
        
        # Step 4: Update lifecycle states based on events
        self._update_lifecycle_from_events(events, chapter_num)
        
        # Step 5: Suppress background items with no significance
        self._item_tracker._apply_suppression()
        
        # Step 6: Filter extraction to remove suppressed items
        filtered_items = self._filter_suppressed_items(items)
        entities["items"] = filtered_items
        
        return filtered
    
    def _register_extracted_items(
        self,
        items: List[Dict[str, Any]],
        chapter_num: int,
        event_item_refs: Dict[str, List[str]],
    ) -> None:
        """Register and classify extracted items."""
        for item in items:
            item_id = sanitize_id(item.get("id", "") or item.get("name", ""))
            if not item_id or item_id == "unknown":
                continue
            
            # Get LLM's relevance hint
            relevance = self._parse_relevance(item.get("relevance", ""))
            
            # Register or update item
            self._item_tracker._register_item(
                item_id=item_id,
                name=item.get("name"),
                relevance=relevance,
                chapter_num=chapter_num,
                event_refs=event_item_refs.get(item_id, []),
            )
    
    def _register_event_referenced_items(
        self,
        event_item_refs: Dict[str, List[str]],
        chapter_num: int,
    ) -> None:
        """Register items referenced in events but not explicitly extracted."""
        for item_id, event_ids in event_item_refs.items():
            if item_id not in self._item_tracker._items:
                # Item referenced in events but not extracted - promote to causal
                self._item_tracker._register_item(
                    item_id=item_id,
                    name=None,
                    relevance=ItemRelevance.CAUSAL,
                    chapter_num=chapter_num,
                    event_refs=event_ids,
                )
                self._item_tracker._items_promoted += 1
            else:
                # Phase 6: Item exists - update with event references to trigger promotion
                existing_item = self._item_tracker._items[item_id]
                self._item_tracker._register_item(
                    item_id=item_id,
                    name=existing_item.name,
                    relevance=existing_item.relevance,
                    chapter_num=chapter_num,
                    event_refs=event_ids,
                )
    
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
                patient_id = sanitize_id(patient)
                if patient_id and patient_id != "unknown":
                    self._add_item_ref(item_refs, patient_id, event_id)
            
            # Check for "item" field in event (some extractions include this)
            item_field = event.get("item", "")
            if item_field:
                item_id = sanitize_id(item_field)
                if item_id and item_id != "unknown":
                    self._add_item_ref(item_refs, item_id, event_id)
        
        return item_refs
    
    def _add_item_ref(
        self,
        item_refs: Dict[str, List[str]],
        item_id: str,
        event_id: str,
    ) -> None:
        """Add an item reference to the refs dict."""
        if item_id not in item_refs:
            item_refs[item_id] = []
        if event_id not in item_refs[item_id]:
            item_refs[item_id].append(event_id)
    
    def _update_lifecycle_from_events(
        self,
        events: List[Dict[str, Any]],
        chapter_num: int,
    ) -> None:
        """Update item lifecycle states based on events."""
        for event in events:
            event_type = event.get("type", "").lower()
            agent = sanitize_id(event.get("agent", ""))
            patient = sanitize_id(event.get("patient", ""))
            
            self._process_event_lifecycle(event, event_type, agent, patient)
    
    def _process_event_lifecycle(
        self,
        event: Dict[str, Any],
        event_type: str,
        agent: str,
        patient: str,
    ) -> None:
        """Process a single event for lifecycle updates."""
        items = self._item_tracker._items
        
        # Give event: item transfers from agent to patient
        if event_type in ("give", "hand", "pass"):
            item_id = sanitize_id(event.get("item", ""))
            if item_id and item_id in items:
                item = items[item_id]
                item.lifecycle_state = ItemLifecycleState.GIVEN
                item.carrier = patient if patient != "unknown" else None
        
        # Take event: agent takes item
        elif event_type in ("take", "pick_up", "grab", "receive"):
            item_id = sanitize_id(event.get("item", patient))
            if item_id and item_id in items:
                item = items[item_id]
                item.lifecycle_state = ItemLifecycleState.CARRIED
                item.carrier = agent if agent != "unknown" else None
        
        # Destroy events (check before generic use events)
        elif event_type in ITEM_DESTROY_EVENTS:
            item_id = sanitize_id(event.get("item", patient))
            if item_id and item_id in items:
                item = items[item_id]
                item.lifecycle_state = ItemLifecycleState.DESTROYED
        
        # Drop/discard events
        elif event_type in ("drop", "discard", "lose", "abandon"):
            item_id = sanitize_id(event.get("item", patient))
            if item_id and item_id in items:
                item = items[item_id]
                item.lifecycle_state = ItemLifecycleState.DISCARDED
                item.carrier = None
        
        # Use event: item was used (generic catch-all)
        elif event_type in ITEM_USE_EVENTS:
            item_id = sanitize_id(event.get("item", patient))
            if item_id and item_id in items:
                item = items[item_id]
                item.lifecycle_state = ItemLifecycleState.USED
    
    def _filter_suppressed_items(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter extraction to remove suppressed items."""
        filtered_items = []
        for item in items:
            item_id = sanitize_id(item.get("id", "") or item.get("name", ""))
            if item_id and item_id != "unknown":
                tracked = self._item_tracker._items.get(item_id)
                if tracked and not tracked.suppressed:
                    filtered_items.append(item)
        return filtered_items
    
    def _parse_relevance(self, llm_relevance: str) -> ItemRelevance:
        """Parse LLM relevance hint into ItemRelevance enum."""
        llm_relevance = llm_relevance.lower() if llm_relevance else ""
        if llm_relevance == "causal":
            return ItemRelevance.CAUSAL
        elif llm_relevance == "latent":
            return ItemRelevance.LATENT
        return ItemRelevance.BACKGROUND
