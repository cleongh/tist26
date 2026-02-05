"""
Item Tracker Configuration Constants.

Contains event type sets for item tracking.
"""

from typing import Set

# Event types that indicate item usage
ITEM_USE_EVENTS: Set[str] = {
    "give", "take", "use", "destroy", "drop", "discover", 
    "wield", "drink", "eat", "read", "open", "break"
}

# Event types that indicate item transfer
ITEM_TRANSFER_EVENTS: Set[str] = {"give", "take", "steal", "receive"}

# Event types that indicate item destruction
ITEM_DESTROY_EVENTS: Set[str] = {"destroy", "break", "burn", "consume"}
