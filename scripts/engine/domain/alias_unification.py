"""
Alias Unification - Records when two canonical IDs are unified

Per LOGIC_DESIGN.md: Deterministic and explainable - every conclusion
must trace back to rules. Unifications are logged with full provenance.
"""

from dataclasses import dataclass
from typing import Dict, Set, Any

from .unification_reason import UnificationReason


@dataclass
class AliasUnification:
    """
    Records when two canonical IDs are unified into one.
    
    Per LOGIC_DESIGN.md: Deterministic and explainable - every conclusion
    must trace back to rules. Unifications are logged with full provenance.
    """
    absorbed_canonical: str       # The canonical ID that was absorbed/retired
    surviving_canonical: str      # The canonical ID that remains active
    shared_alias: str             # The alias that triggered the unification
    absorbed_aliases: Set[str]    # All aliases that were migrated
    chapter: int                  # Chapter where unification occurred
    reason: UnificationReason
    entity_type: str              # "character" or "location"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "absorbed_canonical": self.absorbed_canonical,
            "surviving_canonical": self.surviving_canonical,
            "shared_alias": self.shared_alias,
            "absorbed_aliases": list(self.absorbed_aliases),
            "chapter": self.chapter,
            "reason": self.reason.value,
            "entity_type": self.entity_type,
        }
