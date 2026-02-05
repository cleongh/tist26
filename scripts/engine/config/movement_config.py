"""
Movement Configuration - Constants for movement event detection.

Contains explicit movement types used to detect location transitions.
"""

from typing import Set


# Movement event types that explicitly indicate location change
EXPLICIT_MOVEMENT_TYPES: Set[str] = {
    # Primary movement types
    'leave', 'exit', 'depart', 'travel', 'move', 'go',
    'enter', 'arrive', 'return',
    # Locomotion types
    'walk', 'run', 'fly', 'drive', 'ride', 'swim',
    # Magical movement
    'apparate', 'teleport', 'portal',
    # Escape/pursuit
    'escape', 'flee', 'chase',
    # Vertical movement
    'climb', 'descend', 'jump', 'land', 'fall',
}
