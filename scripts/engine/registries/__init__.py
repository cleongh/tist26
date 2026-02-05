"""
Registries Module - Entity, Lifecycle, and Rule Storage

This module provides classes for managing entities, their lifecycle
states, and rules across chapters in the narrative logic engine.

Classes:
    - EntityRegistry: Canonical entity storage
    - LifecycleRegistry: Entity lifecycle state management
    - RuleRegistry: Rule loading, priorities, activation
"""

from .entity_registry import EntityRegistry
from .lifecycle_registry import LifecycleRegistry
from .rule_registry import RuleRegistry

__all__ = [
    "EntityRegistry",
    "LifecycleRegistry",
    "RuleRegistry",
]
