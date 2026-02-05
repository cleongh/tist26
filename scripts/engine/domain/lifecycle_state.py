"""
Lifecycle State - Entity lifecycle states for memory optimization.

Lifecycle rules (deterministic):
    - ACTIVE: Entity acted within last 3 chapters
    - LATENT: Inactive for 3-9 chapters
    - FROZEN: Inactive for ≥10 chapters

Only ACTIVE entities participate in logic (WorldState/ASP).
LATENT and FROZEN entities remain in registry for future reactivation.
"""

from enum import Enum


class LifecycleState(Enum):
    """
    Entity lifecycle states for memory optimization.
    
    Lifecycle rules (deterministic):
        - ACTIVE: Entity acted within last 3 chapters
        - LATENT: Inactive for 3-9 chapters  
        - FROZEN: Inactive for ≥10 chapters
    
    Only ACTIVE entities participate in logic (WorldState/ASP).
    LATENT and FROZEN entities remain in registry for future reactivation.
    """
    ACTIVE = "active"
    LATENT = "latent"
    FROZEN = "frozen"
