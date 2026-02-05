"""
Entity Registry Configuration - Lifecycle threshold constants.

These constants define the lifecycle state transitions for entities.
"""

# Entity is ACTIVE if acted within last N chapters
ACTIVE_THRESHOLD = 3

# Entity is LATENT if inactive for N to (FROZEN-1) chapters
# Entity becomes FROZEN if inactive for ≥LATENT_THRESHOLD chapters
LATENT_THRESHOLD = 10
