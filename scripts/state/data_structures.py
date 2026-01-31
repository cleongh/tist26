"""
Data structures for experiment results.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List


@dataclass
class ChapterError:
    """An error detected in a specific chapter."""
    chapter_file: str
    category: str
    error_type: str
    description: str
    story_fragment: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ChapterResult:
    """Result of evaluating a single chapter."""
    story_name: str
    variant: str  # "original" or "modified"
    chapter_file: str
    chapter_number: int
    errors: List[ChapterError] = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "story_name": self.story_name,
            "variant": self.variant,
            "chapter_file": self.chapter_file,
            "chapter_number": self.chapter_number,
            "error_count": len(self.errors),
            "errors": [e.to_dict() for e in self.errors],
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass 
class StepResults:
    """Results from one step of the experiment."""
    step: int
    approach: str  # "llm" or "logic"
    timestamp: str
    chapters_processed: int = 0
    total_errors: int = 0
    results: List[ChapterResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "step": self.step,
            "approach": self.approach,
            "timestamp": self.timestamp,
            "chapters_processed": self.chapters_processed,
            "total_errors": self.total_errors,
            "results": [r.to_dict() for r in self.results],
        }
