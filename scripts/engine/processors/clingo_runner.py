"""
Clingo Runner - Single point for all Clingo ASP solver operations.

Responsibilities:
    - Run Clingo for batch violation detection
    - Run Clingo for sequential event execution
    - Manage rule loading and fact preparation
    - Extract violations, state changes, and derived facts

Per LOGIC_DESIGN.md: Python orchestrates, ASP handles all reasoning.
This class is the ONLY place where Clingo should be invoked.
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_manager import StateManager
    from ..registries import RuleRegistry
    from ..domain import Event, EventResult

logger = logging.getLogger(__name__)

# Diagnostic logging for ASP universe size (Phase 8.8)
ASP_UNIVERSE_LOGGING_ENABLED = os.environ.get('ASP_UNIVERSE_LOGGING', '').lower() == 'true'


@dataclass
class ClingoExecutionResult:
    """Result of a Clingo execution."""
    violations: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: List[str] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
    success: bool = True
    error_message: str = ""


class ClingoRunner:
    """
    Central runner for all Clingo ASP solver operations.
    
    Per LOGIC_DESIGN.md: Python orchestrates, ASP handles all reasoning.
    This class is the ONLY place where Clingo should be invoked.
    
    Provides:
        - check(): Batch violation detection
        - execute_event(): Sequential event execution with state tracking
    """
    
    def __init__(
        self,
        state_manager: 'StateManager',
        rule_registry: 'RuleRegistry',
    ):
        """
        Initialize the Clingo runner.
        
        Args:
            state_manager: StateManager for cross-chapter state
            rule_registry: RuleRegistry for loading active rules
        """
        self.state_manager = state_manager
        self.rule_registry = rule_registry
        self._clingo_available = self._check_clingo_available()
    
    def _check_clingo_available(self) -> bool:
        """Check if Clingo is available for import."""
        try:
            import clingo
            return True
        except ImportError:
            logger.warning("Clingo not available - violations cannot be detected")
            return False
    
    @property
    def clingo_available(self) -> bool:
        """Whether Clingo is available."""
        return self._clingo_available
    
    # =========================================================================
    # BATCH MODE - Violation Detection
    # =========================================================================
    
    def check(
        self,
        facts: str,
        chapter_num: int,
    ) -> List[Dict[str, Any]]:
        """
        Use Clingo to find violations in batch mode.
        
        This is a batch evaluation mode as opposed to sequential evaluation.
        
        Args:
            facts: ASP facts string (from AspConverter)
            chapter_num: Current chapter number
        
        Returns:
            List of violation dictionaries
        """
        violations = []
        
        if not self._clingo_available:
            return violations
        
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
        
        # Phase 8.8: Log ASP universe size diagnostics
        self._log_asp_universe(combined, chapter_num)
        
        # Write to temp file
        facts_path = self._write_temp_facts(combined)
        
        try:
            result = self._run_clingo_batch(facts_path, combined)
            violations = result.violations
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
    
    # =========================================================================
    # SEQUENTIAL MODE - Event Execution
    # =========================================================================
    
    def execute_event(
        self,
        event: 'Event',
        event_facts: str,
    ) -> 'ClingoExecutionResult':
        """
        Execute a single event and return all results.
        
        This runs Clingo to:
            1. Detect violations
            2. Extract state changes
            3. Extract derived facts (present, carries, relationship)
        
        Args:
            event: The Event to execute
            event_facts: ASP facts for the event (from AspConverter)
        
        Returns:
            ClingoExecutionResult with violations, state_changes, derived_facts
        """
        result = ClingoExecutionResult()
        
        if not self._clingo_available:
            return result
        
        # Build ASP program
        program_parts = []
        
        # 1. Current world state
        program_parts.append(self.state_manager.get_asp_facts_for_clingo())
        
        # 2. Event facts
        program_parts.append(f"\n% Event {event.id} at time {event.time}")
        program_parts.append(event_facts)
        
        combined_facts = "\n".join(program_parts)
        
        # Write facts to temp file
        facts_path = self._write_temp_facts(combined_facts)
        
        try:
            result = self._run_clingo_sequential(facts_path, event.id)
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            result.violations.append({
                "category": "system",
                "type": "clingo_error",
                "event": event.id,
                "detail": str(e),
            })
        finally:
            os.unlink(facts_path)
        
        return result
    
    # =========================================================================
    # INTERNAL METHODS - Clingo Execution
    # =========================================================================
    
    def _write_temp_facts(self, combined: str) -> str:
        """Write combined facts to a temporary file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            f.write(combined)
            return f.name
    
    def _load_rules(self, ctl) -> int:
        """
        Load rules from registry into Clingo control.
        
        Returns:
            Number of rules loaded
        """
        rules_loaded = 0
        for rule_file in self.rule_registry.get_active_rule_files():
            if rule_file.exists():
                ctl.load(str(rule_file))
                rules_loaded += 1
        return rules_loaded
    
    def _run_clingo_batch(
        self,
        facts_path: str,
        combined: str,
    ) -> ClingoExecutionResult:
        """
        Run Clingo solver in batch mode (violations only).
        
        Args:
            facts_path: Path to temporary facts file
            combined: Combined facts string for source text lookup
            
        Returns:
            ClingoExecutionResult with violations
        """
        import clingo
        
        result = ClingoExecutionResult()
        
        ctl = clingo.Control(["--warn=none"])
        
        # Load rules from registry
        rules_loaded = self._load_rules(ctl)
        
        if rules_loaded == 0:
            result.violations.append({
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
                        violation = self._parse_violation_atom_batch(atom, combined)
                        result.violations.append(violation)
        
        return result
    
    def _run_clingo_sequential(
        self,
        facts_path: str,
        event_id: str,
    ) -> ClingoExecutionResult:
        """
        Run Clingo solver in sequential mode (full extraction).
        
        Args:
            facts_path: Path to temporary facts file
            event_id: Event ID for violation attribution
            
        Returns:
            ClingoExecutionResult with violations, state_changes, derived_facts
        """
        import clingo
        
        result = ClingoExecutionResult()
        
        ctl = clingo.Control(["--warn=none"])
        
        # Load rules from registry
        self._load_rules(ctl)
        
        # Load facts
        ctl.load(facts_path)
        ctl.ground([("base", [])])
        
        # Solve and collect results
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                for atom in model.symbols(shown=True):
                    if atom.name == "violation":
                        violation = self._parse_violation_atom_sequential(atom, event_id)
                        result.violations.append(violation)
                    
                    if atom.name == "state_change":
                        result.state_changes.append(str(atom))
                    
                    if atom.name in ("present", "carries", "relationship"):
                        result.derived_facts.append(str(atom))
        
        return result
    
    # =========================================================================
    # INTERNAL METHODS - Violation Parsing
    # =========================================================================
    
    def _parse_violation_atom_batch(
        self,
        atom,
        combined: str,
    ) -> Dict[str, Any]:
        """
        Parse a violation atom in batch mode (includes source text lookup).
        
        Args:
            atom: Clingo violation atom
            combined: Combined facts string for source text lookup
            
        Returns:
            Violation dictionary
        """
        parts = [str(arg) for arg in atom.arguments]
        event_id = parts[2] if len(parts) > 2 else ""
        
        # Try to find source text for the event
        source_text = self._find_source_text(event_id, combined)
        
        return {
            "category": parts[0] if len(parts) > 0 else "unknown",
            "type": parts[1] if len(parts) > 1 else "unknown",
            "event": event_id,
            "detail": parts[3] if len(parts) > 3 else "",
            "source_text": source_text,
            "description": f"Violation: {parts[1] if len(parts) > 1 else 'unknown'}",
        }
    
    def _parse_violation_atom_sequential(
        self,
        atom,
        default_event_id: str,
    ) -> Dict[str, Any]:
        """
        Parse a violation atom in sequential mode (includes trace for time_travel).
        
        Args:
            atom: Clingo violation atom
            default_event_id: Default event ID if not in atom
            
        Returns:
            Violation dictionary
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
        if vtype == "time_travel" and detail_arg is not None:
            self._parse_time_travel_trace(detail_arg, violation_dict)
        
        return violation_dict
    
    def _parse_time_travel_trace(
        self,
        detail_arg,
        violation_dict: Dict[str, Any],
    ) -> None:
        """
        Parse time_travel violation trace into violation dict.
        
        Args:
            detail_arg: The detail argument from the violation atom
            violation_dict: Dictionary to update with trace info
        """
        try:
            if hasattr(detail_arg, 'name') and detail_arg.name == "tt_info":
                tt_args = detail_arg.arguments
                if len(tt_args) >= 5:
                    violation_dict["trace"] = {
                        "character": str(tt_args[0]),
                        "earlier_location": str(tt_args[3]),
                        "earlier_time": int(str(tt_args[4])),
                        "later_location": str(tt_args[1]),
                        "later_time": int(str(tt_args[2])),
                    }
        except (ValueError, AttributeError, IndexError):
            pass
    
    def _find_source_text(
        self,
        event_id: str,
        combined: str,
    ) -> str:
        """
        Find the source text for an event from the combined facts.
        
        Args:
            event_id: Event ID to search for
            combined: Combined facts string
            
        Returns:
            Source text if found, empty string otherwise
        """
        if not event_id:
            return ""
        
        source_pattern = f'event_source({event_id}, "'
        for line in combined.split('\n'):
            if source_pattern in line:
                try:
                    start = line.index('"') + 1
                    end = line.rindex('"')
                    return line[start:end]
                except ValueError:
                    pass
                break
        
        return ""
    
    # =========================================================================
    # DIAGNOSTICS
    # =========================================================================
    
    def _log_asp_universe(self, combined_facts: str, chapter_num: int) -> None:
        """
        Log ASP universe size diagnostics.
        
        Phase 8.8: Optional diagnostic for tracking ASP grounding size.
        Enable with ASP_UNIVERSE_LOGGING=true environment variable.
        """
        if not ASP_UNIVERSE_LOGGING_ENABLED:
            return
        
        # Count entity declarations
        character_count = combined_facts.count('character(')
        item_count = combined_facts.count('item(')
        location_count = combined_facts.count('location_entity(')
        event_count = combined_facts.count('event(')
        
        logger.info(
            f"[ASP Universe Ch{chapter_num}] "
            f"characters={character_count}, items={item_count}, "
            f"locations={location_count}, events={event_count}"
        )
