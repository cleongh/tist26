"""
Conflict Resolver - Handles Rule Overrides & Deactivation

Responsibilities:
    - Detect when story contradicts universal rules
    - Generate story-specific override rules
    - Deactivate overridden universal rules
    - Log conflicts with provenance

Per LOGIC_DESIGN.md Section 5 (Step 3):
    If a story contradicts a universal rule:
        - Generate a story-specific override rule
        - Deactivate the universal rule
    Conflicts are logged with provenance

Phase 3 Refactoring (Step 3.4):
    - Detect violations against universal rules
    - Check if story provides override
    - Generate story-specific exception rules
    - Log conflicts with full provenance
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import json

from .rule_registry import RuleRegistry, RuleLayer


@dataclass
class StoryContext:
    """
    Context about a story that affects rule interpretation.
    
    Used to identify when violations should be treated as story exceptions
    rather than actual errors.
    """
    story_id: str = ""
    is_fantasy: bool = False
    has_magic: bool = False
    has_teleportation: bool = False
    undead_characters: List[str] = field(default_factory=list)
    ghost_characters: List[str] = field(default_factory=list)
    immortal_characters: List[str] = field(default_factory=list)
    custom_exceptions: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class Conflict:
    """
    Record of a conflict between story and universal rules.
    """
    id: str
    universal_rule_id: str
    story_rule_id: str
    violation_type: str
    entities_involved: List[str]
    event_id: str
    timestamp: str
    resolved: bool = False
    resolution: str = ""  # 'override', 'exception', 'retain'
    provenance: Dict[str, Any] = field(default_factory=dict)


class ConflictResolver:
    """
    Resolves conflicts between rule layers.
    
    When a story violates a universal rule, this component:
        1. Analyzes the conflict
        2. Generates an appropriate story-specific rule
        3. Deactivates the universal rule for this story
        4. Logs the conflict with full provenance
    
    Per LOGIC_DESIGN.md:
        - Stories can override physical impossibilities
        - Contradicted rules are deactivated but retained
        - All conflicts are logged for auditing
    
    Does NOT:
        - Make narrative judgments
        - Interpret violation meaning
        - Delete or forget rules
    """
    
    def __init__(self, rule_registry: RuleRegistry):
        self.rule_registry = rule_registry
        self.conflicts: List[Conflict] = []
        self._conflict_counter = 0
        self.story_context: Optional[StoryContext] = None
    
    def set_story_context(self, context: StoryContext) -> None:
        """Set the story context for conflict analysis."""
        self.story_context = context
    
    def initialize_story_context(self, story_id: str, 
                                  story_metadata: Dict[str, Any] = None) -> StoryContext:
        """
        Initialize story context from metadata.
        
        Args:
            story_id: Identifier for the story
            story_metadata: Optional metadata about the story
        
        Returns:
            Initialized StoryContext
            
        Note:
            Per LOGIC_DESIGN.md Section 2, story attributes must come from
            extraction, not hardcoded detection. The metadata dict should
            contain is_fantasy, has_magic, has_teleportation, etc. as
            determined by the LLM extraction phase.
        """
        metadata = story_metadata or {}
        
        # Story attributes come from extraction/metadata only (LOGIC_DESIGN.md)
        # No hardcoded story detection - that would be encoding story logic in Python
        is_fantasy = metadata.get("is_fantasy", False)
        has_magic = metadata.get("has_magic", False)
        has_teleportation = metadata.get("has_teleportation", False)
        
        context = StoryContext(
            story_id=story_id,
            is_fantasy=is_fantasy,
            has_magic=has_magic,
            has_teleportation=has_teleportation,
            undead_characters=metadata.get("undead_characters", []),
            ghost_characters=metadata.get("ghost_characters", []),
            immortal_characters=metadata.get("immortal_characters", []),
        )
        
        self.story_context = context
        return context
    
    def _generate_conflict_id(self) -> str:
        """Generate a unique conflict ID."""
        self._conflict_counter += 1
        return f"conflict_{self._conflict_counter}"
    
    def analyze_violation(self, violation: Dict[str, Any], 
                          story_context: Dict[str, Any] = None) -> Optional[Conflict]:
        """
        Analyze a violation to determine if it represents a story-universal conflict.
        
        Not all violations are conflicts. This method identifies when a story
        is intentionally breaking a universal rule (e.g., ghosts acting while 'dead').
        
        Args:
            violation: Violation dict from Clingo
            story_context: Additional context about the story
        
        Returns:
            Conflict object if this is a rule conflict, None otherwise
        """
        category = violation.get("category", "")
        vtype = violation.get("type", "")
        event_id = violation.get("event", "")
        detail = violation.get("detail", "")
        
        # Identify known conflict patterns
        conflict_patterns = self._identify_conflict_patterns(
            category, vtype, detail, story_context or {}
        )
        
        if not conflict_patterns:
            return None  # Not a rule conflict, just a regular violation
        
        # Create conflict record
        conflict = Conflict(
            id=self._generate_conflict_id(),
            universal_rule_id=conflict_patterns.get("universal_rule", f"{category}_{vtype}"),
            story_rule_id="",  # Will be set when resolved
            violation_type=vtype,
            entities_involved=self._extract_entities(violation),
            event_id=event_id,
            timestamp=datetime.now().isoformat(),
            provenance={
                "violation": violation,
                "pattern": conflict_patterns,
                "context": story_context,
            }
        )
        
        return conflict
    
    def _identify_conflict_patterns(self, category: str, vtype: str, 
                                    detail: str, context: Dict) -> Optional[Dict]:
        """
        Identify if a violation matches a known conflict pattern.
        
        Conflict patterns indicate the story is intentionally violating
        a universal rule (e.g., fantasy elements, magic, etc.).
        """
        # Use StoryContext if available and context is a dict
        if self.story_context and isinstance(context, dict):
            # Merge StoryContext into context
            if not context.get("undead_characters"):
                context["undead_characters"] = self.story_context.undead_characters
            if not context.get("ghost_characters"):
                context["ghost_characters"] = self.story_context.ghost_characters
            if not context.get("is_fantasy"):
                context["is_fantasy"] = self.story_context.is_fantasy
            if not context.get("has_magic"):
                context["has_magic"] = self.story_context.has_magic
            if not context.get("has_teleportation"):
                context["has_teleportation"] = self.story_context.has_teleportation
        
        # -----------------------------------------------------------------
        # ARCHITECTURE NOTE (LOGIC_DESIGN.md Section 2 & 8):
        # The pattern matching below is a transitional implementation.
        # Ideally, these exceptions should be ASP rules like:
        #     -violation(causality, dead_agent, E, C) :- ghost(C), agent(E, C).
        # The Python code here only checks metadata flags that were extracted
        # by the LLM, it does not reason about the story world.
        # -----------------------------------------------------------------
        
        # Ghost/undead characters acting (dead_character_acting)
        if vtype == "dead_character_acting":
            # Check if the character is a known ghost/undead in story context
            # This is metadata lookup, not narrative reasoning
            character = detail
            undead_chars = context.get("undead_characters", [])
            ghost_chars = context.get("ghost_characters", [])
            
            if character in undead_chars or character in ghost_chars:
                return {
                    "type": "undead_exception",
                    "universal_rule": "causality_dead_character_acting",
                    "reason": f"{character} is undead/ghost in this story",
                }
        
        # Magic/teleportation (ubiquity violations)
        if vtype == "ubiquity" and category == "location":
            if context.get("has_teleportation"):
                return {
                    "type": "teleportation_exception",
                    "universal_rule": "location_ubiquity",
                    "reason": "Story has teleportation/apparition",
                }
        
        # Impossible physics
        if category == "causality" and vtype in ("impossible_action", "physical_impossibility"):
            if context.get("is_fantasy") or context.get("has_magic"):
                return {
                    "type": "magic_exception",
                    "universal_rule": f"causality_{vtype}",
                    "reason": "Story has magic/fantasy elements",
                }
        
        return None
    
    def _extract_entities(self, violation: Dict[str, Any]) -> List[str]:
        """Extract entity IDs involved in a violation."""
        entities = []
        
        detail = violation.get("detail", "")
        if detail and detail != "unknown":
            # Handle pair(X, Y) format
            if detail.startswith("pair("):
                inner = detail[5:-1]
                entities.extend([e.strip() for e in inner.split(",")])
            else:
                entities.append(detail)
        
        return entities
    
    def resolve_conflict(self, conflict: Conflict, 
                         resolution_type: str = "override") -> Tuple[bool, str]:
        """
        Resolve a conflict by generating appropriate rules.
        
        Resolution types:
            - 'override': Generate story rule that overrides universal rule
            - 'exception': Generate exception for specific entities
            - 'retain': Keep universal rule, mark violation as intentional
        
        Args:
            conflict: The conflict to resolve
            resolution_type: How to resolve ('override', 'exception', 'retain')
        
        Returns:
            Tuple of (success, story_rule_id or error message)
        """
        if resolution_type == "override":
            return self._resolve_with_override(conflict)
        elif resolution_type == "exception":
            return self._resolve_with_exception(conflict)
        elif resolution_type == "retain":
            return self._resolve_retain(conflict)
        else:
            return False, f"Unknown resolution type: {resolution_type}"
    
    def _resolve_with_override(self, conflict: Conflict) -> Tuple[bool, str]:
        """
        Resolve by fully overriding the universal rule.
        
        The universal rule is deactivated for this story.
        """
        # Generate story-specific override rule
        story_rule_id = f"story_override_{conflict.id}"
        story_rule_content = self._generate_override_rule(conflict)
        
        # Add story rule
        self.rule_registry.add_rule(
            rule_id=story_rule_id,
            layer=RuleLayer.STORY,
            content=story_rule_content,
            source=f"Generated from conflict {conflict.id}",
        )
        
        # Deactivate universal rule
        self.rule_registry.deactivate_rule(
            rule_id=conflict.universal_rule_id,
            overriding_rule_id=story_rule_id,
            reason=conflict.provenance.get("pattern", {}).get("reason", "Story override"),
        )
        
        # Update conflict record
        conflict.story_rule_id = story_rule_id
        conflict.resolved = True
        conflict.resolution = "override"
        
        self.conflicts.append(conflict)
        
        return True, story_rule_id
    
    def _resolve_with_exception(self, conflict: Conflict) -> Tuple[bool, str]:
        """
        Resolve by adding an exception for specific entities.
        
        The universal rule remains active but doesn't apply to listed entities.
        """
        story_rule_id = f"story_exception_{conflict.id}"
        story_rule_content = self._generate_exception_rule(conflict)
        
        # Add exception rule
        self.rule_registry.add_rule(
            rule_id=story_rule_id,
            layer=RuleLayer.STORY,
            content=story_rule_content,
            source=f"Generated exception from conflict {conflict.id}",
        )
        
        # Update conflict record
        conflict.story_rule_id = story_rule_id
        conflict.resolved = True
        conflict.resolution = "exception"
        
        self.conflicts.append(conflict)
        
        return True, story_rule_id
    
    def _resolve_retain(self, conflict: Conflict) -> Tuple[bool, str]:
        """
        Resolve by retaining the violation as intentional.
        
        No rules are changed, but the conflict is logged.
        """
        conflict.resolved = True
        conflict.resolution = "retain"
        
        self.conflicts.append(conflict)
        
        return True, "retained_as_intentional"
    
    def _generate_override_rule(self, conflict: Conflict) -> str:
        """Generate ASP rule that overrides a universal rule."""
        vtype = conflict.violation_type
        
        # Generate negation of the universal rule
        return f"""
% Story override for {conflict.universal_rule_id}
% Generated from conflict: {conflict.id}
% Reason: {conflict.provenance.get('pattern', {}).get('reason', 'Story override')}

% Disable violation detection for {vtype}
story_override({vtype}).
-violation(Category, {vtype}, E, D) :- story_override({vtype}), violation(Category, {vtype}, E, D).
"""
    
    def _generate_exception_rule(self, conflict: Conflict) -> str:
        """Generate ASP rule that creates an exception for specific entities."""
        entities = conflict.entities_involved
        vtype = conflict.violation_type
        
        lines = [
            f"% Story exception for {conflict.universal_rule_id}",
            f"% Generated from conflict: {conflict.id}",
            f"% Entities excepted: {', '.join(entities)}",
            "",
        ]
        
        for entity in entities:
            lines.append(f"story_exception({vtype}, {entity}).")
        
        lines.append("")
        lines.append(f"% Suppress violations for excepted entities")
        lines.append(f"-violation(Category, {vtype}, E, Entity) :- "
                     f"story_exception({vtype}, Entity), violation(Category, {vtype}, E, Entity).")
        
        return "\n".join(lines)
    
    def get_unresolved_conflicts(self) -> List[Conflict]:
        """Get all unresolved conflicts."""
        return [c for c in self.conflicts if not c.resolved]
    
    def get_conflicts_by_type(self, vtype: str) -> List[Conflict]:
        """Get all conflicts of a specific violation type."""
        return [c for c in self.conflicts if c.violation_type == vtype]
    
    def get_conflict_summary(self) -> Dict[str, Any]:
        """
        Get summary of all conflicts for auditing.
        
        Per LOGIC_DESIGN.md Section 6: Audit all active and deactivated rules.
        """
        by_resolution = {}
        for c in self.conflicts:
            res = c.resolution or "unresolved"
            by_resolution[res] = by_resolution.get(res, 0) + 1
        
        return {
            "total_conflicts": len(self.conflicts),
            "resolved": len([c for c in self.conflicts if c.resolved]),
            "unresolved": len([c for c in self.conflicts if not c.resolved]),
            "by_resolution": by_resolution,
            "conflicts": [
                {
                    "id": c.id,
                    "universal_rule": c.universal_rule_id,
                    "story_rule": c.story_rule_id,
                    "violation_type": c.violation_type,
                    "entities": c.entities_involved,
                    "resolved": c.resolved,
                    "resolution": c.resolution,
                }
                for c in self.conflicts
            ]
        }
    
    def reset(self) -> None:
        """Reset resolver for a new story."""
        self.conflicts = []
        self._conflict_counter = 0
    
    def save(self, path: Path) -> None:
        """Save conflict history to file."""
        with open(path, 'w') as f:
            json.dump(self.get_conflict_summary(), f, indent=2)
    
    def load(self, path: Path) -> None:
        """Load conflict history from file."""
        with open(path) as f:
            data = json.load(f)
        
        self.conflicts = [
            Conflict(
                id=c["id"],
                universal_rule_id=c["universal_rule"],
                story_rule_id=c.get("story_rule", ""),
                violation_type=c["violation_type"],
                entities_involved=c.get("entities", []),
                event_id="",  # Not stored in summary
                timestamp="",  # Not stored in summary
                resolved=c.get("resolved", False),
                resolution=c.get("resolution", ""),
            )
            for c in data.get("conflicts", [])
        ]
