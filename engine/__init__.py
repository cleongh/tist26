"""
Narrative Logic Engine - Python Orchestration Layer

This module provides the orchestration layer for the Narrative Logic Engine.
Following LOGIC_DESIGN.md, Python is strictly for orchestration - all reasoning
is performed by ASP (Clingo) and rule learning by ILASP.

Modules:
    state_manager: World state snapshots & deltas
    event_executor: Applies events per timestep
    rule_registry: Rule loading, priorities, activation
    conflict_resolver: Handles rule overrides & deactivation
    learning_adapter: ILASP integration
    final_analysis: Story-wide analysis after final chapter (Phase 5)

Anti-Goals (from LOGIC_DESIGN.md):
    - Python must NOT encode narrative logic in conditionals
    - Python must NOT use LLM reasoning inside the logic engine
    - Python must NOT delete overridden rules
    - Python must NOT produce natural language explanations
    - Python must NOT break determinism or grounding assumptions

Phase 4 Additions:
    - ViolationSeverity: Enum for hard/soft/warning severity
    - StructuredViolation: Structured violation output
    - ChapterEvaluationResult: Structured chapter evaluation result

Phase 5 Additions:
    - Provenance: Tracks how conclusions were reached
    - FinalAnalyzer: Story-wide analysis after final chapter
    - FinalAnalysisResult: Structured final analysis output
    - LooseEnd, LongRangeInconsistency: Detected issues
"""

from .state_manager import StateManager
from .event_executor import (
    EventExecutor, 
    Event, 
    EventResult,
    ViolationSeverity,
    StructuredViolation,
    ChapterEvaluationResult,
    Provenance,
)
from .rule_registry import RuleRegistry
from .conflict_resolver import ConflictResolver
from .learning_adapter import LearningAdapter
from .final_analysis import (
    FinalAnalyzer,
    FinalAnalysisResult,
    RuleAuditEntry,
    LooseEnd,
    LongRangeInconsistency,
)

__all__ = [
    # Core modules
    'StateManager',
    'EventExecutor',
    'RuleRegistry',
    'ConflictResolver',
    'LearningAdapter',
    'FinalAnalyzer',
    # Event types
    'Event',
    'EventResult',
    # Violation types (Phase 4+5)
    'ViolationSeverity',
    'StructuredViolation',
    'ChapterEvaluationResult',
    'Provenance',
    # Final analysis types (Phase 5)
    'FinalAnalysisResult',
    'RuleAuditEntry',
    'LooseEnd',
    'LongRangeInconsistency',
]

__version__ = '0.3.0'  # Phase 5 update
