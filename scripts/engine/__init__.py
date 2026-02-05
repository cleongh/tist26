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

Phase 2 (Alias Resolution):
    - AliasResolver: Canonical identity & alias resolution
    - AliasConflict: Records conflicting alias mappings

Phase 3 (Continuity Context):
    - ContinuityContextBuilder: Gathers known state for LLM prompts
    - ContinuityContext: Structured context for prompt injection

Phase 4 (Item Tracking):
    - ItemTracker: Item lifecycle management & filtering
    - TrackedItem: Tracked item with lifecycle state
    - ItemLifecycleState: Enum for item states
    - ItemRelevance: Enum for item relevance classification
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
from .resolvers import ConflictResolver, AliasResolver
from .learning_adapter import LearningAdapter
from .final_analysis import (
    FinalAnalyzer,
    FinalAnalysisResult,
    RuleAuditEntry,
    LooseEnd,
    LongRangeInconsistency,
)
from .domain import AliasConflict, CanonicalPromotion, PromotionReason, ContinuityContext
from .builders import ContinuityContextBuilder
from .item_tracker import (
    ItemTracker,
    TrackedItem,
    ItemLifecycleState,
    ItemRelevance,
)
from .registries import (
    EntityRegistry,
    LifecycleRegistry,
    RuleRegistry,
)
from .managers import (
    CharacterAliasManager,
    LocationAliasManager,
)
from .domain import (
    RegisteredEntity,
    EntityType,
    LifecycleState,
    # State manager domain classes
    Entity,
    Relation,
    StoryRule,
    WorldState,
    StateDelta,
    # Rule registry domain classes
    RuleLayer,
    Rule,
    RuleOverride,
    # Conflict resolver domain classes
    StoryContext,
    Conflict,
    # Movement resolver domain classes
    DerivedTransition,
    MovementContinuityResult,
)
from .resolvers import MovementResolver
from .config import (
    ACTIVE_THRESHOLD,
    LATENT_THRESHOLD,
    EXPLICIT_MOVEMENT_TYPES,
)
# Context persistence (refactored from context_persistence.py)
from .managers import PersistenceManager, ConsultantsManager
from .domain import Context
from .active_universe import ActiveUniverse
from .domain import ActiveUniverseResult, TimeScope
# ASP diagnostics (refactored from asp_diagnostics.py)
from .asp_diagnostics_generator import ASPDiagnosticsGenerator
from .domain import ASPUniverseStats, ASPDiagnosticsCollector
# Relationship management (refactored from relationship_projector.py)
from .managers import RelationshipManager
from .domain import Relationship, FilteredRelationshipResult
# Rule projection (refactored from rule_projector.py)
from .managers import RuleManager
from .domain import ProjectedRule, RuleProjectionResult
# ASP conversion utilities (Phase 8: All ASP formatting consolidated to AspConverter)
from .preprocessors import AspConverter

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
    # Alias resolution (Phase 2)
    'AliasResolver',
    'AliasConflict',
    'CanonicalPromotion',
    'PromotionReason',
    # Continuity context (Phase 3)
    'ContinuityContextBuilder',
    'ContinuityContext',
    # Item tracking (Phase 4)
    'ItemTracker',
    'TrackedItem',
    'ItemLifecycleState',
    'ItemRelevance',
    # Entity registry (Phase 8.2: Memory optimization)
    'EntityRegistry',
    'LifecycleRegistry',
    'RegisteredEntity',
    'EntityType',
    # Entity lifecycle (Phase 8.3)
    'LifecycleState',
    'ACTIVE_THRESHOLD',
    'LATENT_THRESHOLD',
    # State manager domain classes
    'Entity',
    'Relation',
    'StoryRule',
    'WorldState',
    'StateDelta',
    # Rule registry domain classes
    'RuleLayer',
    'Rule',
    'RuleOverride',
    # Conflict resolver domain classes
    'StoryContext',
    'Conflict',
    # Movement resolver domain classes
    'MovementResolver',
    'DerivedTransition',
    'MovementContinuityResult',
    'EXPLICIT_MOVEMENT_TYPES',
    # Managers (Phase 2)
    'CharacterAliasManager',
    'LocationAliasManager',
    # Context persistence (refactored from context_persistence.py)
    'PersistenceManager',
    'ConsultantsManager',
    'Context',
    # Active universe (Phase 8.6: ASP grounding optimization)
    'ActiveUniverse',
    'ActiveUniverseResult',
    'TimeScope',
    # ASP diagnostics (refactored from asp_diagnostics.py)
    'ASPDiagnosticsGenerator',
    'ASPUniverseStats',
    'ASPDiagnosticsCollector',
    # Relationship management (refactored from relationship_projector.py)
    'RelationshipManager',
    'Relationship',
    'FilteredRelationshipResult',
    # Rule projection (refactored from rule_projector.py)
    'RuleManager',
    'ProjectedRule',
    'RuleProjectionResult',
    # ASP conversion utilities (Phase 8)
    'AspConverter',
]

__version__ = '0.9.12'  # Refactored rule_projector.py to RuleManager
