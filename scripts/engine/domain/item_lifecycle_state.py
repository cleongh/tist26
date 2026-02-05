"""
Item Lifecycle State Enum.

Tracks the lifecycle state of items in the narrative.
"""

from enum import Enum


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
