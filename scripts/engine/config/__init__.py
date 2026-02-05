"""
Configuration module for the engine.

Contains configuration constants and settings.
"""

from .entity_registry_config import ACTIVE_THRESHOLD, LATENT_THRESHOLD
from .item_tracker_config import (
    ITEM_USE_EVENTS,
    ITEM_TRANSFER_EVENTS,
    ITEM_DESTROY_EVENTS,
)
from .movement_config import EXPLICIT_MOVEMENT_TYPES
from .relationship_manager_config import _DEBUG_RELATIONSHIP, _debug_chapter_stats
from .asp_diagnostics_config import _DIAGNOSTICS_ENABLED, _global_collector
from .rule_manager_config import ENTITY_PATTERNS, RESERVED_WORDS

__all__ = [
    "ACTIVE_THRESHOLD",
    "LATENT_THRESHOLD",
    "ITEM_USE_EVENTS",
    "ITEM_TRANSFER_EVENTS",
    "ITEM_DESTROY_EVENTS",
    "EXPLICIT_MOVEMENT_TYPES",
    "_DEBUG_RELATIONSHIP",
    "_debug_chapter_stats",
    "_DIAGNOSTICS_ENABLED",
    "_global_collector",
    "ENTITY_PATTERNS",
    "RESERVED_WORDS",
]
