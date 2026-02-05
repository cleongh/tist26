"""
Chapter Evaluator - High-level chapter evaluation orchestration.

Coordinates ASP conversion, Clingo execution, and result construction.
Provides both batch and sequential evaluation modes.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .domain.chapter_evaluation_result import ChapterEvaluationResult
from .domain.structured_violation import StructuredViolation
from .utils.severity_classifier import classify_severity
from .preprocessors import AspConverter
from .processors import ClingoRunner
from .preprocessors.event_preprocessor import EventPreprocessor

if TYPE_CHECKING:
    from .state_manager import StateManager
    from .registries import RuleRegistry
    from .resolvers import AliasResolver

logger = logging.getLogger(__name__)


class ChapterEvaluator:
    """
    High-level chapter evaluation orchestration.
    
    Provides two evaluation modes:
        - Batch mode: Evaluates all events at once
        - Sequential mode: Evaluates events one at a time
    
    Per LOGIC_DESIGN.md: Python orchestrates, ASP handles all reasoning.
    This class coordinates the evaluation pipeline but delegates all
    logic checking to ClingoRunner.
    """
    
    def __init__(
        self,
        state_manager: 'StateManager',
        rule_registry: 'RuleRegistry',
        alias_resolver: Optional['AliasResolver'] = None,
    ):
        """
        Initialize the chapter evaluator.
        
        Args:
            state_manager: StateManager for state tracking
            rule_registry: RuleRegistry for loading rules
            alias_resolver: Optional AliasResolver for character normalization
        """
        self.state_manager = state_manager
        self.rule_registry = rule_registry
        self.alias_resolver = alias_resolver
        
        # Initialize components
        self.asp_converter = AspConverter(state_manager, alias_resolver)
        self.clingo_runner = ClingoRunner(state_manager, rule_registry)
        self.event_preprocessor = EventPreprocessor(state_manager, alias_resolver)
    
    def evaluate_chapter(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        High-level chapter evaluation combining ASP conversion and Clingo check.
        
        This is the main entry point for batch chapter evaluation.
        Returns raw violations for backward compatibility.
        
        Args:
            structured_data: Structured chapter data from LLM extraction
            chapter_num: Current chapter number
        
        Returns:
            Tuple of (violations list, ASP facts string)
        """
        # Preprocess events
        events = structured_data.get("events", [])
        events = self.event_preprocessor.validate_and_fix_events(events)
        events = self.event_preprocessor.assign_global_event_ids(events, chapter_num)
        structured_data["events"] = events
        
        # Convert to ASP facts
        facts = self.asp_converter.convert(structured_data, chapter_num)
        
        # Run Clingo
        violations = self.clingo_runner.check(facts, chapter_num)
        
        # Update StateManager with persistent facts
        self.state_manager.accumulate_persistent_facts(facts)
        self.state_manager.extract_state_from_facts(facts)
        
        return violations, facts
    
    def evaluate_chapter_structured(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
    ) -> ChapterEvaluationResult:
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
        # Get raw violations and facts
        raw_violations, facts = self.evaluate_chapter(structured_data, chapter_num)
        events = structured_data.get("events", [])
        
        # Convert to structured violations
        structured_violations = self._convert_to_structured_violations(raw_violations)
        
        return ChapterEvaluationResult(
            chapter_num=chapter_num,
            event_count=len(events),
            violations=structured_violations,
            asp_facts=facts,
            evaluation_mode="batch",
        )
    
    def evaluate_chapter_sequential(
        self,
        structured_data: Dict[str, Any],
        chapter_num: int,
        event_executor,  # Avoid circular import
    ) -> ChapterEvaluationResult:
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
            event_executor: EventExecutor instance for event execution
        
        Returns:
            ChapterEvaluationResult with per-event violations
        """
        # Preprocess events
        events = self.event_preprocessor.preprocess_chapter_events(
            structured_data, chapter_num
        )
        
        # Load initial entities
        event_executor._load_initial_entities(structured_data, chapter_num)
        
        # Execute events sequentially
        all_violations = []
        all_state_changes = []
        
        for event in events:
            result = event_executor.execute_event(event)
            
            # Convert to structured violations
            for v in result.violations:
                violation = self._convert_violation_dict_to_structured(
                    v, event.id, event.time, event.source_text
                )
                all_violations.append(violation)
            
            # Track state changes
            for change in result.state_changes:
                all_state_changes.append({
                    "event_id": event.id,
                    "time": event.time,
                    "change": change,
                })
        
        # Build ASP facts for reference
        facts = self.asp_converter.convert(structured_data, chapter_num)
        
        return ChapterEvaluationResult(
            chapter_num=chapter_num,
            event_count=len(events),
            violations=all_violations,
            state_changes=all_state_changes,
            asp_facts=facts,
            evaluation_mode="sequential",
        )
    
    def _convert_to_structured_violations(
        self,
        raw_violations: List[Dict[str, Any]],
    ) -> List[StructuredViolation]:
        """
        Convert raw violation dicts to StructuredViolation objects.
        
        Args:
            raw_violations: List of raw violation dictionaries
            
        Returns:
            List of StructuredViolation objects
        """
        structured = []
        
        for v in raw_violations:
            structured.append(
                self._convert_violation_dict_to_structured(
                    v,
                    v.get("event", ""),
                    self._extract_event_time(v.get("event", "")),
                    v.get("source_text"),
                )
            )
        
        return structured
    
    def _convert_violation_dict_to_structured(
        self,
        v: Dict[str, Any],
        event_id: str,
        event_time: int,
        source_text: Optional[str],
    ) -> StructuredViolation:
        """
        Convert a single violation dict to a StructuredViolation.
        
        Args:
            v: Violation dictionary
            event_id: Event ID
            event_time: Event time
            source_text: Source text (optional)
            
        Returns:
            StructuredViolation object
        """
        # Extract entities from detail
        entities = []
        detail = v.get("detail", "")
        if detail and detail != "unknown":
            entities.append(detail)
        
        # Determine severity
        severity = classify_severity(
            v.get("category", ""),
            v.get("type", "")
        )
        
        return StructuredViolation(
            rule=f"{v.get('category', 'unknown')}/{v.get('type', 'unknown')}",
            category=v.get("category", "unknown"),
            violation_type=v.get("type", "unknown"),
            event_id=event_id,
            event_time=event_time,
            entities=entities,
            severity=severity,
            source_text=source_text,
        )
    
    def _extract_event_time(self, event_id: str) -> int:
        """
        Extract event time from event ID.
        
        Args:
            event_id: Event ID (e.g., "e123")
            
        Returns:
            Event time as integer, 0 if not extractable
        """
        if event_id.startswith('e') and event_id[1:].isdigit():
            return int(event_id[1:])
        return 0
    
    def get_violations_json(self, result: ChapterEvaluationResult) -> str:
        """
        Get violations as JSON string.
        
        Phase 4, Step 4.3: Pure structured output, no LLM interpretation.
        
        Args:
            result: ChapterEvaluationResult from evaluation
        
        Returns:
            JSON string with violations
        """
        return result.to_json()
