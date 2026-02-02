"""
Evidence Checklist for Error Detection.

Defines required evidence per error category and evaluates whether
the extracted predicates satisfy detection requirements.

This provides transparent, auditable reasoning for detectability classification.

Per LOGIC_DESIGN.md:
- Deterministic behavior
- Does NOT affect runtime logic
- Lives in evaluation/reporting code only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from ..extraction.extraction_diagnostics import EvidenceType


class PredicateType(Enum):
    """Types of structured predicates required for detection."""
    
    # Relationship predicates
    RELATIONSHIP = "relationship"  # relationship(C1, C2, Type, Time)
    SOCIAL_ACTION_TYPE = "social_action_type"  # event with social_action_type field
    
    # Temporal predicates
    TEMPORAL_CONSTRAINT = "temporal_constraint"  # temporal_constraints array entry
    AFTER_LINK = "after_link"  # event.after field
    
    # Location predicates
    PRESENT = "present"  # present(Entity, Location, Time)
    EVENT_LOCATION = "event_location"  # event.location field
    
    # State predicates
    CHARACTER_STATE = "character_state"  # character.state (normal/injured/dead)
    CHARACTER_APPEARANCE = "character_appearance"  # character.appearance
    CHARACTER_EMOTION = "character_emotion"  # character.emotion
    
    # Item predicates
    CARRIES = "carries"  # carries(Character, Item, Time)
    ITEM_STATE = "item_state"  # item.state
    
    # Event predicates
    EVENT_TYPE = "event_type"  # event.type


@dataclass
class EvidenceRequirement:
    """A single evidence requirement for error detection."""
    
    predicate_type: PredicateType
    description: str
    # Whether this is mandatory (AND) or one-of-many (OR)
    is_mandatory: bool = True


@dataclass
class ErrorCategoryChecklist:
    """Evidence checklist for an error category."""
    
    category: str
    description: str
    
    # Mandatory requirements (ALL must be present)
    mandatory_predicates: List[PredicateType] = field(default_factory=list)
    
    # Alternative requirements (AT LEAST ONE must be present)
    alternative_predicates: List[PredicateType] = field(default_factory=list)
    
    # Evidence types that indicate this category
    evidence_types: List[EvidenceType] = field(default_factory=list)
    
    # ASP rules that detect this category
    detection_rules: List[str] = field(default_factory=list)


# =============================================================================
# ERROR CATEGORY DEFINITIONS
# =============================================================================

ERROR_CATEGORY_CHECKLISTS: Dict[str, ErrorCategoryChecklist] = {
    
    # --- EMOTIONAL ERRORS ---
    "emotional_inconsistency": ErrorCategoryChecklist(
        category="emotional_inconsistency",
        description="Hostile character shows kindness, or vice versa",
        mandatory_predicates=[
            PredicateType.RELATIONSHIP,  # Must know the relationship type
        ],
        alternative_predicates=[
            PredicateType.SOCIAL_ACTION_TYPE,  # Event with social intent
            PredicateType.EVENT_TYPE,  # Emotional event type (hug, praise, etc.)
        ],
        evidence_types=[EvidenceType.EMOTIONAL],
        detection_rules=[
            "emotional_mismatch",
            "relationship_behavior_conflict",
            "hostile_kindness_violation",
            "emotional_contradiction",
        ],
    ),
    
    "relationship_violation": ErrorCategoryChecklist(
        category="relationship_violation",
        description="Action contradicts established relationship",
        mandatory_predicates=[
            PredicateType.RELATIONSHIP,
        ],
        alternative_predicates=[
            PredicateType.EVENT_TYPE,
            PredicateType.SOCIAL_ACTION_TYPE,
        ],
        evidence_types=[EvidenceType.EMOTIONAL],
        detection_rules=[
            "relationship_contradiction",
            "relationship_mismatch",
            "social_conflict",
        ],
    ),
    
    # --- TEMPORAL ERRORS ---
    "temporal_violation": ErrorCategoryChecklist(
        category="temporal_violation",
        description="Events occur in impossible temporal order",
        mandatory_predicates=[],  # No single mandatory predicate
        alternative_predicates=[
            PredicateType.TEMPORAL_CONSTRAINT,
            PredicateType.AFTER_LINK,
        ],
        evidence_types=[EvidenceType.TEMPORAL],
        detection_rules=[
            "temporal_conflict",
            "timeline_violation",
            "causality_error",
            "temporal_ordering_error",
        ],
    ),
    
    "causality_violation": ErrorCategoryChecklist(
        category="causality_violation",
        description="Effect precedes cause, or consequence without prerequisite",
        mandatory_predicates=[],
        alternative_predicates=[
            PredicateType.AFTER_LINK,
            PredicateType.TEMPORAL_CONSTRAINT,
            PredicateType.CARRIES,  # For item-based causality
            PredicateType.CHARACTER_STATE,  # For state-based causality
        ],
        evidence_types=[EvidenceType.TEMPORAL],
        detection_rules=[
            "causality_error",
            "prerequisite_missing",
            "effect_before_cause",
        ],
    ),
    
    # --- LOCATION ERRORS ---
    "location_violation": ErrorCategoryChecklist(
        category="location_violation",
        description="Character in two places at once, or impossible movement",
        mandatory_predicates=[],
        alternative_predicates=[
            PredicateType.PRESENT,
            PredicateType.EVENT_LOCATION,
        ],
        evidence_types=[EvidenceType.LOCATION],
        detection_rules=[
            "non_ubiquity",
            "ubiquity_violation",
            "location_conflict",
            "presence_contradiction",
        ],
    ),
    
    "movement_violation": ErrorCategoryChecklist(
        category="movement_violation",
        description="Character moves between unconnected locations",
        mandatory_predicates=[
            PredicateType.EVENT_LOCATION,  # Need location on events
        ],
        alternative_predicates=[
            PredicateType.PRESENT,
        ],
        evidence_types=[EvidenceType.LOCATION],
        detection_rules=[
            "movement_impossible",
            "disconnected_travel",
        ],
    ),
    
    # --- APPEARANCE ERRORS ---
    "appearance_inconsistency": ErrorCategoryChecklist(
        category="appearance_inconsistency",
        description="Character appearance contradicts prior description",
        mandatory_predicates=[
            PredicateType.CHARACTER_APPEARANCE,
        ],
        alternative_predicates=[],
        evidence_types=[EvidenceType.APPEARANCE],
        detection_rules=[
            "appearance_mismatch",
            "appearance_contradiction",
            "physical_state_conflict",
        ],
    ),
    
    # --- STATE ERRORS ---
    "state_violation": ErrorCategoryChecklist(
        category="state_violation",
        description="Character acts in impossible state (e.g., dead character acting)",
        mandatory_predicates=[
            PredicateType.CHARACTER_STATE,
        ],
        alternative_predicates=[
            PredicateType.EVENT_TYPE,
        ],
        evidence_types=[],  # Not tied to specific evidence type
        detection_rules=[
            "character_state_conflict",
            "state_contradiction",
            "dead_character_acting",
        ],
    ),
    
    # --- ITEM ERRORS ---
    "item_violation": ErrorCategoryChecklist(
        category="item_violation",
        description="Character uses item they don't have, or item in wrong state",
        mandatory_predicates=[],
        alternative_predicates=[
            PredicateType.CARRIES,
            PredicateType.ITEM_STATE,
        ],
        evidence_types=[],
        detection_rules=[
            "item_presence_error",
            "item_state_conflict",
            "carrying_contradiction",
        ],
    ),
    
    "possession_violation": ErrorCategoryChecklist(
        category="possession_violation",
        description="Item possessed by multiple characters, or used without possession",
        mandatory_predicates=[
            PredicateType.CARRIES,
        ],
        alternative_predicates=[],
        evidence_types=[],
        detection_rules=[
            "possession_conflict",
            "item_ubiquity",
            "use_without_possession",
        ],
    ),
}


@dataclass
class ChecklistItem:
    """A single item in an evaluated checklist."""
    
    predicate_type: PredicateType
    requirement: str  # "mandatory" or "alternative"
    present: bool
    source: Optional[str] = None  # Where the evidence came from


@dataclass
class ChecklistEvaluation:
    """Result of evaluating an error's evidence checklist."""
    
    error_category: str
    chapter_id: str
    
    # Checklist items
    items: List[ChecklistItem] = field(default_factory=list)
    
    # Summary
    mandatory_satisfied: bool = False
    alternative_satisfied: bool = False
    overall_satisfied: bool = False
    
    # Missing evidence
    missing_mandatory: List[PredicateType] = field(default_factory=list)
    missing_alternatives: List[PredicateType] = field(default_factory=list)
    
    # Justification
    justification: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error_category": self.error_category,
            "chapter_id": self.chapter_id,
            "items": [
                {
                    "predicate": item.predicate_type.value,
                    "requirement": item.requirement,
                    "present": item.present,
                    "source": item.source,
                }
                for item in self.items
            ],
            "mandatory_satisfied": self.mandatory_satisfied,
            "alternative_satisfied": self.alternative_satisfied,
            "overall_satisfied": self.overall_satisfied,
            "missing_mandatory": [p.value for p in self.missing_mandatory],
            "missing_alternatives": [p.value for p in self.missing_alternatives],
            "justification": self.justification,
        }


# =============================================================================
# PREDICATE PRESENCE CHECKING
# =============================================================================

def check_predicate_presence(
    predicate_type: PredicateType,
    extraction_result: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check if a predicate type is present in the extraction result.
    
    Args:
        predicate_type: The predicate type to check
        extraction_result: Merged extraction result
        
    Returns:
        Tuple of (is_present, source_description)
    """
    entities = extraction_result.get("entities", {})
    events = extraction_result.get("events", [])
    
    if predicate_type == PredicateType.RELATIONSHIP:
        relationships = entities.get("relationships", [])
        if relationships:
            return True, f"{len(relationships)} relationships"
        return False, None
    
    elif predicate_type == PredicateType.SOCIAL_ACTION_TYPE:
        for event in events:
            if event.get("social_action_type"):
                return True, f"event with social_action_type"
        return False, None
    
    elif predicate_type == PredicateType.TEMPORAL_CONSTRAINT:
        constraints = extraction_result.get("temporal_constraints", [])
        if constraints:
            return True, f"{len(constraints)} temporal constraints"
        return False, None
    
    elif predicate_type == PredicateType.AFTER_LINK:
        for event in events:
            after = event.get("after")
            if after and after != "null" and after != "":
                return True, f"event with after link"
        return False, None
    
    elif predicate_type == PredicateType.PRESENT:
        # Present predicates are derived from locations + events
        locations = entities.get("locations", [])
        if locations:
            return True, f"{len(locations)} locations"
        return False, None
    
    elif predicate_type == PredicateType.EVENT_LOCATION:
        for event in events:
            loc = event.get("location")
            if loc and loc != "null" and loc != "":
                return True, f"event with location"
        return False, None
    
    elif predicate_type == PredicateType.CHARACTER_STATE:
        characters = entities.get("characters", [])
        for char in characters:
            state = char.get("state", "normal")
            if state != "normal":
                return True, f"character with state={state}"
        # Even "normal" states are present
        if characters:
            return True, f"{len(characters)} characters with states"
        return False, None
    
    elif predicate_type == PredicateType.CHARACTER_APPEARANCE:
        characters = entities.get("characters", [])
        for char in characters:
            appearance = char.get("appearance", "normal")
            if appearance != "normal":
                return True, f"character with appearance={appearance}"
        return False, None
    
    elif predicate_type == PredicateType.CHARACTER_EMOTION:
        characters = entities.get("characters", [])
        for char in characters:
            emotion = char.get("emotion", "neutral")
            if emotion not in ("neutral", "calm"):
                return True, f"character with emotion={emotion}"
        return False, None
    
    elif predicate_type == PredicateType.CARRIES:
        # Check for give/take events or item tracking
        for event in events:
            if event.get("type") in ("give", "take"):
                return True, f"give/take event"
        return False, None
    
    elif predicate_type == PredicateType.ITEM_STATE:
        items = entities.get("items", [])
        for item in items:
            state = item.get("state")
            if state and state != "intact":
                return True, f"item with state={state}"
        if items:
            return True, f"{len(items)} items with states"
        return False, None
    
    elif predicate_type == PredicateType.EVENT_TYPE:
        if events:
            types = set(e.get("type", "") for e in events)
            return True, f"event types: {', '.join(types)}"
        return False, None
    
    return False, None


def evaluate_checklist(
    error_category: str,
    chapter_id: str,
    extraction_result: Dict[str, Any],
) -> ChecklistEvaluation:
    """
    Evaluate the evidence checklist for an error category.
    
    Args:
        error_category: The error category to evaluate
        chapter_id: Chapter identifier
        extraction_result: Merged extraction result
        
    Returns:
        ChecklistEvaluation with detailed results
    """
    evaluation = ChecklistEvaluation(
        error_category=error_category,
        chapter_id=chapter_id,
    )
    
    # Get the checklist for this category
    checklist = ERROR_CATEGORY_CHECKLISTS.get(error_category)
    if not checklist:
        evaluation.justification = f"Unknown error category: {error_category}"
        return evaluation
    
    # Check mandatory predicates
    mandatory_present = []
    for predicate_type in checklist.mandatory_predicates:
        present, source = check_predicate_presence(predicate_type, extraction_result)
        evaluation.items.append(ChecklistItem(
            predicate_type=predicate_type,
            requirement="mandatory",
            present=present,
            source=source,
        ))
        if present:
            mandatory_present.append(predicate_type)
        else:
            evaluation.missing_mandatory.append(predicate_type)
    
    # Check alternative predicates
    alternative_present = []
    for predicate_type in checklist.alternative_predicates:
        present, source = check_predicate_presence(predicate_type, extraction_result)
        evaluation.items.append(ChecklistItem(
            predicate_type=predicate_type,
            requirement="alternative",
            present=present,
            source=source,
        ))
        if present:
            alternative_present.append(predicate_type)
        else:
            evaluation.missing_alternatives.append(predicate_type)
    
    # Evaluate satisfaction
    # Mandatory: ALL must be present (or none required)
    evaluation.mandatory_satisfied = (
        len(evaluation.missing_mandatory) == 0 or 
        len(checklist.mandatory_predicates) == 0
    )
    
    # Alternative: AT LEAST ONE must be present (or none required)
    evaluation.alternative_satisfied = (
        len(alternative_present) > 0 or
        len(checklist.alternative_predicates) == 0
    )
    
    # Overall: both conditions must be met
    evaluation.overall_satisfied = (
        evaluation.mandatory_satisfied and evaluation.alternative_satisfied
    )
    
    # Generate justification
    justification_parts = []
    
    if evaluation.overall_satisfied:
        justification_parts.append("All required evidence present.")
        if mandatory_present:
            justification_parts.append(
                f"Mandatory: {', '.join(p.value for p in mandatory_present)}"
            )
        if alternative_present:
            justification_parts.append(
                f"Alternatives satisfied by: {', '.join(p.value for p in alternative_present)}"
            )
    else:
        justification_parts.append("Insufficient evidence for detection.")
        if evaluation.missing_mandatory:
            justification_parts.append(
                f"Missing mandatory: {', '.join(p.value for p in evaluation.missing_mandatory)}"
            )
        if not evaluation.alternative_satisfied and checklist.alternative_predicates:
            justification_parts.append(
                f"Missing all alternatives: {', '.join(p.value for p in evaluation.missing_alternatives)}"
            )
    
    evaluation.justification = " ".join(justification_parts)
    
    return evaluation


def get_checklist_for_category(category: str) -> Optional[ErrorCategoryChecklist]:
    """Get the evidence checklist for an error category."""
    return ERROR_CATEGORY_CHECKLISTS.get(category)


def get_all_categories() -> List[str]:
    """Get all defined error categories."""
    return list(ERROR_CATEGORY_CHECKLISTS.keys())


def format_checklist_evaluation(evaluation: ChecklistEvaluation) -> str:
    """
    Format a checklist evaluation as a human-readable string.
    
    Args:
        evaluation: ChecklistEvaluation to format
        
    Returns:
        Formatted string
    """
    lines = [
        f"Evidence Checklist: {evaluation.error_category}",
        f"Chapter: {evaluation.chapter_id}",
        "-" * 40,
    ]
    
    # Group items by requirement type
    mandatory_items = [i for i in evaluation.items if i.requirement == "mandatory"]
    alternative_items = [i for i in evaluation.items if i.requirement == "alternative"]
    
    if mandatory_items:
        lines.append("MANDATORY (all required):")
        for item in mandatory_items:
            status = "✓" if item.present else "✗"
            source = f" ({item.source})" if item.source else ""
            lines.append(f"  {status} {item.predicate_type.value}{source}")
    
    if alternative_items:
        lines.append("ALTERNATIVE (at least one):")
        for item in alternative_items:
            status = "✓" if item.present else "✗"
            source = f" ({item.source})" if item.source else ""
            lines.append(f"  {status} {item.predicate_type.value}{source}")
    
    lines.append("-" * 40)
    overall = "SATISFIED" if evaluation.overall_satisfied else "NOT SATISFIED"
    lines.append(f"Status: {overall}")
    lines.append(f"Justification: {evaluation.justification}")
    
    return "\n".join(lines)
