"""
Domain classes for the Event Executor module.

Contains dataclasses and enums for structured output.
"""

from .entity_diagnostic_info import EntityDiagnosticInfo
from .violation_severity import ViolationSeverity
from .provenance import Provenance
from .structured_violation import StructuredViolation
from .chapter_evaluation_result import ChapterEvaluationResult
from .event import Event
from .event_result import EventResult

# Alias resolution domain classes
from .promotion_reason import PromotionReason
from .unification_reason import UnificationReason
from .alias_unification import AliasUnification
from .canonical_promotion import CanonicalPromotion
from .alias_conflict import AliasConflict

# Entity registry domain classes
from .entity_type import EntityType
from .lifecycle_state import LifecycleState
from .registered_entity import RegisteredEntity

# State manager domain classes
from .entity import Entity
from .relation import Relation
from .story_rule import StoryRule
from .world_state import WorldState
from .state_delta import StateDelta

# Item tracker domain classes
from .item_lifecycle_state import ItemLifecycleState
from .item_relevance import ItemRelevance
from .tracked_item import TrackedItem

# Learning adapter domain classes
from .learning_task import LearningTask
from .learned_rule import LearnedRule

# Active universe domain classes
from .active_universe_result import ActiveUniverseResult
from .time_scope import TimeScope

# Rule registry domain classes
from .rule_layer import RuleLayer
from .rule import Rule
from .rule_override import RuleOverride

# Conflict resolver domain classes
from .story_context import StoryContext
from .conflict import Conflict

# Movement resolver domain classes
from .derived_transition import DerivedTransition
from .movement_continuity_result import MovementContinuityResult

# Relationship manager domain classes
from .relationship import Relationship
from .filtered_relationship_result import FilteredRelationshipResult

# ASP diagnostics domain classes
from .asp_universe_stats import ASPUniverseStats
from .asp_diagnostics_collector import ASPDiagnosticsCollector

# Continuity context domain classes
from .continuity_context import ContinuityContext

# Context persistence domain classes
from .context import Context

# Rule projector domain classes
from .projected_rule import ProjectedRule
from .rule_projection_result import RuleProjectionResult

__all__ = [
    "EntityDiagnosticInfo",
    "ViolationSeverity",
    "Provenance",
    "StructuredViolation",
    "ChapterEvaluationResult",
    "Event",
    "EventResult",
    # Alias resolution domain classes
    "PromotionReason",
    "UnificationReason",
    "AliasUnification",
    "CanonicalPromotion",
    "AliasConflict",
    # Entity registry domain classes
    "EntityType",
    "LifecycleState",
    "RegisteredEntity",
    # State manager domain classes
    "Entity",
    "Relation",
    "StoryRule",
    "WorldState",
    "StateDelta",
    # Item tracker domain classes
    "ItemLifecycleState",
    "ItemRelevance",
    "TrackedItem",
    # Learning adapter domain classes
    "LearningTask",
    "LearnedRule",
    # Active universe domain classes
    "ActiveUniverseResult",
    "TimeScope",
    # Rule registry domain classes
    "RuleLayer",
    "Rule",
    "RuleOverride",
    # Conflict resolver domain classes
    "StoryContext",
    "Conflict",
    # Movement resolver domain classes
    "DerivedTransition",
    "MovementContinuityResult",
    # Relationship manager domain classes
    "Relationship",
    "FilteredRelationshipResult",
    # ASP diagnostics domain classes
    "ASPUniverseStats",
    "ASPDiagnosticsCollector",
    # Continuity context domain classes
    "ContinuityContext",
    # Context persistence domain classes
    "Context",
    # Rule projector domain classes
    "ProjectedRule",
    "RuleProjectionResult",
]
