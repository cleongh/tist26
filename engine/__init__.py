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
    - build_continuity_context: Convenience function

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
from .alias_resolver import AliasResolver, AliasConflict, CanonicalPromotion, PromotionReason
from .continuity_context import (
    ContinuityContextBuilder,
    ContinuityContext,
    build_continuity_context,
)
from .item_tracker import (
    ItemTracker,
    TrackedItem,
    ItemLifecycleState,
    ItemRelevance,
)
from .entity_registry import (
    EntityRegistry,
    RegisteredEntity,
    EntityType,
    LifecycleState,
    ACTIVE_THRESHOLD,
    LATENT_THRESHOLD,
)
from .context_persistence import (
    PersistentContext,
    ContextMetadata,
)
from .active_universe import (
    compute_active_universe,
    compute_active_universe_from_state_manager,
    ActiveUniverseResult,
    extract_entities_from_events,
    filter_asp_facts_by_universe,
    # Time scoping (Phase 8.7)
    TimeScope,
    compute_time_scope,
    filter_facts_by_time_scope,
)
from .asp_diagnostics import (
    # ASP diagnostics (Phase 8.8)
    log_asp_universe,
    log_run_summary,
    ASPUniverseStats,
    ASPDiagnosticsCollector,
    enable as enable_asp_diagnostics,
    disable as disable_asp_diagnostics,
    is_enabled as asp_diagnostics_enabled,
    get_collector as get_asp_diagnostics_collector,
    reset_collector as reset_asp_diagnostics,
)
from .relationship_projector import (
    # Relationship projection (Phase 8.10)
    ProjectedRelationship,
    RelationshipProjectionResult,
    project_relationships,
    project_relationships_to_asp_facts,
    is_relationship_in_universe,
    filter_relationship_facts,
    # Relationship debug (Phase 8.11.2)
    enable_relationship_debug,
    disable_relationship_debug,
    is_relationship_debug_enabled,
    reset_relationship_debug_stats,
    get_relationship_debug_stats,
)
from .rule_projector import (
    # Rule projection (Phase 8.11)
    ProjectedRule,
    RuleProjectionResult,
    project_story_rules,
    project_learned_rules,  # Phase 8.11.1
    project_rules,  # Phase 8.11.1: Unified projection
    get_projected_rules_content,
    get_projected_learned_rules_content,  # Phase 8.11.1
    get_all_projected_rules_content,
    extract_entities_from_rule,
    is_rule_in_universe,
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
    # Alias resolution (Phase 2)
    'AliasResolver',
    'AliasConflict',
    'CanonicalPromotion',
    'PromotionReason',
    # Continuity context (Phase 3)
    'ContinuityContextBuilder',
    'ContinuityContext',
    'build_continuity_context',
    # Item tracking (Phase 4)
    'ItemTracker',
    'TrackedItem',
    'ItemLifecycleState',
    'ItemRelevance',
    # Entity registry (Phase 8.2: Memory optimization)
    'EntityRegistry',
    'RegisteredEntity',
    'EntityType',
    # Entity lifecycle (Phase 8.3)
    'LifecycleState',
    'ACTIVE_THRESHOLD',
    'LATENT_THRESHOLD',
    # Context persistence (Phase 8.4)
    'PersistentContext',
    'ContextMetadata',
    # Active universe (Phase 8.6: ASP grounding optimization)
    'compute_active_universe',
    'compute_active_universe_from_state_manager',
    'ActiveUniverseResult',
    'extract_entities_from_events',
    'filter_asp_facts_by_universe',
    # Time scoping (Phase 8.7: Time-local ASP facts)
    'TimeScope',
    'compute_time_scope',
    'filter_facts_by_time_scope',
    # ASP diagnostics (Phase 8.8)
    'log_asp_universe',
    'log_run_summary',
    'ASPUniverseStats',
    'ASPDiagnosticsCollector',
    'enable_asp_diagnostics',
    'disable_asp_diagnostics',
    'asp_diagnostics_enabled',
    'get_asp_diagnostics_collector',
    'reset_asp_diagnostics',
    # Relationship projection (Phase 8.10)
    'ProjectedRelationship',
    'RelationshipProjectionResult',
    'project_relationships',
    'project_relationships_to_asp_facts',
    'is_relationship_in_universe',
    'filter_relationship_facts',
    # Relationship debug (Phase 8.11.2)
    'enable_relationship_debug',
    'disable_relationship_debug',
    'is_relationship_debug_enabled',
    'reset_relationship_debug_stats',
    'get_relationship_debug_stats',
    # Rule projection (Phase 8.11)
    'ProjectedRule',
    'RuleProjectionResult',
    'project_story_rules',
    'project_learned_rules',
    'project_rules',
    'get_projected_rules_content',
    'get_projected_learned_rules_content',
    'get_all_projected_rules_content',
    'extract_entities_from_rule',
    'is_rule_in_universe',
]

__version__ = '0.9.9'  # Phase 8.11.2: Relationship projection debug instrumentation
