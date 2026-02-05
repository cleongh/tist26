"""
Relationship Manager Configuration - Debug settings for relationship filtering.
"""

from typing import Dict

# Debug flag for relationship filtering validation.
# When disabled (default), no debug code is executed.
_DEBUG_RELATIONSHIP: bool = False

# Per-chapter statistics for relationship filtering
_debug_chapter_stats: Dict[int, Dict[str, int]] = {}
