"""
Item Relevance Enum.

Classifies item relevance for narrative tracking.
"""

from enum import Enum


class ItemRelevance(Enum):
    """
    Item relevance classification.
    
    - CAUSAL: Item participates in events, always kept
    - LATENT: Item may become relevant later (Chekhov's Gun)
    - BACKGROUND: Scene dressing, may be suppressed
    """
    CAUSAL = "causal"
    LATENT = "latent"
    BACKGROUND = "background"
