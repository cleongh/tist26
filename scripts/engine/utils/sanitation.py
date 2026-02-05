"""
Sanitation utilities for ASP atom identifiers.

Provides functions to sanitize strings for use as ASP (Answer Set Programming) atoms.
"""

import re
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..aliases import AliasResolver


def sanitize_id(value: Any) -> str:
    """
    Sanitize a value for use as an ASP atom.
    
    Args:
        value: The value to sanitize (will be converted to string)
        
    Returns:
        A sanitized string safe for use as an ASP atom identifier.
        Returns "unknown" if input is empty/None.
    """
    if not value:
        return "unknown"
    s = str(value).lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if s and s[0].isdigit():
        s = 'n' + s
    return s or "unknown"


def sanitize_character_id(
    value: Any,
    alias_resolver: Optional['AliasResolver'] = None,
) -> str:
    """
    Sanitize and normalize a character ID.
    
    First sanitizes the value for ASP, then normalizes it using
    the alias resolver if available.
    
    Args:
        value: The character ID to sanitize
        alias_resolver: Optional AliasResolver for canonical ID resolution
        
    Returns:
        A sanitized and normalized character ID
    """
    # Import here to avoid circular imports
    from ..aliases import normalize_character_id
    
    s = sanitize_id(value)
    if s and s != "unknown":
        # Use AliasResolver if available, else fall back to legacy
        s = normalize_character_id(s, alias_resolver)
    return s
