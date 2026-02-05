"""
Learned Rule Dataclass.

Represents a rule learned via ILASP.
"""

from dataclasses import dataclass


@dataclass
class LearnedRule:
    """
    A rule learned via ILASP.
    """
    id: str
    content: str
    story_id: str
    chapter: int
    version: int
    source_task_id: str
    confidence: float = 1.0
    timestamp: str = ""
