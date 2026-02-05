"""
Movement Resolver

Reduces false time_travel violations by detecting implicit movement between locations.
Per LOGIC_DESIGN.md: Python orchestrates, ASP handles logic. This module adds
derived transition facts, NOT reasoning logic.

Design Principles:
- Minimal bridging: only insert implicit "leave" when necessary
- No distance/duration inference
- Within-chapter only
- All derived transitions are marked and logged
- Does NOT suppress genuine contradictions

The resolver analyzes validated event sequences and inserts implicit leave events
when a character appears at different locations in consecutive events without
explicit movement.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from ..domain import DerivedTransition, MovementContinuityResult
from ..config import EXPLICIT_MOVEMENT_TYPES

logger = logging.getLogger(__name__)


class MovementResolver:
    """
    Analyzes event sequences to detect and bridge implicit movement gaps.
    
    Per LOGIC_DESIGN.md Section 2:
        "Logic-first architecture: ASP is the source of truth"
    
    This resolver does NOT add logic - it adds derived facts that help ASP
    understand implicit movement that the extraction didn't capture.
    """
    
    def __init__(self, chapter_num: int = 1):
        """
        Initialize the resolver for a specific chapter.
        
        Args:
            chapter_num: Current chapter number (transitions are chapter-scoped)
        """
        self.chapter_num = chapter_num
        self._transition_counter = 0
        self._audit_log: List[Dict[str, Any]] = []
    
    def analyze_events(
        self,
        events: List[Dict[str, Any]],
        sanitize_fn: Optional[callable] = None
    ) -> MovementContinuityResult:
        """
        Analyze event sequence and detect implicit movement gaps.
        
        Args:
            events: List of validated events (already normalized)
            sanitize_fn: Optional function to sanitize IDs (from EventExecutor)
        
        Returns:
            MovementContinuityResult with derived transitions
        """
        result = MovementContinuityResult(original_events=events)
        
        if not events:
            return result
        
        # Build per-agent event sequences
        agent_events = self._build_agent_event_sequences(events, sanitize_fn)
        
        result.agents_analyzed = len(agent_events)
        
        # Analyze each agent's event sequence
        for agent, indexed_events in agent_events.items():
            transitions = self._analyze_agent_sequence(agent, indexed_events, events, sanitize_fn)
            result.derived_transitions.extend(transitions)
        
        result.gaps_bridged = len(result.derived_transitions)
        
        # Log summary
        self._log_analysis_summary(result)
        
        return result
    
    def _build_agent_event_sequences(
        self,
        events: List[Dict[str, Any]],
        sanitize_fn: Optional[callable]
    ) -> Dict[str, List[Tuple[int, Dict[str, Any]]]]:
        """Build per-agent event sequences from event list."""
        agent_events: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
        
        for idx, event in enumerate(events):
            agent = event.get("agent")
            if not agent or agent == "unknown":
                continue
            
            # Normalize agent ID if sanitizer provided
            if sanitize_fn:
                agent = sanitize_fn(agent)
            
            if agent not in agent_events:
                agent_events[agent] = []
            agent_events[agent].append((idx, event))
        
        return agent_events
    
    def _log_analysis_summary(self, result: MovementContinuityResult) -> None:
        """Log summary of movement analysis."""
        if result.derived_transitions:
            logger.info(
                f"MovementResolver: Chapter {self.chapter_num} - "
                f"Bridged {result.gaps_bridged} movement gaps for "
                f"{result.agents_analyzed} agents"
            )
            for t in result.derived_transitions:
                self._audit_log.append({
                    "type": "derived_transition",
                    "chapter": self.chapter_num,
                    **t.to_dict()
                })
    
    def _analyze_agent_sequence(
        self,
        agent: str,
        indexed_events: List[Tuple[int, Dict[str, Any]]],
        all_events: List[Dict[str, Any]],
        sanitize_fn: Optional[callable]
    ) -> List[DerivedTransition]:
        """
        Analyze a single agent's event sequence for movement gaps.
        
        Args:
            agent: Sanitized agent ID
            indexed_events: List of (original_index, event) for this agent
            all_events: Full event list (to check for intervening movement)
            sanitize_fn: Optional ID sanitizer
        
        Returns:
            List of derived transitions needed
        """
        transitions = []
        
        for i in range(len(indexed_events) - 1):
            prev_idx, prev_event = indexed_events[i]
            curr_idx, curr_event = indexed_events[i + 1]
            
            transition = self._check_movement_gap(
                agent, prev_idx, prev_event, curr_idx, curr_event, 
                all_events, sanitize_fn
            )
            
            if transition:
                transitions.append(transition)
        
        return transitions
    
    def _check_movement_gap(
        self,
        agent: str,
        prev_idx: int,
        prev_event: Dict[str, Any],
        curr_idx: int,
        curr_event: Dict[str, Any],
        all_events: List[Dict[str, Any]],
        sanitize_fn: Optional[callable]
    ) -> Optional[DerivedTransition]:
        """Check for a movement gap between two consecutive agent events."""
        # Get locations
        prev_loc = prev_event.get("location")
        curr_loc = curr_event.get("location")
        
        # Skip if either location is missing
        if not prev_loc or not curr_loc:
            return None
        if prev_loc == "unknown" or curr_loc == "unknown":
            return None
        
        # Normalize locations if sanitizer provided
        if sanitize_fn:
            prev_loc = sanitize_fn(prev_loc)
            curr_loc = sanitize_fn(curr_loc)
        
        # Skip if same location
        if prev_loc == curr_loc:
            return None
        
        # Check if there's explicit movement between these events
        has_explicit_movement = self._has_explicit_movement_between(
            agent, prev_idx, curr_idx, all_events, sanitize_fn
        )
        
        if has_explicit_movement:
            return None
        
        # No explicit movement found - insert derived transition
        transition = self._create_derived_transition(
            agent=agent,
            from_location=prev_loc,
            to_location=curr_loc,
            prev_event=prev_event,
            curr_event=curr_event,
        )
        
        logger.debug(
            f"Derived transition for {agent}: "
            f"{prev_loc} -> {curr_loc} "
            f"(between {prev_event.get('id', prev_idx)} and {curr_event.get('id', curr_idx)})"
        )
        
        return transition
    
    def _has_explicit_movement_between(
        self,
        agent: str,
        start_idx: int,
        end_idx: int,
        all_events: List[Dict[str, Any]],
        sanitize_fn: Optional[callable]
    ) -> bool:
        """
        Check if there's an explicit movement event between two indices.
        
        Args:
            agent: Agent to check
            start_idx: Start event index (exclusive)
            end_idx: End event index (exclusive)
            all_events: Full event list
            sanitize_fn: Optional ID sanitizer
        
        Returns:
            True if explicit movement event exists for this agent
        """
        for idx in range(start_idx + 1, end_idx):
            event = all_events[idx]
            
            # Check if this is a movement event for our agent
            event_agent = event.get("agent", "")
            if sanitize_fn:
                event_agent = sanitize_fn(event_agent)
            
            if event_agent != agent:
                continue
            
            event_type = event.get("type", "").lower()
            if event_type in EXPLICIT_MOVEMENT_TYPES:
                return True
        
        return False
    
    def _create_derived_transition(
        self,
        agent: str,
        from_location: str,
        to_location: str,
        prev_event: Dict[str, Any],
        curr_event: Dict[str, Any],
    ) -> DerivedTransition:
        """Create a derived transition record."""
        self._transition_counter += 1
        
        # Generate synthetic event ID
        derived_id = f"dt{self.chapter_num}_{self._transition_counter}"
        
        # Get event IDs
        prev_id = prev_event.get("global_id", prev_event.get("id", "unknown"))
        curr_id = curr_event.get("global_id", curr_event.get("id", "unknown"))
        
        return DerivedTransition(
            agent=agent,
            from_location=from_location,
            to_location=to_location,
            after_event_id=prev_id,
            before_event_id=curr_id,
            chapter=self.chapter_num,
            derived_event_id=derived_id,
        )
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Get the audit log of all derived transitions."""
        return self._audit_log.copy()
    
    def reset(self) -> None:
        """Reset the resolver state for a new chapter."""
        self._transition_counter = 0
        self._audit_log.clear()
    
    @staticmethod
    def analyze_movement_continuity(
        events: List[Dict[str, Any]],
        chapter_num: int = 1,
        sanitize_fn: Optional[callable] = None
    ) -> MovementContinuityResult:
        """
        Convenience static method to analyze movement continuity.
        
        Args:
            events: List of validated events
            chapter_num: Current chapter number
            sanitize_fn: Optional ID sanitizer function
        
        Returns:
            MovementContinuityResult with derived transitions
        """
        resolver = MovementResolver(chapter_num=chapter_num)
        return resolver.analyze_events(events, sanitize_fn)
