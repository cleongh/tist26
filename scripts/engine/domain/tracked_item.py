"""
Tracked Item Dataclass.

Represents a tracked item with its lifecycle state.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .item_lifecycle_state import ItemLifecycleState
from .item_relevance import ItemRelevance


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
