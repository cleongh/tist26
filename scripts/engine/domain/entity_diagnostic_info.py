"""
EntityDiagnosticInfo - Enhanced entity information for diagnostics.

Phase 7: Enhanced diagnostics with canonical IDs, aliases, item lifecycle.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EntityDiagnosticInfo:
    """
    Phase 7: Enhanced entity information for diagnostics.
    
    Ensures all reported issues reference:
        - Canonical IDs only
        - Aliases (if relevant)
        - Item relevance and lifecycle (for items)
    """
    canonical_id: str
    entity_type: str  # "character", "item", "location"
    aliases: List[str] = field(default_factory=list)
    # Item-specific fields (Phase 7)
    item_relevance: Optional[str] = None  # "causal", "latent", "background"
    item_lifecycle: Optional[str] = None  # "introduced", "carried", "used", "destroyed", etc.
    item_carrier: Optional[str] = None  # Character carrying the item
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "canonical_id": self.canonical_id,
            "entity_type": self.entity_type,
        }
        if self.aliases:
            result["aliases"] = self.aliases
        if self.item_relevance:
            result["relevance"] = self.item_relevance
        if self.item_lifecycle:
            result["lifecycle"] = self.item_lifecycle
        if self.item_carrier:
            result["carrier"] = self.item_carrier
        return result
