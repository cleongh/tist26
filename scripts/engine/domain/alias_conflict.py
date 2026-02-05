"""
Alias Conflict - Records when an alias maps to multiple canonical IDs

Per LOGIC_DESIGN.md: conflicts are now RESOLVED (unified) rather than
left unresolved. The chosen_canonical field indicates which ID was kept.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Any, Optional


@dataclass
class AliasConflict:
    """
    Records when an alias maps to multiple canonical IDs.
    
    Per LOGIC_DESIGN.md: conflicts are now RESOLVED (unified) rather than
    left unresolved. The chosen_canonical field indicates which ID was kept.
    """
    alias: str
    canonical_ids: Set[str]
    first_seen_chapter: int
    conflict_chapter: int
    # Resolution info (populated after unification)
    chosen_canonical: Optional[str] = None
    absorbed_canonical: Optional[str] = None
    resolution_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "alias": self.alias,
            "canonical_ids": list(self.canonical_ids),
            "first_seen_chapter": self.first_seen_chapter,
            "conflict_chapter": self.conflict_chapter,
        }
        if self.chosen_canonical:
            result["chosen_canonical"] = self.chosen_canonical
        if self.absorbed_canonical:
            result["absorbed_canonical"] = self.absorbed_canonical
        if self.resolution_reason:
            result["resolution_reason"] = self.resolution_reason
        return result
