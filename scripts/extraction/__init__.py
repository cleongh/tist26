# extraction/ - LLM calls and prompt construction
# TODO: Future refactors may split prompts into separate files

from .api_clients import (
    GeminiAPIClient,
    OpenAIAPIClient,
    LocalLLMClient,
    create_api_client,
)
from .prompts import (
    LLM_SYSTEM_MESSAGE,
    LLM_LINT_PROMPT,
)
from .llm_client import LLMClient
from .chapter_extractor import structure_chapter_standalone

# Phase 2: Split extraction functions
from .extractors import (
    extract_characters_and_locations,
    extract_items,
    extract_relationships,
    extract_events,
    merge_extractions,
    extract_chapter_split,
)

# Phase 3: EntityRegistry for canonical entity management
from .entity_registry import EntityRegistry, ValidationWarning

# Phase 4: RelationshipNormalizer for group expansion and deduplication
from .relationship_normalizer import (
    RelationshipNormalizer,
    RelationshipConflict,
    NormalizationResult,
)

# Phase 5: EventNormalizer for strict validation and item classification
from .event_normalizer import (
    EventNormalizer,
    EventNormalizationResult,
    DroppedEvent,
    ItemUsage,
    ItemUsageType,
)

# Phase 6: LifecycleTracker for cross-chapter lifecycle management
from .lifecycle_tracker import (
    LifecycleTracker,
    EntityLifecycle,
    EntityLifecycleState,
    RelationshipLifecycle,
    RelationshipState,
    LooseEnd,
    BackAnnotation,
    FinalAnalysisResult,
)

# JSON utilities for deterministic LLM output parsing
from .json_utils import (
    parse_llm_json,
    parse_llm_json_strict,
    repair_json,
    JSONParseError,
)

__all__ = [
    "GeminiAPIClient",
    "OpenAIAPIClient",
    "LocalLLMClient",
    "create_api_client",
    "LLM_SYSTEM_MESSAGE",
    "LLM_LINT_PROMPT",
    "LLMClient",
    "structure_chapter_standalone",
    # Phase 2: Split extraction functions
    "extract_characters_and_locations",
    "extract_items",
    "extract_relationships",
    "extract_events",
    "merge_extractions",
    "extract_chapter_split",
    # Phase 3: EntityRegistry
    "EntityRegistry",
    "ValidationWarning",
    # Phase 4: RelationshipNormalizer
    "RelationshipNormalizer",
    "RelationshipConflict",
    "NormalizationResult",
    # Phase 5: EventNormalizer
    "EventNormalizer",
    "EventNormalizationResult",
    "DroppedEvent",
    "ItemUsage",
    "ItemUsageType",
    # Phase 6: LifecycleTracker
    "LifecycleTracker",
    "EntityLifecycle",
    "EntityLifecycleState",
    "RelationshipLifecycle",
    "RelationshipState",
    "LooseEnd",
    "BackAnnotation",
    "FinalAnalysisResult",
    # JSON utilities
    "parse_llm_json",
    "parse_llm_json_strict",
    "repair_json",
    "JSONParseError",
]
