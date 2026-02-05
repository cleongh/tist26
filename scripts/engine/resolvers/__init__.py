"""
Resolvers Module - Conflict, Alias, and Movement Resolution

This module provides classes for resolving conflicts between rule layers,
maintaining canonical entity identities, and detecting implicit movement.

Classes:
    - ConflictResolver: Handles rule overrides and deactivation
    - AliasResolver: Core canonical identity and alias resolution
    - MovementResolver: Detects and bridges implicit movement gaps
"""

from .conflict_resolver import ConflictResolver
from .alias_resolver import AliasResolver
from .movement_resolver import MovementResolver

__all__ = [
    "ConflictResolver",
    "AliasResolver",
    "MovementResolver",
]
