"""
Learning Task Dataclass.

Represents an ILASP learning task for rule induction.
"""

from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ..preprocessors import AspConverter


@dataclass
class LearningTask:
    """
    Represents an ILASP learning task.
    
    Contains:
        - Background knowledge (existing rules and facts)
        - Positive examples (patterns that SHOULD trigger violations)
        - Negative examples (patterns that should NOT trigger violations)
        - Mode declarations (hypothesis space)
    """
    id: str
    background_knowledge: str
    positive_examples: List[str]
    negative_examples: List[str]
    mode_declarations: str = ""
    story_id: str = ""
    chapter: int = 0
    
    def to_ilasp_format(self, asp_converter: 'AspConverter' = None) -> str:
        """
        Convert to ILASP task file format.
        
        Args:
            asp_converter: Optional AspConverter instance
        """
        if asp_converter is None:
            from ..preprocessors import AspConverter
            asp_converter = AspConverter()
        
        lines = [
            f"% ILASP Learning Task: {self.id}",
            f"% Story: {self.story_id}, Chapter: {self.chapter}",
            f"% Generated: {datetime.now().isoformat()}",
            "",
        ]
        
        # Mode declarations
        if self.mode_declarations:
            lines.append("% === MODE DECLARATIONS ===")
            lines.append(self.mode_declarations)
            lines.append("")
        
        # Background knowledge
        lines.append("% === BACKGROUND KNOWLEDGE ===")
        lines.append(self.background_knowledge)
        lines.append("")
        
        # Positive examples
        if self.positive_examples:
            lines.append("% === POSITIVE EXAMPLES ===")
            for i, ex in enumerate(self.positive_examples):
                lines.append(asp_converter.ilasp_positive_example_to_asp(
                    f"pos_{self.id}_{i}", ex
                ))
            lines.append("")
        
        # Negative examples
        if self.negative_examples:
            lines.append("% === NEGATIVE EXAMPLES ===")
            for i, ex in enumerate(self.negative_examples):
                lines.append(asp_converter.ilasp_negative_example_to_asp(
                    f"neg_{self.id}_{i}", ex
                ))
            lines.append("")
        
        return "\n".join(lines)
