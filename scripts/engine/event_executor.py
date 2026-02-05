"""
Event Executor - Applies Events Per Timestep

Responsibilities:
    - Process events sequentially
    - Apply state transitions via ASP
    - Invoke Clingo for each event
    - Collect violations per event

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

Note: ASP conversion, Clingo execution, and chapter evaluation have been
refactored into separate modules:
    - preprocessors/asp_converter.py: AspConverter class
    - processors/clingo_runner.py: ClingoRunner class (single point for Clingo)
    - chapter_evaluator.py: ChapterEvaluator class
    - preprocessors/event_preprocessor.py: EventPreprocessor class
"""

from typing import Dict, List, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .active_universe import ActiveUniverseResult
    from .state_manager import StateManager
    from .registries import RuleRegistry
    from .resolvers import AliasResolver

# Import domain classes
from .domain import (
    EntityDiagnosticInfo,
    ViolationSeverity,
    Provenance,
    StructuredViolation,
    ChapterEvaluationResult,
    Event,
    EventResult,
)

# Import utility functions
from .utils.sanitation import sanitize_id, sanitize_character_id
from .utils.severity_classifier import classify_severity

# Import alias functions from managers
from .managers import normalize_character_id

# Import refactored components
from .preprocessors import AspConverter
from .processors import ClingoRunner
from .preprocessors.event_preprocessor import EventPreprocessor
from .chapter_evaluator import ChapterEvaluator

from .domain import MovementContinuityResult


# =============================================================================
# NOTE: Domain classes (EntityDiagnosticInfo, ViolationSeverity, Provenance,
# StructuredViolation, ChapterEvaluationResult, Event, EventResult) have been
# moved to scripts/engine/domain/ module.
# =============================================================================


# =============================================================================
# NOTE: Character alias resolution functions (normalize_character_id,
# generate_alias_facts) have been moved to scripts/engine/alias_resolver.py
# =============================================================================


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
    
    Note: ASP conversion, chapter evaluation, and event preprocessing have been
    refactored into separate classes. This class now primarily handles:
        - Single event execution (execute_event)
        - Sequential event execution (execute_events_sequential)
        - State changes (apply_state_changes)
    
    For chapter-level evaluation, use ChapterEvaluator instead.
    """
    
    def __init__(
        self,
        state_manager: 'StateManager',
        rule_registry: 'RuleRegistry',
        alias_resolver: 'AliasResolver' = None,
    ):
        self.state_manager = state_manager
        self.rule_registry = rule_registry
        self.alias_resolver = alias_resolver
        self._clingo_available = self._check_clingo()
        self._last_continuity_result: Optional[MovementContinuityResult] = None
        
        # Initialize delegated components
        self._asp_converter = AspConverter(state_manager, alias_resolver)
        self._clingo_runner = ClingoRunner(state_manager, rule_registry)
        self._event_preprocessor = EventPreprocessor(state_manager, alias_resolver)
        self._chapter_evaluator = ChapterEvaluator(state_manager, rule_registry, alias_resolver)
    
    def set_alias_resolver(self, alias_resolver: 'AliasResolver') -> None:
        """Set the alias resolver for dynamic alias resolution."""
        self.alias_resolver = alias_resolver
        self._asp_converter.alias_resolver = alias_resolver
        self._event_preprocessor.alias_resolver = alias_resolver
    
    def _check_clingo(self) -> bool:
        """Check if Clingo is available."""
        try:
            import clingo
            return True
        except ImportError:
            return False
    
    # =========================================================================
    # DELEGATED METHODS - Forward to refactored components
    # =========================================================================
    
    def to_asp(
        self,
        data: Dict[str, Any],
        chapter_num: int,
        active_universe: Optional['ActiveUniverseResult'] = None,
    ) -> str:
        """Convert structured JSON to ASP facts. Delegates to AspConverter."""
        result = self._asp_converter.convert(data, chapter_num, active_universe)
        self._last_continuity_result = self._asp_converter.last_continuity_result
        return result
    
    def check_with_clingo(self, facts: str, chapter_num: int) -> List[Dict[str, Any]]:
        """Use Clingo to find violations in batch mode. Delegates to ClingoRunner."""
        return self._clingo_runner.check(facts, chapter_num)
    
    def create_event(
        self,
        event_data: Dict[str, Any],
        time: int,
        chapter_num: int = 0,
    ) -> Event:
        """Create an Event from extracted event data. Delegates to EventPreprocessor."""
        return self._event_preprocessor.create_event(event_data, time, chapter_num)
    
    def assign_global_event_ids(
        self,
        events: List[Dict[str, Any]],
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """Assign continuous global IDs to events. Delegates to EventPreprocessor."""
        return self._event_preprocessor.assign_global_event_ids(events, chapter_num)
    
    def validate_and_fix_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Validate and fix extracted events. Delegates to EventPreprocessor."""
        return self._event_preprocessor.validate_and_fix_events(events)
    
    def evaluate_chapter(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Evaluate chapter in batch mode. Delegates to ChapterEvaluator."""
        return self._chapter_evaluator.evaluate_chapter(structured_data, chapter_num)
    
    def evaluate_chapter_structured(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> ChapterEvaluationResult:
        """Evaluate chapter with structured output. Delegates to ChapterEvaluator."""
        return self._chapter_evaluator.evaluate_chapter_structured(structured_data, chapter_num)
    
    def evaluate_chapter_sequential(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> ChapterEvaluationResult:
        """Evaluate chapter sequentially. Delegates to ChapterEvaluator."""
        return self._chapter_evaluator.evaluate_chapter_sequential(
            structured_data, chapter_num, self
        )
    
    def get_violations_json(self, result: ChapterEvaluationResult) -> str:
        """Get violations as JSON string. Delegates to ChapterEvaluator."""
        return self._chapter_evaluator.get_violations_json(result)
    
    # =========================================================================
    # CORE EVENT EXECUTION METHODS - Kept in this class
    # =========================================================================
    
    def execute_event(self, event: Event) -> EventResult:
        """
        Execute a single event as a state transition.
        
        This is the core of sequential evaluation:
            1. Get current world state from StateManager
            2. Combine with event facts
            3. Run Clingo to detect violations and derive new facts
            4. Update world state
        """
        result = EventResult(event_id=event.id, time=event.time)
        
        if not self._clingo_available:
            return result
        
        # Convert event to ASP facts
        event_facts = self._event_to_asp_facts(event)
        
        # Execute via ClingoRunner
        clingo_result = self._clingo_runner.execute_event(event, event_facts)
        
        # Transfer results
        result.violations = clingo_result.violations
        result.state_changes = clingo_result.state_changes
        result.derived_facts = clingo_result.derived_facts
        
        # Apply state changes to StateManager
        self._apply_state_changes(event, result)
        
        return result
    
    def _event_to_asp_facts(self, event: Event) -> str:
        """Convert event to ASP fact format."""
        asp_converter = AspConverter()
        facts = asp_converter.event_to_asp(event)
        return "\n".join(facts)
    
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
        """
        results = []
        for event in events:
            result = self.execute_event(event)
            results.append(result)
        return results
    
    def execute_chapter_events(
        self,
        chapter_data: Dict[str, Any],
    ) -> Tuple[List[EventResult], List[Dict]]:
        """
        Execute all events from a chapter.
        
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
    
    def _load_initial_entities(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> None:
        """
        Load initial entities into StateManager before event evaluation.
        
        This establishes the initial world state for sequential evaluation.
        """
        entities = structured_data.get("entities", {})
        
        # Add characters
        for char in entities.get("characters", []):
            char_id = sanitize_character_id(
                char.get("id", "") or char.get("name", ""),
                self.alias_resolver
            )
            if char_id and char_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=char_id,
                    entity_type="character",
                    chapter=chapter_num,
                )
                if char.get("state", "") == "dead":
                    self.state_manager.mark_dead(char_id)
        
        # Add locations
        for loc in entities.get("locations", []):
            loc_id = sanitize_id(loc.get("id", "") or loc.get("name", ""))
            if loc_id and loc_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=loc_id,
                    entity_type="location",
                    chapter=chapter_num,
                )
        
        # Add items
        for item in entities.get("items", []):
            item_id = sanitize_id(item.get("id", "") or item.get("name", ""))
            if item_id and item_id != "unknown":
                self.state_manager.add_entity(
                    entity_id=item_id,
                    entity_type="item",
                    chapter=chapter_num,
                )
        
        # Add relationships
        for rel in entities.get("relationships", []):
            from_char = sanitize_character_id(rel.get("from", ""), self.alias_resolver)
            to_char = sanitize_character_id(rel.get("to", ""), self.alias_resolver)
            rel_type = sanitize_id(rel.get("type", "neutral"))
            if from_char != "unknown" and to_char != "unknown":
                self.state_manager.add_relationship(from_char, to_char, rel_type, chapter_num)
