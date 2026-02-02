"""
Event Executor - Applies Events Per Timestep

Responsibilities:
    - Process events sequentially
    - Apply state transitions via ASP
    - Invoke Clingo for each event
    - Collect violations per event
    - Convert structured data to ASP facts (Step 3.2)

Per LOGIC_DESIGN.md Section 4:
    - Events are state transitions, not static facts
    - Each event occurs at a specific timestep
    - Events modify the LKG (presence, relationships, items, rules)
    - Events are evaluated sequentially, producing new world states

Per LOGIC_DESIGN.md Section 5 (Step 2):
    For each event:
        - Apply state transition
        - Recompute derived facts
        - Enforce constraints
        - Detect violations

Phase 3 Refactoring (Step 3.2):
    - Move _to_asp() conversion here
    - Sequential event processing: one event = one state transition

Phase 4 Refactoring (Pipeline):
    Step 4.1: evaluate_chapter() outputs structured JSON only
    Step 4.2: evaluate_chapter_sequential() for per-event evaluation
    Step 4.3: No Python-encoded story logic, no LLM interpretation
    
    Anti-patterns REMOVED:
        - Python conditionals encoding story logic (e.g., "if fantasy world...")
        - LLM interpretation of violations (was Step 6 in old pipeline)
        - Natural language error generation
    
    Output format per LOGIC_DESIGN.md Section 5.5:
        - Structured JSON only
        - Violated rule + entities + event index + severity
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING
from pathlib import Path
from enum import Enum
import tempfile
import os
import re
import json

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult

from .asp_diagnostics import log_asp_universe
from .movement_continuity_guard import (
    MovementContinuityGuard,
    MovementContinuityResult,
    generate_transition_asp_facts,
)

if TYPE_CHECKING:
    from .state_manager import StateManager
    from .rule_registry import RuleRegistry


# =============================================================================
# STRUCTURED OUTPUT TYPES (Phase 4, Step 4.1 + Phase 5, Step 5.1 + Phase 7)
# Per LOGIC_DESIGN.md Section 5.5: Output is structured JSON only
# Phase 7: Enhanced diagnostics with canonical IDs, aliases, item lifecycle
# =============================================================================


@dataclass
class EntityDiagnosticInfo:
    """
    Phase 7: Enhanced entity information for diagnostics.
    
    Ensures all reported issues reference:
        - Canonical IDs only
        - Aliases (if relevant)
        - Item relevance and lifecycle (for items)
    """
    canonical_id: str
    entity_type: str  # "character", "item", "location"
    aliases: List[str] = field(default_factory=list)
    # Item-specific fields (Phase 7)
    item_relevance: Optional[str] = None  # "causal", "latent", "background"
    item_lifecycle: Optional[str] = None  # "introduced", "carried", "used", "destroyed", etc.
    item_carrier: Optional[str] = None  # Character carrying the item
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "canonical_id": self.canonical_id,
            "entity_type": self.entity_type,
        }
        if self.aliases:
            result["aliases"] = self.aliases
        if self.item_relevance:
            result["relevance"] = self.item_relevance
        if self.item_lifecycle:
            result["lifecycle"] = self.item_lifecycle
        if self.item_carrier:
            result["carrier"] = self.item_carrier
        return result

class ViolationSeverity(Enum):
    """Severity of a violation per LOGIC_DESIGN.md."""
    HARD = "hard"           # Hard contradiction (impossible in story world)
    SOFT = "soft"           # Soft inconsistency (unusual but possible)
    WARNING = "warning"     # Potential issue (may be intentional)


@dataclass
class Provenance:
    """
    Provenance tracking for conclusions (Phase 5, Step 5.1).
    
    Tracks how a conclusion was reached for full auditability.
    """
    rule_id: str                        # ID of the rule that produced this conclusion
    rule_layer: str                     # "universal", "learned", or "story"
    chapter: int                        # Chapter where this was concluded
    event_id: Optional[str] = None      # Event that triggered this (if applicable)
    derived_from: List[str] = field(default_factory=list)  # IDs of facts used to derive this
    timestamp: str = ""                 # When this was concluded
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "rule_id": self.rule_id,
            "rule_layer": self.rule_layer,
            "chapter": self.chapter,
            "event_id": self.event_id,
            "derived_from": self.derived_from,
            "timestamp": self.timestamp,
        }


@dataclass
class StructuredViolation:
    """
    Structured violation output per LOGIC_DESIGN.md Section 5.5.
    
    Each issue includes:
        - Violated rule
        - Entities involved (Phase 7: with canonical IDs and aliases)
        - Event index / time
        - Severity
        - Provenance (Phase 5)
    
    NO natural language interpretation - pure structured data.
    
    Phase 7: All entity references use canonical IDs. Entity info includes
    aliases and item lifecycle/relevance when applicable.
    """
    rule: str                           # The rule that was violated
    category: str                       # coherence, causality, temporal, location, emotional
    violation_type: str                 # Specific type (dead_agent, impossible_location, etc.)
    event_id: str                       # Event that triggered the violation
    event_time: int                     # Timestep of the event
    entities: List[str]                 # Canonical entity IDs involved in the violation
    severity: ViolationSeverity = ViolationSeverity.SOFT
    source_text: Optional[str] = None   # Original text that was evaluated
    provenance: Optional[Provenance] = None  # How this was concluded (Phase 5)
    # Phase 7: Enhanced entity diagnostics
    entity_info: List[EntityDiagnosticInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "rule": self.rule,
            "category": self.category,
            "type": self.violation_type,
            "event_id": self.event_id,
            "event_time": self.event_time,
            "entities": self.entities,
            "severity": self.severity.value,
            "source_text": self.source_text,
        }
        if self.provenance:
            result["provenance"] = self.provenance.to_dict()
        # Phase 7: Include entity diagnostic info
        if self.entity_info:
            result["entity_info"] = [e.to_dict() for e in self.entity_info]
        return result


@dataclass
class ChapterEvaluationResult:
    """
    Structured result of evaluating a chapter.
    
    Per LOGIC_DESIGN.md Section 5.5: Output is structured JSON only.
    
    Contains:
        - List of violations with full metadata
        - State changes applied during evaluation
        - Chapter summary statistics
        - Provenance tracking (Phase 5)
    
    Does NOT contain:
        - Natural language descriptions
        - LLM interpretations
        - Suggested fixes
    """
    chapter_num: int
    event_count: int
    violations: List[StructuredViolation] = field(default_factory=list)
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    asp_facts: str = ""
    evaluation_mode: str = "batch"  # "batch" or "sequential"
    rules_applied: List[str] = field(default_factory=list)  # Rule IDs used (Phase 5)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "chapter_num": self.chapter_num,
            "event_count": self.event_count,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "state_changes": self.state_changes,
            "evaluation_mode": self.evaluation_mode,
            "rules_applied": self.rules_applied,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# CHARACTER ALIAS RESOLUTION
# =============================================================================
# 
# Per LOGIC_DESIGN.md: Aliases are discovered dynamically during extraction
# and managed by AliasResolver. The hardcoded CHARACTER_ALIASES below are
# DEPRECATED and only kept for backward compatibility with legacy code.
#
# The proper flow is:
#   1. LLM extracts entities with aliases from story text
#   2. AliasResolver.register_character() is called during extraction
#   3. AliasResolver.normalize_chapter_output() normalizes all IDs
#   4. EventExecutor receives already-normalized data
#
# When AliasResolver is provided to EventExecutor, it will use dynamic
# resolution. Otherwise, it falls back to these legacy hardcoded aliases.
# =============================================================================

# DEPRECATED: Legacy hardcoded aliases for backward compatibility
# These will be removed once all code paths use AliasResolver
_LEGACY_CHARACTER_ALIASES = {
    # Harry Potter characters - minimal set for tests
    'harry_potter': 'harry',
    'potter': 'harry',
    'ron_weasley': 'ron',
    'hermione_granger': 'hermione',
    'hagrid': 'hagrid',
    'rubeus_hagrid': 'hagrid',
}


def normalize_character_id(char_id: str, alias_resolver=None) -> str:
    """
    Normalize character IDs to canonical form.
    
    Args:
        char_id: The character ID to normalize
        alias_resolver: Optional AliasResolver for dynamic resolution
        
    Returns:
        Canonical character ID
        
    Note:
        If alias_resolver is provided, uses dynamic resolution.
        Otherwise falls back to legacy hardcoded aliases (deprecated).
    """
    if not char_id:
        return char_id
    normalized = char_id.lower().strip()
    
    if alias_resolver is not None:
        return alias_resolver.resolve(normalized)
    
    # Legacy fallback - deprecated
    return _LEGACY_CHARACTER_ALIASES.get(normalized, normalized)


def generate_alias_facts(
    alias_resolver=None,
    active_universe: Optional['ActiveUniverseResult'] = None,
) -> str:
    """
    Generate ASP alias facts for character resolution.
    
    Per LOGIC_DESIGN.md: Python is orchestration only, all logic in ASP.
    This function generates alias/2 facts that ASP uses for alias resolution.
    
    Args:
        alias_resolver: Optional AliasResolver for dynamic aliases
        active_universe: Optional filter - only include aliases for entities in this universe.
        
    Returns:
        ASP facts as a string, e.g.:
            alias(harry_potter, harry).
            alias(potter, harry).
    """
    lines = ["% Character alias facts"]
    all_entities = active_universe.all_entities if active_universe else None
    
    if alias_resolver is not None:
        # Dynamic: generate from AliasResolver's registered aliases
        for canonical_id in alias_resolver.get_all_canonical_ids():
            # Skip if canonical not in active universe (Phase 8.6)
            if all_entities is not None and canonical_id not in all_entities:
                continue
            for alias in alias_resolver.get_aliases(canonical_id):
                if alias != canonical_id:
                    lines.append(f"alias({alias}, {canonical_id}).")
    else:
        # Legacy fallback - deprecated
        lines.append("% (generated from legacy hardcoded aliases - deprecated)")
        for alias_id, canonical_id in _LEGACY_CHARACTER_ALIASES.items():
            if alias_id != canonical_id:
                if all_entities is not None and canonical_id not in all_entities:
                    continue
                lines.append(f"alias({alias_id}, {canonical_id}).")
    
    return "\n".join(lines)


@dataclass
class Event:
    """
    Represents a story event as a state transition.
    
    Events are not static facts - they cause changes to the world state.
    """
    id: str
    event_type: str
    time: int
    agent: Optional[str] = None
    patient: Optional[str] = None
    location: Optional[str] = None
    destination: Optional[str] = None  # For travel events
    source_text: Optional[str] = None
    emotion: Optional[str] = None  # Emotion associated with event
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_asp_facts(self) -> str:
        """Convert event to ASP fact format."""
        lines = [
            f"event({self.id}).",
            f"event_type({self.id}, {self.event_type}).",
            f"event_time({self.id}, {self.time}).",
        ]
        
        if self.agent:
            lines.append(f"agent({self.id}, {self.agent}).")
        if self.patient:
            lines.append(f"patient({self.id}, {self.patient}).")
        if self.location:
            lines.append(f"location({self.id}, {self.location}).")
        if self.destination:
            lines.append(f"event_destination({self.id}, {self.destination}).")
        if self.emotion:
            lines.append(f"event_emotion({self.id}, {self.emotion}).")
        if self.source_text:
            # Escape for ASP string
            escaped = self.source_text.replace('"', '\\"').replace('\n', ' ')[:80]
            lines.append(f'event_source({self.id}, "{escaped}").')
        
        return "\n".join(lines)


@dataclass
class EventResult:
    """Result of executing a single event."""
    event_id: str
    time: int
    violations: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: List[str] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)


class EventExecutor:
    """
    Executes events as state transitions.
    
    For each event:
        1. Convert event to ASP facts
        2. Combine with current world state
        3. Run Clingo with rules
        4. Extract violations and new state
        5. Update StateManager
    
    Does NOT:
        - Encode event logic in Python
        - Make reasoning decisions
        - Filter or interpret violations
    
    Alias Resolution:
        If an AliasResolver is provided, it will be used for dynamic alias
        resolution. Otherwise, falls back to legacy hardcoded aliases.
        The proper pattern is for data to be pre-normalized by calling
        AliasResolver.normalize_chapter_output() before reaching EventExecutor.
    """
    
    def __init__(self, state_manager: 'StateManager', rule_registry: 'RuleRegistry',
                 alias_resolver: 'AliasResolver' = None):
        from .state_manager import StateManager
        from .rule_registry import RuleRegistry
        
        self.state_manager = state_manager
        self.rule_registry = rule_registry
        self.alias_resolver = alias_resolver  # Optional: for dynamic alias resolution
        self._clingo_available = self._check_clingo()
        self._last_continuity_result: Optional[MovementContinuityResult] = None
    
    def set_alias_resolver(self, alias_resolver: 'AliasResolver') -> None:
        """Set the alias resolver for dynamic alias resolution."""
        self.alias_resolver = alias_resolver
    
    def _check_clingo(self) -> bool:
        """Check if Clingo is available."""
        try:
            import clingo
            return True
        except ImportError:
            return False
    
    def _parse_violation(self, atom: Any, default_event_id: str) -> Dict[str, Any]:
        """
        Parse a violation atom from Clingo output into a structured dict.
        
        Handles special compound terms like tt_info for time_travel violations
        to extract detailed debugging information.
        
        Args:
            atom: A Clingo Symbol representing a violation/4 atom
            default_event_id: Event ID to use if violation doesn't specify one
        
        Returns:
            Dict with keys: category, type, event, detail, and additional 
            trace fields for specific violation types
        """
        args = atom.arguments
        category = str(args[0]) if len(args) > 0 else "unknown"
        vtype = str(args[1]) if len(args) > 1 else "unknown"
        event_ref = str(args[2]) if len(args) > 2 else default_event_id
        detail_arg = args[3] if len(args) > 3 else None
        
        violation_dict = {
            "category": category,
            "type": vtype,
            "event": event_ref,
            "detail": str(detail_arg) if detail_arg else "",
        }
        
        # Parse rich detail for time_travel violations
        # Format: tt_info(Character, Loc1, Time1, Loc2, Time2)
        if vtype == "time_travel" and detail_arg is not None:
            try:
                if hasattr(detail_arg, 'name') and detail_arg.name == "tt_info":
                    tt_args = detail_arg.arguments
                    if len(tt_args) >= 5:
                        violation_dict["trace"] = {
                            "character": str(tt_args[0]),
                            "earlier_location": str(tt_args[3]),  # L2 is "earlier" (lower T)
                            "earlier_time": int(str(tt_args[4])),  # T2
                            "later_location": str(tt_args[1]),    # L1 is "later" (higher T)
                            "later_time": int(str(tt_args[2])),   # T1
                        }
            except (ValueError, AttributeError, IndexError):
                # Fallback to string representation if parsing fails
                pass
        
        return violation_dict
    
    def _sanitize_id(self, value: Any) -> str:
        """Sanitize a value for use as an ASP atom."""
        if not value:
            return "unknown"
        s = str(value).lower()
        s = re.sub(r'[^a-z0-9_]', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        if s and s[0].isdigit():
            s = 'n' + s
        return s or "unknown"
    
    def _sanitize_char(self, value: Any) -> str:
        """Sanitize and normalize character ID."""
        s = self._sanitize_id(value)
        if s and s != "unknown":
            # Use AliasResolver if available, else fall back to legacy
            s = normalize_character_id(s, self.alias_resolver)
        return s
    
    def to_asp(
        self,
        data: Dict[str, Any],
        chapter_num: int,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """
        Convert structured JSON to ASP facts.
        
        Extracted from LogicEvaluator._to_asp() per Step 3.2.
        
        Phase 8.8: If active_universe is provided, only emit entity declarations
        (character/item/location_entity predicates) for entities in the universe.
        This prevents ASP grounding explosion by limiting global constants.
        
        Args:
            data: Structured chapter data with entities and events
            chapter_num: Current chapter number
            active_universe: Optional filter - only declare entities in this universe.
                           Other predicates (agent, patient, etc.) are still emitted.
        
        Returns:
            ASP facts as a string
        """
        lines = [f"% Chapter {chapter_num} facts"]
        
        # Get the active universe filter set (if provided)
        universe_entities = active_universe.all_entities if active_universe else None
        
        # Inject alias facts for ASP-based alias resolution
        # Per LOGIC_DESIGN.md: Python orchestrates, ASP handles logic
        # Use AliasResolver if available for dynamic aliases
        lines.append("")
        lines.append(generate_alias_facts(self.alias_resolver, active_universe=active_universe))
        lines.append("")
        
        # Track all character/location/item IDs
        char_ids = set()
        location_ids = set()
        item_ids = set()
        
        entities = data.get("entities", {})
        
        # Process characters
        for char in entities.get("characters", []):
            cid = self._sanitize_char(char.get("id", ""))
            cname = self._sanitize_char(char.get("name", ""))
            
            # Phase 8.8: Only emit character() declarations for entities in active universe
            if cid and cid != "unknown":
                char_ids.add(cid)
                if universe_entities is None or cid in universe_entities:
                    lines.append(f"character({cid}).")
            if cname and cname != "unknown" and cname != cid:
                char_ids.add(cname)
                if universe_entities is None or cname in universe_entities:
                    lines.append(f"character({cname}).")
            
            # Character aliases (Phase 1: store and generate ASP facts)
            # Only emit alias facts if the character is in the universe
            char_key = cid if cid != "unknown" else cname
            if universe_entities is None or char_key in universe_entities:
                for alias in char.get("aliases", []):
                    alias_id = self._sanitize_char(alias)
                    if alias_id and alias_id != "unknown" and alias_id != char_key:
                        lines.append(f"alias({alias_id}, {char_key}).")
            
            # Emotional state - only emit if character is in universe
            emotion = self._sanitize_id(char.get("emotion", ""))
            if emotion and emotion not in ("unknown", "neutral"):
                char_key = cid if cid != "unknown" else cname
                if char_key != "unknown":
                    if universe_entities is None or char_key in universe_entities:
                        lines.append(f"character_emotion({char_key}, {emotion}).")
            
            # Physical state - only emit if character is in universe
            state = self._sanitize_id(char.get("state", ""))
            if state and state not in ("unknown", "normal"):
                char_key = cid if cid != "unknown" else cname
                if char_key != "unknown":
                    if universe_entities is None or char_key in universe_entities:
                        lines.append(f"character_state({char_key}, {state}).")
                        if state == "dead":
                            lines.append(f"is_dead({char_key}).")
            
            # Appearance - only emit if character is in universe
            appearance = self._sanitize_id(char.get("appearance", ""))
            if appearance and appearance not in ("unknown", "normal", "none"):
                char_key = cid if cid != "unknown" else cname
                if char_key != "unknown":
                    if universe_entities is None or char_key in universe_entities:
                        lines.append(f"character_appearance({char_key}, {appearance}).")
        
        # Process items
        for item in entities.get("items", []):
            iid = self._sanitize_id(item.get("id", ""))
            iname = self._sanitize_id(item.get("name", ""))
            
            # Phase 8.8: Only emit item() declarations for entities in active universe
            if iid and iid != "unknown":
                item_ids.add(iid)
                if universe_entities is None or iid in universe_entities:
                    lines.append(f"item({iid}).")
            if iname and iname != "unknown" and iname != iid:
                item_ids.add(iname)
                if universe_entities is None or iname in universe_entities:
                    lines.append(f"item({iname}).")
            
            item_key = iid if iid != "unknown" else iname
            
            # Item state - only emit if item is in universe
            item_state = self._sanitize_id(item.get("state", ""))
            if item_state and item_state not in ("unknown", "intact"):
                if item_key != "unknown":
                    if universe_entities is None or item_key in universe_entities:
                        lines.append(f"item_state({item_key}, {item_state}).")
            
            # Item relevance (Phase 1: store for Chekhov tracking) - only if in universe
            relevance = self._sanitize_id(item.get("relevance", ""))
            if relevance and relevance in ("causal", "latent"):
                if item_key != "unknown":
                    if universe_entities is None or item_key in universe_entities:
                        lines.append(f"item_relevance({item_key}, {relevance}).")
        
        # Legacy support for "objects" field
        for obj in entities.get("objects", []):
            oid = self._sanitize_id(obj.get("id", obj.get("name", "")))
            if oid and oid != "unknown":
                item_ids.add(oid)
                # Phase 8.8: Only emit object() declarations for entities in active universe
                if universe_entities is None or oid in universe_entities:
                    lines.append(f"object({oid}).")
        
        # Process locations
        for loc in entities.get("locations", []):
            lid = self._sanitize_id(loc.get("id", ""))
            lname = self._sanitize_id(loc.get("name", ""))
            
            # Phase 8.8: Only emit location_entity() declarations for entities in active universe
            if lid and lid != "unknown":
                location_ids.add(lid)
                if universe_entities is None or lid in universe_entities:
                    lines.append(f"location_entity({lid}).")
            if lname and lname != "unknown" and lname != lid:
                location_ids.add(lname)
                if universe_entities is None or lname in universe_entities:
                    lines.append(f"location_entity({lname}).")
            
            loc_key = lid if lid != "unknown" else lname
            
            # Connections - only emit if location is in universe
            if universe_entities is None or loc_key in universe_entities:
                for conn in loc.get("connections", []):
                    conn_id = self._sanitize_id(conn)
                    if conn_id and conn_id != "unknown" and loc_key != "unknown":
                        lines.append(f"connected({loc_key}, {conn_id}).")
                        lines.append(f"connected({conn_id}, {loc_key}).")
                
                # Containment - only emit if location is in universe
                for sub in loc.get("contains", []):
                    sub_id = self._sanitize_id(sub)
                    if sub_id and sub_id != "unknown" and loc_key != "unknown":
                        lines.append(f"contains({loc_key}, {sub_id}).")
                        lines.append(f"connected({loc_key}, {sub_id}).")
                        lines.append(f"connected({sub_id}, {loc_key}).")
        
        # Process relationships - only emit if both characters are in universe
        for rel in entities.get("relationships", []):
            from_char = self._sanitize_char(rel.get("from", ""))
            to_char = self._sanitize_char(rel.get("to", ""))
            rel_type = self._sanitize_id(rel.get("type", "neutral"))
            if from_char != "unknown" and to_char != "unknown" and rel_type != "neutral":
                # Phase 8.8: Only emit relationship facts if both entities are in active universe
                if universe_entities is None or (from_char in universe_entities and to_char in universe_entities):
                    # Use initial_relationship for EC to derive time-indexed relationship/4
                    lines.append(f"initial_relationship({from_char}, {to_char}, {rel_type}).")
                    # Also keep relationship/3 for backward compatibility with simpler rules
                    lines.append(f"relationship({from_char}, {to_char}, {rel_type}).")
        
        # Process initial_rules - convert relationship predicates to relationship facts
        # This handles rules like {"subject": "mr_dursley", "predicate": "hostile", "object": "harry_potter"}
        for rule in data.get("initial_rules", []):
            subject = self._sanitize_char(rule.get("subject", ""))
            predicate = self._sanitize_id(rule.get("predicate", ""))
            obj = self._sanitize_char(rule.get("object", ""))
            
            if subject != "unknown" and obj != "unknown" and predicate not in ("unknown", ""):
                # Phase 8.8: Only emit relationship facts if both entities are in active universe
                if universe_entities is None or (subject in universe_entities and obj in universe_entities):
                    # Map predicate to relationship type (hostile, friendly, hates, loves, etc.)
                    rel_type = predicate  # The predicate IS the relationship type
                    lines.append(f"initial_relationship({subject}, {obj}, {rel_type}).")
                    lines.append(f"relationship({subject}, {obj}, {rel_type}).")
        
        # Process events
        event_ids = []
        for i, event in enumerate(data.get("events", [])):
            eid = self._sanitize_id(event.get("global_id", event.get("id", f"e{chapter_num}_{i+1}")))
            event_ids.append(eid)
            
            lines.append(f"event({eid}).")
            etype = self._sanitize_id(event.get("type", "action"))
            lines.append(f"event_type({eid}, {etype}).")
            lines.append(f"event_global({eid}, {etype}, {chapter_num}).")
            
            # Event order and time
            if eid.startswith('e') and eid[1:].isdigit():
                event_num = int(eid[1:])
                lines.append(f"event_order({eid}, {event_num}).")
                # event_time is required by ASP rules (emotional.lp, etc.)
                lines.append(f"event_time({eid}, {event_num}).")
                # time/1 fact for EC framework
                lines.append(f"time({event_num}).")
            
            # Event source text
            source_text = event.get('source_text', '')
            if source_text:
                escaped_source = source_text.replace('"', '\\"').replace('\n', ' ')[:80]
                lines.append(f'event_source({eid}, "{escaped_source}").')
            
            # Agent
            if event.get("agent"):
                agent_id = self._sanitize_char(event['agent'])
                lines.append(f"agent({eid}, {agent_id}).")
                # Phase 8.8: Only emit character() declaration if agent is in active universe
                if agent_id not in char_ids and agent_id != "unknown":
                    char_ids.add(agent_id)
                    if universe_entities is None or agent_id in universe_entities:
                        lines.append(f"character({agent_id}).")
            
            # Patient
            if event.get("patient"):
                patient_raw = event['patient']
                patient_id = self._sanitize_id(patient_raw)
                if patient_id in char_ids or patient_id not in item_ids:
                    patient_id = self._sanitize_char(patient_raw)
                lines.append(f"patient({eid}, {patient_id}).")
                # Phase 8.8: Only emit is_dead if patient is in active universe
                if etype == "death":
                    if universe_entities is None or patient_id in universe_entities:
                        lines.append(f"is_dead({patient_id}).")
            
            # Location
            if event.get("location"):
                loc_id = self._sanitize_id(event['location'])
                lines.append(f"location({eid}, {loc_id}).")
                # Phase 8.8: Only emit location_entity() declaration if location is in active universe
                if loc_id not in location_ids and loc_id != "unknown":
                    location_ids.add(loc_id)
                    if universe_entities is None or loc_id in universe_entities:
                        lines.append(f"location_entity({loc_id}).")
            
            # Event emotion
            event_emotion = self._sanitize_id(event.get("emotion", ""))
            if event_emotion and event_emotion != "unknown":
                lines.append(f"event_emotion({eid}, {event_emotion}).")
            
            # Temporal ordering
            after_event = self._sanitize_id(event.get("after", ""))
            if after_event and after_event not in ("unknown", "null"):
                lines.append(f"must_precede({after_event}, {eid}).")
        
        # Generate implicit time ordering
        for i in range(len(event_ids) - 1):
            lines.append(f"time_order({event_ids[i]}, {event_ids[i+1]}).")
        
        # Movement Continuity Guard: detect and bridge implicit movement gaps
        # Per LOGIC_DESIGN.md: Python orchestrates, adds derived facts - ASP handles logic
        events_list = data.get("events", [])
        if events_list:
            guard = MovementContinuityGuard(chapter_num=chapter_num)
            continuity_result = guard.analyze_events(events_list, self._sanitize_id)
            if continuity_result.derived_transitions:
                lines.append(generate_transition_asp_facts(continuity_result))
                # Store result for audit access
                self._last_continuity_result = continuity_result
        
        # Add story rules from StateManager
        lines.append(f"\n% Story rules (dynamic, established by events)")
        lines.append(f"event_order(e0, 0).  % Initial state event")
        
        current_state = self.state_manager.get_current_state()
        for rule in current_state.story_rules:
            if rule.valid:
                lines.append(self._rule_to_asp(rule))
        
        return "\n".join(lines)
    
    def _rule_to_asp(self, rule) -> str:
        """Convert a StoryRule to ASP fact."""
        if rule.rule_type == 'relationship':
            return f"relationship_rule({rule.subject}, {rule.predicate}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'trait':
            return f"trait_rule({rule.subject}, {rule.predicate}, {rule.established_by})."
        elif rule.rule_type == 'location':
            return f"location_rule({rule.subject}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'possession':
            return f"possession_rule({rule.subject}, {rule.object}, {rule.established_by})."
        elif rule.rule_type == 'temporal':
            return f"temporal_rule({rule.subject}, must_precede, {rule.object}, {rule.established_by})."
        return ""
    
    def create_event(self, event_data: Dict[str, Any], time: int, 
                      chapter_num: int = 0) -> Event:
        """
        Create an Event from extracted event data.
        
        Args:
            event_data: Dict with keys like 'id', 'type', 'agent', 'patient', 'location'
            time: The timestep for this event
            chapter_num: Current chapter number (for ID generation)
        
        Returns:
            Event object ready for execution
        """
        # Use global_id if available (assigned by StateManager), else generate
        event_id = event_data.get('global_id')
        if not event_id:
            event_id = event_data.get('id', f'e{chapter_num}_{time}')
        
        return Event(
            id=self._sanitize_id(event_id),
            event_type=self._sanitize_id(event_data.get('type', 'action')),
            time=time,
            agent=self._sanitize_char(event_data.get('agent')) if event_data.get('agent') else None,
            patient=self._sanitize_id(event_data.get('patient')) if event_data.get('patient') else None,
            location=self._sanitize_id(event_data.get('location')) if event_data.get('location') else None,
            destination=self._sanitize_id(event_data.get('destination')) if event_data.get('destination') else None,
            source_text=event_data.get('source_text'),
            emotion=self._sanitize_id(event_data.get('emotion')) if event_data.get('emotion') else None,
            metadata=event_data.get('metadata', {})
        )
    
    def assign_global_event_ids(self, events: List[Dict[str, Any]], 
                                 chapter_num: int) -> List[Dict[str, Any]]:
        """
        Assign continuous global IDs to events and log them.
        
        Event IDs are continuous across all chapters (e1, e2, ..., eN).
        Extracted from LogicEvaluator._assign_global_event_ids()
        """
        for event in events:
            event_id = self.state_manager.log_event(event, chapter_num)
            event['global_id'] = event_id
            event['chapter'] = chapter_num
        
        return events
    
    def validate_and_fix_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate and fix extracted events post-processing.
        Fixes common LLM extraction errors without deleting valid events.
        
        Extracted from LogicEvaluator._validate_and_fix_events()
        """
        # Actions that logically require no patient (reflexive/intransitive)
        no_patient_actions = {
            'travel', 'walk', 'run', 'fly', 'drive', 'move', 'go', 'leave', 'arrive',
            'escape', 'flee', 'return', 'enter', 'exit', 'climb', 'jump', 'land',
            'die', 'dies', 'died', 'death', 'faint', 'collapse', 'wake', 'sleep',
            'rest', 'hide', 'wait', 'stand', 'sit', 'kneel', 'bow', 'fall',
            'think', 'read', 'write', 'sing', 'cry', 'laugh', 'scream', 'shout',
            'practice', 'train', 'study', 'work', 'eat', 'drink',
            'discover', 'realize', 'understand', 'learn', 'notice', 'observe',
        }
        
        fixed_events = []
        for event in events:
            agent = event.get('agent')
            patient = event.get('patient')
            event_type = event.get('type', '').lower()
            
            # Fix: If agent == patient, decide based on action type
            if agent and patient and str(agent).lower() == str(patient).lower():
                if event_type in no_patient_actions:
                    event['patient'] = None
            
            fixed_events.append(event)
        
        return fixed_events
    
    def execute_event(self, event: Event) -> EventResult:
        """
        Execute a single event as a state transition.
        
        This is the core of sequential evaluation:
            1. Get current world state from StateManager
            2. Combine with event facts
            3. Run Clingo to detect violations and derive new facts
            4. Update world state
        
        Args:
            event: The event to execute
        
        Returns:
            EventResult with violations and state changes
        """
        result = EventResult(event_id=event.id, time=event.time)
        
        if not self._clingo_available:
            return result
        
        import clingo
        
        # Build ASP program
        program_parts = []
        
        # 1. Current world state
        program_parts.append(self.state_manager.get_asp_facts_for_clingo())
        
        # 2. Event facts
        program_parts.append(f"\n% Event {event.id} at time {event.time}")
        program_parts.append(event.to_asp_facts())
        
        combined_facts = "\n".join(program_parts)
        
        # Write facts to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined_facts)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load rules from registry
            for rule_file in self.rule_registry.get_active_rule_files():
                if rule_file.exists():
                    ctl.load(str(rule_file))
            
            # Load facts
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            # Solve and collect results
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        # Collect violations
                        if atom.name == "violation":
                            violation_dict = self._parse_violation(atom, event.id)
                            result.violations.append(violation_dict)
                        
                        # Collect state changes (for updating world state)
                        if atom.name == "state_change":
                            result.state_changes.append(str(atom))
                        
                        # Collect derived facts
                        if atom.name in ("present", "carries", "relationship"):
                            result.derived_facts.append(str(atom))
            
            # Apply state changes to StateManager
            self._apply_state_changes(event, result)
            
        except Exception as e:
            result.violations.append({
                "category": "system",
                "type": "clingo_error",
                "event": event.id,
                "detail": str(e),
            })
        finally:
            os.unlink(facts_path)
        
        return result
    
    def _apply_state_changes(self, event: Event, result: EventResult) -> None:
        """
        Apply state changes from event execution to the StateManager.
        
        Updates:
            - Character locations (via presence)
            - Character deaths
            - New relationships
            - Item possession
        """
        # Track death events
        if event.event_type in ('die', 'dies', 'died', 'death', 'kill', 'murder'):
            if event.patient:
                self.state_manager.mark_dead(event.patient)
            elif event.agent:
                self.state_manager.mark_dead(event.agent)
        
        # Track location changes
        if event.location and event.agent:
            self.state_manager.add_relation(
                predicate="present",
                args=(event.agent, event.location),
                source_event=event.id
            )
        
        # Advance time for next event
        self.state_manager.advance_time()
    
    def execute_events_sequential(self, events: List[Event]) -> List[EventResult]:
        """
        Execute a sequence of events in order.
        
        Per LOGIC_DESIGN.md Section 4:
            Events are evaluated sequentially, and each produces a new world state.
        
        Args:
            events: List of events to execute in order
        
        Returns:
            List of EventResults, one per event
        """
        results = []
        
        for event in events:
            result = self.execute_event(event)
            results.append(result)
        
        return results
    
    def execute_chapter_events(self, chapter_data: Dict[str, Any]) -> Tuple[List[EventResult], List[Dict]]:
        """
        Execute all events from a chapter.
        
        Args:
            chapter_data: Structured chapter data with 'events' list
        
        Returns:
            Tuple of (list of EventResults, combined violations list)
        """
        events = []
        for i, event_data in enumerate(chapter_data.get('events', [])):
            event = self.create_event(event_data, time=self.state_manager.current_time + i)
            events.append(event)
        
        results = self.execute_events_sequential(events)
        
        # Combine all violations
        all_violations = []
        for result in results:
            all_violations.extend(result.violations)
        
        return results, all_violations
    
    def check_with_clingo(self, facts: str, chapter_num: int) -> List[Dict[str, Any]]:
        """
        Use Clingo to find violations in batch mode.
        
        This is a batch evaluation mode (like LogicEvaluator._check_with_clingo)
        as opposed to the sequential execute_event() mode.
        
        Extracted from LogicEvaluator._check_with_clingo() per Step 3.2.
        
        Args:
            facts: ASP facts string (from to_asp())
            chapter_num: Current chapter number
        
        Returns:
            List of violation dictionaries
        """
        violations = []
        
        if not self._clingo_available:
            return violations
        
        import clingo
        
        # Get cross-chapter state facts
        cross_chapter_facts = self.state_manager.get_cross_chapter_state_facts()
        
        # Combine all knowledge
        program_parts = [facts]
        
        # Add cross-chapter state
        if cross_chapter_facts:
            program_parts.append("\n% Cross-chapter state:")
            program_parts.extend(cross_chapter_facts)
        
        # Add accumulated persistent facts
        if self.state_manager.accumulated_facts:
            program_parts.append("\n% Previously introduced entities:")
            program_parts.extend(self.state_manager.accumulated_facts)
        
        combined = "\n".join(program_parts)
        
        # Phase 8.8: Log ASP universe size diagnostics (optional, no overhead when disabled)
        log_asp_universe(combined, chapter_num)
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined)
            facts_path = f.name
        
        try:
            ctl = clingo.Control(["--warn=none"])
            
            # Load rules from registry
            rules_loaded = 0
            for rule_file in self.rule_registry.get_active_rule_files():
                if rule_file.exists():
                    ctl.load(str(rule_file))
                    rules_loaded += 1
            
            if rules_loaded == 0:
                violations.append({
                    "category": "system",
                    "type": "no_rules_loaded",
                    "event": "none",
                    "detail": "No rule files were loaded",
                })
            
            ctl.load(facts_path)
            ctl.ground([("base", [])])
            
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "violation":
                            parts = [str(arg) for arg in atom.arguments]
                            event_id = parts[2] if len(parts) > 2 else ""
                            
                            # Try to find source text for the event
                            source_text = ""
                            if event_id:
                                source_pattern = f'event_source({event_id}, "'
                                for line in combined.split('\n'):
                                    if source_pattern in line:
                                        try:
                                            start = line.index('"') + 1
                                            end = line.rindex('"')
                                            source_text = line[start:end]
                                        except ValueError:
                                            pass
                                        break
                            
                            violations.append({
                                "category": parts[0] if len(parts) > 0 else "unknown",
                                "type": parts[1] if len(parts) > 1 else "unknown",
                                "event": event_id,
                                "detail": parts[3] if len(parts) > 3 else "",
                                "source_text": source_text,
                                "description": f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
                            })
                            
        except Exception as e:
            violations.append({
                "category": "system",
                "type": "clingo_error",
                "event": "none",
                "detail": str(e),
            })
        finally:
            os.unlink(facts_path)
        
        return violations
    
    def evaluate_chapter(self, structured_data: Dict[str, Any], 
                         chapter_num: int) -> Tuple[List[Dict[str, Any]], str]:
        """
        High-level chapter evaluation combining ASP conversion and Clingo check.
        
        This is the main entry point for batch chapter evaluation.
        
        Args:
            structured_data: Structured chapter data from LLM extraction
            chapter_num: Current chapter number
        
        Returns:
            Tuple of (violations list, ASP facts string)
        """
        # Assign global event IDs
        events = structured_data.get("events", [])
        events = self.validate_and_fix_events(events)
        events = self.assign_global_event_ids(events, chapter_num)
        structured_data["events"] = events
        
        # Convert to ASP facts
        facts = self.to_asp(structured_data, chapter_num)
        
        # Run Clingo
        violations = self.check_with_clingo(facts, chapter_num)
        
        # Update StateManager with persistent facts
        self.state_manager.accumulate_persistent_facts(facts)
        self.state_manager.extract_state_from_facts(facts)
        
        return violations, facts

    # =========================================================================
    # PHASE 4: PIPELINE REFACTORING
    # =========================================================================
    
    def evaluate_chapter_structured(self, structured_data: Dict[str, Any], 
                                     chapter_num: int) -> ChapterEvaluationResult:
        """
        Evaluate chapter and return structured JSON output only.
        
        Phase 4, Step 4.1: Refactored evaluate_chapter()
        
        Changes from old pipeline:
            - NO Python-encoded logic decisions
            - ALL reasoning delegated to Clingo
            - Output is structured JSON only (no natural language)
            - NO LLM interpretation step
        
        Args:
            structured_data: Structured chapter data from LLM extraction
            chapter_num: Current chapter number
        
        Returns:
            ChapterEvaluationResult with structured violations
        """
        # Assign global event IDs
        events = structured_data.get("events", [])
        events = self.validate_and_fix_events(events)
        events = self.assign_global_event_ids(events, chapter_num)
        structured_data["events"] = events
        
        # Convert to ASP facts
        facts = self.to_asp(structured_data, chapter_num)
        
        # Run Clingo (all reasoning happens here, not in Python)
        raw_violations = self.check_with_clingo(facts, chapter_num)
        
        # Update StateManager with persistent facts
        self.state_manager.accumulate_persistent_facts(facts)
        self.state_manager.extract_state_from_facts(facts)
        
        # Convert to structured violations (Phase 4 output format)
        structured_violations = []
        for v in raw_violations:
            # Extract entities from event facts
            entities = []
            event_id = v.get("event", "")
            detail = v.get("detail", "")
            
            if detail and detail != "unknown":
                entities.append(detail)
            
            # Look up event info for time
            event_time = 0
            if event_id.startswith('e') and event_id[1:].isdigit():
                event_time = int(event_id[1:])
            
            # Determine severity based on category
            severity = self._classify_severity(v.get("category", ""), v.get("type", ""))
            
            structured_violations.append(StructuredViolation(
                rule=f"{v.get('category', 'unknown')}/{v.get('type', 'unknown')}",
                category=v.get("category", "unknown"),
                violation_type=v.get("type", "unknown"),
                event_id=event_id,
                event_time=event_time,
                entities=entities,
                severity=severity,
                source_text=v.get("source_text"),
            ))
        
        return ChapterEvaluationResult(
            chapter_num=chapter_num,
            event_count=len(events),
            violations=structured_violations,
            asp_facts=facts,
            evaluation_mode="batch",
        )
    
    def evaluate_chapter_sequential(self, structured_data: Dict[str, Any], 
                                     chapter_num: int) -> ChapterEvaluationResult:
        """
        Evaluate chapter with sequential per-event evaluation.
        
        Phase 4, Step 4.2: Sequential Evaluation
        
        Per LOGIC_DESIGN.md Section 5.2:
            For each event:
                - Apply state transition
                - Recompute derived facts
                - Enforce constraints
                - Detect violations
        
        Each event produces a new world state. Violations are detected
        per-event with exact timestep information.
        
        Args:
            structured_data: Structured chapter data from LLM extraction
            chapter_num: Current chapter number
        
        Returns:
            ChapterEvaluationResult with per-event violations
        """
        # Validate and prepare events
        events_data = structured_data.get("events", [])
        events_data = self.validate_and_fix_events(events_data)
        events_data = self.assign_global_event_ids(events_data, chapter_num)
        structured_data["events"] = events_data
        
        # Extract entities for initial state (before first event)
        self._load_initial_entities(structured_data, chapter_num)
        
        # Convert events to Event objects
        events = []
        for i, event_data in enumerate(events_data):
            time = self.state_manager.current_time + i
            event = self.create_event(event_data, time=time, chapter_num=chapter_num)
            events.append(event)
        
        # Execute events sequentially
        all_violations = []
        all_state_changes = []
        
        for event in events:
            result = self.execute_event(event)
            
            # Convert to structured violations
            for v in result.violations:
                entities = []
                if v.get("detail") and v.get("detail") != "unknown":
                    entities.append(v.get("detail"))
                
                severity = self._classify_severity(v.get("category", ""), v.get("type", ""))
                
                all_violations.append(StructuredViolation(
                    rule=f"{v.get('category', 'unknown')}/{v.get('type', 'unknown')}",
                    category=v.get("category", "unknown"),
                    violation_type=v.get("type", "unknown"),
                    event_id=event.id,
                    event_time=event.time,
                    entities=entities,
                    severity=severity,
                    source_text=event.source_text,
                ))
            
            # Track state changes
            for change in result.state_changes:
                all_state_changes.append({
                    "event_id": event.id,
                    "time": event.time,
                    "change": change,
                })
        
        # Build ASP facts for reference
        facts = self.to_asp(structured_data, chapter_num)
        
        return ChapterEvaluationResult(
            chapter_num=chapter_num,
            event_count=len(events),
            violations=all_violations,
            state_changes=all_state_changes,
            asp_facts=facts,
            evaluation_mode="sequential",
        )
    
    def _load_initial_entities(self, structured_data: Dict[str, Any], 
                                chapter_num: int) -> None:
        """
        Load initial entities into StateManager before event evaluation.
        
        This establishes the initial world state for sequential evaluation.
        """
        entities = structured_data.get("entities", {})
        
        # Add characters
        for char in entities.get("characters", []):
            char_id = self._sanitize_char(char.get("id", "") or char.get("name", ""))
            if char_id and char_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=char_id,
                    entity_type="character",
                    chapter=chapter_num,
                )
                
                # Add character state if dead
                state = char.get("state", "")
                if state == "dead":
                    self.state_manager.mark_dead(char_id)
        
        # Add locations
        for loc in entities.get("locations", []):
            loc_id = self._sanitize_id(loc.get("id", "") or loc.get("name", ""))
            if loc_id and loc_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=loc_id,
                    entity_type="location",
                    chapter=chapter_num,
                )
        
        # Add items
        for item in entities.get("items", []):
            item_id = self._sanitize_id(item.get("id", "") or item.get("name", ""))
            if item_id and item_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=item_id,
                    entity_type="item",
                    chapter=chapter_num,
                )
        
        # Add relationships
        for rel in entities.get("relationships", []):
            from_char = self._sanitize_char(rel.get("from", ""))
            to_char = self._sanitize_char(rel.get("to", ""))
            rel_type = self._sanitize_id(rel.get("type", "neutral"))
            if from_char != "unknown" and to_char != "unknown":
                self.state_manager.add_relationship(from_char, to_char, rel_type, chapter_num)
    
    def _classify_severity(self, category: str, violation_type: str) -> ViolationSeverity:
        """
        Classify violation severity based on category and type.
        
        Per LOGIC_DESIGN.md Section 5.5:
            - Hard contradiction: impossible in story world
            - Soft inconsistency: unusual but possible
            - Warning: potential issue
        
        ALL classification is based on structural rules, NOT Python heuristics
        about story content (e.g., no "if fantasy world then..." logic).
        """
        # Hard contradictions (impossible regardless of story type)
        hard_types = {
            "dead_agent", "dead_patient",       # Dead characters can't act
            "invalid_time_order",                # Temporal impossibility
            "circular_dependency",               # Logical impossibility
            "self_contradiction",                # Direct contradiction
        }
        
        if violation_type in hard_types:
            return ViolationSeverity.HARD
        
        # System errors are hard
        if category == "system":
            return ViolationSeverity.HARD
        
        # Soft inconsistencies (unusual but story might explain)
        soft_categories = {"emotional", "coherence"}
        if category in soft_categories:
            return ViolationSeverity.SOFT
        
        # Default to warning for unknown types
        return ViolationSeverity.WARNING
    
    def get_violations_json(self, result: ChapterEvaluationResult) -> str:
        """
        Get violations as JSON string.
        
        Phase 4, Step 4.3: Pure structured output, no LLM interpretation.
        
        This replaces the old _interpret_violations() anti-pattern that used
        LLM to convert violations to natural language.
        
        Args:
            result: ChapterEvaluationResult from evaluation
        
        Returns:
            JSON string with violations
        """
        return result.to_json()
